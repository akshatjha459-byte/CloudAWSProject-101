"""
test_m2.py — Module 2 test suite.

Tests are deterministic: they use temporary directories and do not require
a real M3 backend, AWS connectivity, or any network access.

Coverage:
    - SHA-256 calculation (hashing.py)
    - SyncEvent construction and validation (events.py)
    - Relative path generation and portable path normalisation (events.py)
    - Event serialisation to dict / JSON (events.py)
    - Invalid operation rejection (events.py)
    - MOVED event validation (events.py)
    - LoggingEventSender dispatches without error (sender.py)
    - _should_ignore filtering (watcher.py)
    - _relative path helper (watcher.py)
    - SyncWatcher raises on missing SYNC_FOLDER (watcher.py)
    - End-to-end: CREATED event (watcher integration)
    - End-to-end: MODIFIED event (watcher integration)
    - End-to-end: DELETED event (watcher integration)
    - End-to-end: MOVED event (watcher integration)
    - Ignored filenames do not produce events (watcher integration)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import List
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Make the project root importable regardless of CWD.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent  # tests/ -> module-02/ -> modules/ -> project root? No.
# Layout: <project_root>/modules/module-02/tests/test_m2.py
# agent/ is at <project_root>/agent/
# So project root is three levels up from this file.
_PROJECT_ROOT = _HERE.parent.parent.parent  # tests -> module-02 -> modules -> project root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Patch SYNC_FOLDER before importing agent.config so the default resolves
# to a path we control inside tests.
with tempfile.TemporaryDirectory() as _tmp_default:
    os.environ.setdefault("SYNC_FOLDER", _tmp_default)

from agent.events import (  # noqa: E402
    OP_CREATED,
    OP_DELETED,
    OP_MODIFIED,
    OP_MOVED,
    SyncEvent,
    make_event,
)
from agent.hashing import sha256_file  # noqa: E402
from agent.sender import EventSender, LoggingEventSender  # noqa: E402
from agent.watcher import SyncWatcher, _relative, _should_ignore  # noqa: E402


# ===========================================================================
# Helpers
# ===========================================================================

class _CapturingSender(EventSender):
    """Test double that records every dispatched event."""

    def __init__(self) -> None:
        self.received: List[SyncEvent] = []

    def send(self, event: SyncEvent) -> None:
        self.received.append(event)


def _write(path: str, content: str = "hello") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _wait_for(sender: _CapturingSender, operation: str, timeout: float = 5.0) -> SyncEvent | None:
    """Poll until sender has received an event with the given operation."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for ev in sender.received:
            if ev.operation == operation:
                return ev
        time.sleep(0.05)
    return None


def _wait_for_count(sender: _CapturingSender, count: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(sender.received) >= count:
            return True
        time.sleep(0.05)
    return False


# ===========================================================================
# Unit tests: hashing
# ===========================================================================

class TestSha256File(unittest.TestCase):

    def test_known_content(self) -> None:
        """sha256_file matches hashlib computed on the same bytes."""
        content = b"Module 2 hashing test"
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(content)
            path = fh.name
        try:
            self.assertEqual(sha256_file(path), expected)
        finally:
            os.unlink(path)

    def test_empty_file(self) -> None:
        """SHA-256 of an empty file equals the known constant."""
        expected = hashlib.sha256(b"").hexdigest()
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            path = fh.name
        try:
            self.assertEqual(sha256_file(path), expected)
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            sha256_file("/nonexistent/file/that/does/not/exist.txt")

    def test_returns_lowercase_hex(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b"case check")
            path = fh.name
        try:
            result = sha256_file(path)
            self.assertEqual(result, result.lower())
            self.assertTrue(all(c in "0123456789abcdef" for c in result))
        finally:
            os.unlink(path)

    def test_large_file_chunked(self) -> None:
        """Files > 64 KiB are hashed correctly (chunked read path)."""
        content = b"x" * (256 * 1024)  # 256 KiB
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(content)
            path = fh.name
        try:
            self.assertEqual(sha256_file(path), expected)
        finally:
            os.unlink(path)


# ===========================================================================
# Unit tests: events
# ===========================================================================

class TestSyncEvent(unittest.TestCase):

    def test_created_event(self) -> None:
        ev = make_event(OP_CREATED, "reports/test.txt", hash="abc123", size=42)
        self.assertEqual(ev.operation, "CREATED")
        self.assertEqual(ev.path, "reports/test.txt")
        self.assertEqual(ev.hash, "abc123")
        self.assertEqual(ev.size, 42)
        self.assertIsNone(ev.dest_path)

    def test_modified_event(self) -> None:
        ev = make_event(OP_MODIFIED, "data/file.csv", hash="def456", size=100)
        self.assertEqual(ev.operation, "MODIFIED")

    def test_deleted_event_no_hash(self) -> None:
        ev = make_event(OP_DELETED, "old.txt")
        self.assertIsNone(ev.hash)
        self.assertIsNone(ev.size)

    def test_moved_event(self) -> None:
        ev = make_event(OP_MOVED, "a.txt", dest_path="b.txt")
        self.assertEqual(ev.operation, "MOVED")
        self.assertEqual(ev.path, "a.txt")
        self.assertEqual(ev.dest_path, "b.txt")

    def test_moved_requires_dest_path(self) -> None:
        with self.assertRaises(ValueError):
            make_event(OP_MOVED, "a.txt")  # no dest_path

    def test_invalid_operation_raises(self) -> None:
        with self.assertRaises(ValueError):
            SyncEvent(
                operation="UPLOADED",  # not a valid operation
                path="x.txt",
                hash=None,
                size=None,
                timestamp="2026-01-01T00:00:00Z",
            )

    def test_portable_paths_backslash(self) -> None:
        """Windows-style backslash paths are normalised to forward slashes."""
        ev = make_event(OP_CREATED, r"subdir\file.txt", hash="h", size=1)
        self.assertEqual(ev.path, "subdir/file.txt")

    def test_to_dict_created(self) -> None:
        ev = make_event(OP_CREATED, "x.txt", hash="aaa", size=10,
                        timestamp="2026-09-03T00:00:00Z")
        d = ev.to_dict()
        self.assertEqual(d["operation"], "CREATED")
        self.assertEqual(d["path"], "x.txt")
        self.assertEqual(d["hash"], "aaa")
        self.assertEqual(d["size"], 10)
        self.assertEqual(d["timestamp"], "2026-09-03T00:00:00Z")
        self.assertNotIn("dest_path", d)

    def test_to_dict_moved_includes_dest_path(self) -> None:
        ev = make_event(OP_MOVED, "a.txt", dest_path="b.txt",
                        timestamp="2026-09-03T00:00:00Z")
        d = ev.to_dict()
        self.assertIn("dest_path", d)
        self.assertEqual(d["dest_path"], "b.txt")

    def test_to_json_is_valid_json(self) -> None:
        ev = make_event(OP_MODIFIED, "f.txt", hash="zzz", size=99,
                        timestamp="2026-09-03T00:00:00Z")
        parsed = json.loads(ev.to_json())
        self.assertEqual(parsed["operation"], "MODIFIED")

    def test_timestamp_defaults_to_utc_iso(self) -> None:
        ev = make_event(OP_CREATED, "t.txt", hash="h", size=1)
        # Should end in Z and be parseable.
        self.assertTrue(ev.timestamp.endswith("Z"))
        self.assertRegex(ev.timestamp, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


# ===========================================================================
# Unit tests: sender
# ===========================================================================

class TestLoggingEventSender(unittest.TestCase):

    def test_send_does_not_raise(self) -> None:
        sender = LoggingEventSender()
        ev = make_event(OP_CREATED, "test.txt", hash="h", size=4)
        # Must not raise.
        sender.send(ev)

    def test_capturing_sender(self) -> None:
        sender = _CapturingSender()
        ev = make_event(OP_DELETED, "gone.txt")
        sender.send(ev)
        self.assertEqual(len(sender.received), 1)
        self.assertEqual(sender.received[0].operation, "DELETED")


# ===========================================================================
# Unit tests: watcher helpers
# ===========================================================================

class TestWatcherHelpers(unittest.TestCase):

    def test_should_ignore_gitkeep(self) -> None:
        self.assertTrue(_should_ignore("/some/dir/.gitkeep"))

    def test_should_ignore_tmp_suffix(self) -> None:
        self.assertTrue(_should_ignore("/some/dir/upload.tmp"))

    def test_should_not_ignore_txt(self) -> None:
        self.assertFalse(_should_ignore("/sync/dir/report.txt"))

    def test_should_not_ignore_pdf(self) -> None:
        self.assertFalse(_should_ignore("/sync/dir/salary.pdf"))

    def test_should_ignore_ds_store(self) -> None:
        self.assertTrue(_should_ignore("/sync/.DS_Store"))

    def test_relative_forward_slashes(self) -> None:
        if os.name == "nt":
            base = "C:\\Users\\user\\org\\files"
            full = "C:\\Users\\user\\org\\files\\subdir\\doc.txt"
        else:
            base = "/home/user/org/files"
            full = "/home/user/org/files/subdir/doc.txt"
        result = _relative(full, base)
        self.assertEqual(result, "subdir/doc.txt")

    def test_relative_root_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            full = os.path.join(td, "file.txt")
            result = _relative(full, td)
            self.assertEqual(result, "file.txt")

    def test_watcher_raises_on_missing_folder(self) -> None:
        sender = _CapturingSender()
        watcher = SyncWatcher(
            sync_folder="/this/path/does/not/exist/ever",
            sender=sender,
        )
        with self.assertRaises(FileNotFoundError):
            watcher.start()


# ===========================================================================
# Integration tests: end-to-end watcher events
# ===========================================================================

class TestWatcherIntegration(unittest.TestCase):
    """These tests start a real watchdog observer against a temp directory."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._sender = _CapturingSender()
        self._watcher = SyncWatcher(
            sync_folder=self._tmpdir,
            sender=self._sender,
        )
        self._watcher.start()
        # Give watchdog a moment to initialise.
        time.sleep(0.3)

    def tearDown(self) -> None:
        self._watcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _clear(self) -> None:
        self._sender.received.clear()

    def test_created_event(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, "new_file.txt")
        temp_path = path + ".tmp"
        _write(temp_path, "hello world")
        os.rename(temp_path, path)
        ev = _wait_for(self._sender, OP_CREATED)
        self.assertIsNotNone(ev, "Expected CREATED event but none received within timeout")
        self.assertEqual(ev.operation, OP_CREATED)
        self.assertEqual(ev.path, "new_file.txt")
        self.assertIsNotNone(ev.hash)
        self.assertIsNotNone(ev.size)
        # Verify the hash matches
        expected_hash = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(ev.hash, expected_hash)

    def test_modified_event(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, "modify_me.txt")
        _write(path, "initial")
        _wait_for(self._sender, OP_CREATED, timeout=3.0)
        self._clear()
        time.sleep(0.1)
        _write(path, "modified content")
        ev = _wait_for(self._sender, OP_MODIFIED)
        self.assertIsNotNone(ev, "Expected MODIFIED event but none received within timeout")
        self.assertEqual(ev.operation, OP_MODIFIED)
        self.assertEqual(ev.path, "modify_me.txt")

    def test_deleted_event(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, "delete_me.txt")
        _write(path, "bye")
        _wait_for(self._sender, OP_CREATED, timeout=3.0)
        self._clear()
        time.sleep(0.1)
        os.unlink(path)
        ev = _wait_for(self._sender, OP_DELETED)
        self.assertIsNotNone(ev, "Expected DELETED event but none received within timeout")
        self.assertEqual(ev.operation, OP_DELETED)
        self.assertEqual(ev.path, "delete_me.txt")
        self.assertIsNone(ev.hash)
        self.assertIsNone(ev.size)

    def test_moved_event(self) -> None:
        self._clear()
        src = os.path.join(self._tmpdir, "before.txt")
        dst = os.path.join(self._tmpdir, "after.txt")
        _write(src, "move me")
        _wait_for(self._sender, OP_CREATED, timeout=3.0)
        self._clear()
        time.sleep(0.1)
        os.rename(src, dst)
        ev = _wait_for(self._sender, OP_MOVED)
        self.assertIsNotNone(ev, "Expected MOVED event but none received within timeout")
        self.assertEqual(ev.operation, OP_MOVED)
        self.assertEqual(ev.path, "before.txt")
        self.assertEqual(ev.dest_path, "after.txt")

    def test_gitkeep_ignored(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, ".gitkeep")
        _write(path, "")
        time.sleep(0.5)
        operations = [ev.operation for ev in self._sender.received
                      if ev.path == ".gitkeep"]
        self.assertEqual(operations, [], ".gitkeep should produce no events")

    def test_tmp_file_ignored(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, "upload.tmp")
        _write(path, "temp")
        time.sleep(0.5)
        operations = [ev.operation for ev in self._sender.received
                      if ev.path == "upload.tmp"]
        self.assertEqual(operations, [], ".tmp files should produce no events")

    def test_subdirectory_file(self) -> None:
        """Files in subdirectories produce events with relative paths."""
        self._clear()
        subdir = os.path.join(self._tmpdir, "reports")
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, "q1.txt")
        _write(path, "quarter 1")
        ev = _wait_for(self._sender, OP_CREATED)
        self.assertIsNotNone(ev, "Expected CREATED event for subdir file")
        self.assertEqual(ev.path, "reports/q1.txt")

    def test_watcher_is_alive(self) -> None:
        self.assertTrue(self._watcher.is_alive())

    def test_transient_delete_suppressed_when_file_reappears(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, "transient.txt")
        _write(path, "content")
        _wait_for(self._sender, OP_CREATED, timeout=3.0)
        self._clear()
        time.sleep(0.1)
        os.unlink(path)
        time.sleep(0.1)
        _write(path, "replaced content")
        time.sleep(1.5)
        ops = [ev.operation for ev in self._sender.received]
        self.assertNotIn(OP_DELETED, ops)
        self.assertIn(OP_CREATED, ops)

    def test_genuine_delete_propagates_after_debounce(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, "real_delete.txt")
        _write(path, "content")
        _wait_for(self._sender, OP_CREATED, timeout=3.0)
        self._clear()
        time.sleep(0.1)
        os.unlink(path)
        ev = _wait_for(self._sender, OP_DELETED, timeout=5.0)
        self.assertIsNotNone(ev, "Expected DELETED event but none received within timeout")
        self.assertEqual(ev.operation, OP_DELETED)
        self.assertEqual(ev.path, "real_delete.txt")

    def test_transient_move_no_duplicate_created_or_deleted(self) -> None:
        self._clear()
        path = os.path.join(self._tmpdir, "atomic.txt")
        _write(path, "content")
        _wait_for(self._sender, OP_CREATED, timeout=3.0)
        self._clear()
        time.sleep(0.1)

        os.unlink(path)
        tmp_path = path + ".tmp"
        _write(tmp_path, "replaced")
        os.rename(tmp_path, path)

        time.sleep(1.5)

        ops = [ev.operation for ev in self._sender.received]
        self.assertEqual(ops.count(OP_CREATED), 1)
        self.assertEqual(ops.count(OP_DELETED), 0)


if __name__ == "__main__":
    unittest.main()
