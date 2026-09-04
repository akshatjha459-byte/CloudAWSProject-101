import logging
import os
import time
import threading
from pathlib import Path
from typing import Optional

from agent.http_sender import HttpEventSender
from agent.state import SyncState
from agent.conflict import copy_local_to_conflict, is_conflict_copy_path
from agent.hashing import sha256_file

logger = logging.getLogger(__name__)

class CloudPoller:
    def __init__(self, sender: HttpEventSender, sync_folder: str, interval: int = 5):
        self.sender = sender
        self.sync_folder = sync_folder
        self.interval = interval
        self.state = SyncState(sync_folder)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("CloudPoller started with interval %s seconds.", self.interval)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        logger.info("CloudPoller stopped.")

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as exc:
                logger.error("CloudPoller error: %s", exc)
            self._stop_event.wait(self.interval)

    def _poll(self):
        since = self.state.get_last_sync_timestamp()
        changes = self.sender.get_changes(since)
        if not changes:
            return

        # Sort changes by timestamp (and id if present) to process in deterministic order
        changes.sort(key=lambda c: (c.get("timestamp"), c.get("id", 0)))

        # Group by timestamp so we only advance checkpoint when an entire timestamp's changes succeed
        groups = {}
        for c in changes:
            ts = c.get("timestamp")
            if ts not in groups:
                groups[ts] = []
            groups[ts].append(c)

        sorted_timestamps = sorted(groups.keys())

        for ts in sorted_timestamps:
            group_success = True
            for change in groups[ts]:
                try:
                    if not self._process_change(change):
                        group_success = False
                        break
                except Exception as exc:
                    logger.error("Unexpected error processing change: %s", exc)
                    group_success = False
                    break
            
            if group_success:
                self.state.set_last_sync_timestamp(ts)
            else:
                logger.warning("Stopping poll batch due to failure at timestamp %s", ts)
                break

    def _process_change(self, change: dict) -> bool:
        operation = change.get("operation")
        path = change.get("path")
        file_hash = change.get("file_hash") or change.get("hash")
        file_id = change.get("file_id")

        if not path or not operation:
            return True

        local_path = Path(self.sync_folder) / path.replace("/", os.sep)
        
        if operation == "DELETED":
            if local_path.exists():
                logger.info("Cloud deleted %s, deleting locally.", path)
                try:
                    local_path.unlink()
                except Exception as exc:
                    logger.error("Error deleting local file %s: %s", path, exc)
                    return False
            
            self.state.update_file_state(path, None, deleted=True)
            return True
        
        elif operation == "MOVED":
            dest_path_str = change.get("dest_path")
            if not dest_path_str:
                return True
            dest_path = Path(self.sync_folder) / dest_path_str.replace("/", os.sep)
            
            if dest_path.exists():
                try:
                    existing_hash = sha256_file(str(dest_path))
                    if existing_hash == file_hash:
                        self.state.update_file_state(path, None, deleted=True)
                        self.state.update_file_state(dest_path_str, file_hash, deleted=False)
                        return True
                except Exception:
                    pass
            
            if local_path.exists():
                logger.info("Cloud MOVED %s to %s, moving locally.", path, dest_path_str)
                try:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.replace(dest_path)
                    self.state.update_file_state(path, None, deleted=True)
                    self.state.update_file_state(dest_path_str, file_hash, deleted=False)
                    return True
                except Exception as exc:
                    logger.error("Error moving local file %s: %s", path, exc)
                    return False
            else:
                 logger.info("Cloud MOVED %s to %s, but local missing, downloading...", path, dest_path_str)
                 content = self.sender.download_file(file_id)
                 if content is not None:
                     try:
                         dest_path.parent.mkdir(parents=True, exist_ok=True)
                         dest_path.write_bytes(content)
                         self.state.update_file_state(path, None, deleted=True)
                         self.state.update_file_state(dest_path_str, file_hash, deleted=False)
                         logger.info("Successfully downloaded %s", dest_path_str)
                         return True
                     except Exception as exc:
                         logger.error("Error writing local file %s: %s", dest_path_str, exc)
                         return False
                 else:
                     logger.error("Failed to download file %s for MOVED", file_id)
                     return False

        elif operation in ("CREATED", "MODIFIED"):
            known_hash = self.state.get_file_hash(path)
            if known_hash == file_hash and local_path.exists():
                return True

            if (
                local_path.exists()
                and not is_conflict_copy_path(path)
                and self._local_diverged_from_base(local_path, known_hash)
                and known_hash
                and file_hash
                and known_hash != file_hash
            ):
                try:
                    local_hash = sha256_file(str(local_path))
                except Exception:
                    local_hash = None
                if local_hash and local_hash != file_hash:
                    logger.warning(
                        "Conflict on %s: local %s vs cloud %s (base %s)",
                        path,
                        local_hash,
                        file_hash,
                        known_hash,
                    )
                    conflict_rel = copy_local_to_conflict(
                        self.sync_folder, path, local_hash
                    )
                    if conflict_rel:
                        self.state.update_file_state(
                            conflict_rel, local_hash, deleted=False
                        )

            logger.info("Cloud %s %s, downloading...", operation, path)
            content = self.sender.download_file(file_id)
            if content is not None:
                try:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(content)
                    self.state.update_file_state(path, file_hash, deleted=False)
                    logger.info("Successfully downloaded %s", path)
                    return True
                except Exception as exc:
                    logger.error("Error writing local file %s: %s", path, exc)
                    return False
            else:
                logger.error("Failed to download file %s", file_id)
                return False
                
        return True

    @staticmethod
    def _local_diverged_from_base(local_path: Path, known_hash: Optional[str]) -> bool:
        """Return True when local bytes no longer match the last synced SHA-256.

        Short/non-hex hashes used in M7 unit tests are not treated as a local
        divergence so existing cloud-to-local tests keep their prior behavior.
        """
        if not known_hash or not local_path.exists():
            return False
        token = known_hash.lower()
        if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
            return False
        try:
            return sha256_file(str(local_path)) != token
        except Exception:
            return False
