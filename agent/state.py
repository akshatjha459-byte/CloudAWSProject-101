import json
import os
from typing import Optional
from pathlib import Path

STATE_FILE = ".sync_state.json"

class SyncState:
    def __init__(self, sync_folder: str):
        self.state_path = Path(sync_folder) / STATE_FILE
        self._state: dict = self._load()
    
    def _load(self) -> dict:
        if not self.state_path.exists():
            return {"last_sync_timestamp": None, "files": {}}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_sync_timestamp": None, "files": {}}
            
    def _save(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

    def get_last_sync_timestamp(self) -> Optional[str]:
        return self._state.get("last_sync_timestamp")

    def set_last_sync_timestamp(self, timestamp: str) -> None:
        self._state["last_sync_timestamp"] = timestamp
        self._save()

    def get_file_hash(self, relative_path: str) -> Optional[str]:
        return self._state.get("files", {}).get(relative_path, {}).get("hash")

    def update_file_state(self, relative_path: str, file_hash: Optional[str], deleted: bool = False) -> None:
        if "files" not in self._state:
            self._state["files"] = {}
        if deleted:
            if relative_path in self._state["files"]:
                del self._state["files"][relative_path]
        else:
            self._state["files"][relative_path] = {"hash": file_hash}
        self._save()
