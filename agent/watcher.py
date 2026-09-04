"""
watcher.py — Module 2: Filesystem watcher.

Uses the ``watchdog`` library to monitor the configured synchronisation
directory (SYNC_FOLDER from M1/config.py) and converts raw filesystem events
into normalised ``SyncEvent`` objects that are dispatched via an
``EventSender``.

Supported event types:
    CREATED   — a new file was created inside the watched directory
    MODIFIED  — an existing file's content changed
    DELETED   — a file was removed
    MOVED     — a file was renamed or moved within the watched directory

Directory events are silently ignored; only file events are normalised.

Dependencies:
    watchdog >= 3.0  (see agent/requirements.txt)
"""

from __future__ import annotations

import logging
import os
import time
import threading
from pathlib import Path

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from agent.events import (
    OP_CREATED,
    OP_DELETED,
    OP_MODIFIED,
    OP_MOVED,
    make_event,
)
from agent.hashing import sha256_file
from agent.sender import EventSender

logger = logging.getLogger(__name__)

# Filenames to ignore (internal / OS artefacts).
_IGNORED_NAMES = frozenset({".gitkeep", ".DS_Store", "Thumbs.db", ".sync_state.json"})
# Suffixes to ignore.
_IGNORED_SUFFIXES = frozenset({".tmp", ".part", ".crdownload", ".swp", ".swo"})


def _should_ignore(path: str) -> bool:
    """Return True if the path should not produce a sync event."""
    name = os.path.basename(path)
    if name in _IGNORED_NAMES:
        return True
    _, suffix = os.path.splitext(name)
    if suffix.lower() in _IGNORED_SUFFIXES:
        return True
    # Hidden files starting with a dot (other than .gitkeep already above) are
    # passed through — they may be legitimate organisation files.
    return False


def _relative(abs_path: str, base: str) -> str:
    """Return *abs_path* as a portable relative path under *base*."""
    rel = os.path.relpath(abs_path, base)
    return rel.replace("\\", "/")


class _SyncEventHandler(FileSystemEventHandler):
    """watchdog event handler that normalises raw events into ``SyncEvent``."""

    def __init__(self, sync_folder: str, sender: EventSender) -> None:
        super().__init__()
        self._sync_folder = sync_folder
        self._sender = sender
        self._pending_deletes: dict[str, float] = {}
        self._delete_debounce_seconds = 1.0
        self._lock = threading.Lock()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _hash_and_size(self, abs_path: str) -> tuple[str | None, int | None]:
        """Return (sha256_hex, size_bytes) for a file, or (None, None) on error."""
        try:
            size = os.path.getsize(abs_path)
            digest = sha256_file(abs_path)
            return digest, size
        except OSError as exc:
            logger.warning("Could not hash %s: %s", abs_path, exc)
            return None, None

    def _dispatch(self, operation: str, src: str, dest: str | None = None) -> None:
        """Build and send a ``SyncEvent`` for *src*."""
        if _should_ignore(src):
            logger.debug("Ignoring %s (matched ignore list)", src)
            return

        rel_src = _relative(src, self._sync_folder)
        base_hash = None

        if operation in (OP_CREATED, OP_MODIFIED):
            file_hash, size = self._hash_and_size(src)
            # Prevent loop: if the hash matches our known state, ignore it
            from agent.state import SyncState
            state = SyncState(self._sync_folder)
            known_hash = state.get_file_hash(rel_src)
            if known_hash and known_hash == file_hash:
                logger.debug("Ignoring %s %s (hash %s matches known state)", operation, rel_src, file_hash)
                return
            base_hash = known_hash
        else:
            file_hash, size = None, None

        rel_dest: str | None = None
        if operation == OP_MOVED and dest is not None:
            if _should_ignore(dest):
                logger.debug("Ignoring MOVED destination %s", dest)
                return
            rel_dest = _relative(dest, self._sync_folder)

        event = make_event(
            operation=operation,
            relative_path=rel_src,
            hash=file_hash,
            size=size,
            dest_path=rel_dest,
            base_hash=base_hash,
        )
        logger.info("Dispatching: %s", event.to_json())
        try:
            self._sender.send(event)
            # Update state after successful send
            from agent.state import SyncState
            state = SyncState(self._sync_folder)
            conflict_path = getattr(self._sender, "last_conflict_path", None)
            if conflict_path:
                cloud_hash = getattr(self._sender, "last_cloud_hash", None)
                state.update_file_state(rel_src, cloud_hash, deleted=False)
                state.update_file_state(conflict_path, file_hash, deleted=False)
            elif operation == OP_DELETED:
                state.update_file_state(rel_src, None, deleted=True)
            elif operation == OP_MOVED and rel_dest:
                state.update_file_state(rel_src, None, deleted=True)
                state.update_file_state(rel_dest, file_hash, deleted=False)
            else:
                state.update_file_state(rel_src, file_hash, deleted=False)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Sender raised an exception for event %s: %s", event.operation, exc)

    def _flush_loop(self) -> None:
        while True:
            time.sleep(1.0)
            self._process_pending_deletes()

    def _process_pending_deletes(self) -> None:
        now = time.monotonic()
        to_dispatch: list[str] = []
        with self._lock:
            for path, ts in list(self._pending_deletes.items()):
                if now - ts >= self._delete_debounce_seconds:
                    to_dispatch.append(path)
            for path in to_dispatch:
                del self._pending_deletes[path]
        for path in to_dispatch:
            if not os.path.exists(path):
                self._dispatch(OP_DELETED, path)
            else:
                self._dispatch(OP_CREATED, path)

    # ------------------------------------------------------------------
    # watchdog callbacks (file events only — directory events ignored)
    # ------------------------------------------------------------------

    def on_created(self, raw_event: FileCreatedEvent | DirCreatedEvent) -> None:
        if isinstance(raw_event, DirCreatedEvent):
            return
        self._process_pending_deletes()
        with self._lock:
            if raw_event.src_path in self._pending_deletes:
                del self._pending_deletes[raw_event.src_path]
        self._dispatch(OP_CREATED, raw_event.src_path)

    def on_modified(self, raw_event: FileModifiedEvent | DirModifiedEvent) -> None:
        if isinstance(raw_event, DirModifiedEvent):
            return
        self._process_pending_deletes()
        with self._lock:
            if raw_event.src_path in self._pending_deletes:
                del self._pending_deletes[raw_event.src_path]
        self._dispatch(OP_MODIFIED, raw_event.src_path)

    def on_deleted(self, raw_event: FileDeletedEvent | DirDeletedEvent) -> None:
        if isinstance(raw_event, DirDeletedEvent):
            return
        with self._lock:
            self._pending_deletes[raw_event.src_path] = time.monotonic()

    def on_moved(self, raw_event: FileMovedEvent | DirMovedEvent) -> None:
        if isinstance(raw_event, DirMovedEvent):
            return
        
        self._process_pending_deletes()
        with self._lock:
            if raw_event.src_path in self._pending_deletes:
                del self._pending_deletes[raw_event.src_path]
        
        src_ignored = _should_ignore(raw_event.src_path)
        dest_ignored = _should_ignore(raw_event.dest_path)
        
        if src_ignored and dest_ignored:
            return
        elif src_ignored and not dest_ignored:
            self._dispatch(OP_CREATED, raw_event.dest_path)
        elif not src_ignored and dest_ignored:
            self._dispatch(OP_DELETED, raw_event.src_path)
        else:
            self._dispatch(OP_MOVED, raw_event.src_path, raw_event.dest_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SyncWatcher:
    """Manages the watchdog observer lifecycle for the configured sync folder.

    Usage::

        sender = LoggingEventSender()
        watcher = SyncWatcher(sync_folder="/abs/path/to/organization/files",
                              sender=sender)
        watcher.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            watcher.stop()
    """

    def __init__(self, sync_folder: str, sender: EventSender) -> None:
        self._sync_folder = sync_folder
        self._sender = sender
        self._observer: Observer | None = None

    def start(self) -> None:
        """Start watching *sync_folder*.  Raises ``FileNotFoundError`` if it
        does not exist."""
        folder = Path(self._sync_folder)
        if not folder.is_dir():
            raise FileNotFoundError(
                f"SYNC_FOLDER does not exist or is not a directory: {self._sync_folder}"
            )

        handler = _SyncEventHandler(
            sync_folder=str(folder.resolve()),
            sender=self._sender,
        )
        self._observer = Observer()
        self._observer.schedule(handler, str(folder.resolve()), recursive=True)
        self._observer.start()
        logger.info("Watcher started on %s", self._sync_folder)

    def stop(self) -> None:
        """Stop the watcher gracefully."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        logger.info("Watcher stopped.")

    def is_alive(self) -> bool:
        """Return True if the observer thread is running."""
        return self._observer is not None and self._observer.is_alive()
