import logging
import os
import time
import threading
from pathlib import Path
from typing import Optional

from agent.http_sender import HttpEventSender
from agent.state import SyncState

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

        latest_timestamp = since
        for change in changes:
            # Check if this change is newer
            ts = change.get("timestamp")
            if not latest_timestamp or ts > latest_timestamp:
                latest_timestamp = ts

            operation = change.get("operation")
            path = change.get("path")
            file_hash = change.get("file_hash")
            file_id = change.get("file_id")

            if not path or not operation:
                continue

            local_path = Path(self.sync_folder) / path.replace("/", os.sep)
            
            if operation == "DELETED":
                if local_path.exists():
                    logger.info("Cloud deleted %s, deleting locally.", path)
                    try:
                        local_path.unlink()
                        self.state.update_file_state(path, None, deleted=True)
                    except Exception as exc:
                        logger.error("Error deleting local file %s: %s", path, exc)
            
            elif operation == "MOVED":
                dest_path_str = change.get("dest_path")
                if not dest_path_str:
                    continue
                dest_path = Path(self.sync_folder) / dest_path_str.replace("/", os.sep)
                
                # Check if we need to download it if it doesn't exist
                if not dest_path.exists() and local_path.exists():
                    logger.info("Cloud MOVED %s to %s, moving locally.", path, dest_path_str)
                    try:
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        local_path.rename(dest_path)
                        self.state.update_file_state(path, None, deleted=True)
                        self.state.update_file_state(dest_path_str, file_hash, deleted=False)
                    except Exception as exc:
                        logger.error("Error moving local file %s: %s", path, exc)
                elif not dest_path.exists() and not local_path.exists():
                     # Just download it
                     logger.info("Cloud MOVED %s to %s, but local missing, downloading...", path, dest_path_str)
                     content = self.sender.download_file(file_id)
                     if content is not None:
                         try:
                             dest_path.parent.mkdir(parents=True, exist_ok=True)
                             dest_path.write_bytes(content)
                             self.state.update_file_state(path, None, deleted=True)
                             self.state.update_file_state(dest_path_str, file_hash, deleted=False)
                             logger.info("Successfully downloaded %s", dest_path_str)
                         except Exception as exc:
                             logger.error("Error writing local file %s: %s", dest_path_str, exc)

            elif operation in ("CREATED", "MODIFIED"):
                known_hash = self.state.get_file_hash(path)
                if known_hash == file_hash and local_path.exists():
                    # We already have this file and hash
                    continue
                
                logger.info("Cloud %s %s, downloading...", operation, path)
                content = self.sender.download_file(file_id)
                if content is not None:
                    try:
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        local_path.write_bytes(content)
                        self.state.update_file_state(path, file_hash, deleted=False)
                        logger.info("Successfully downloaded %s", path)
                    except Exception as exc:
                        logger.error("Error writing local file %s: %s", path, exc)

        if latest_timestamp:
            self.state.set_last_sync_timestamp(latest_timestamp)
