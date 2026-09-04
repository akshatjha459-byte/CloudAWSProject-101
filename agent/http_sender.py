"""
http_sender.py — Module 3: HTTP EventSender for the M2 agent.

Posts normalised ``SyncEvent`` objects to the Module 3 FastAPI backend.

    CREATED / MODIFIED → POST {BACKEND_URL}/sync/upload  (multipart)
    DELETED            → POST {BACKEND_URL}/sync/delete  (JSON)
    MOVED              → POST {BACKEND_URL}/sync/upload  (multipart, dest_path)

The backend origin is supplied by configuration (``BACKEND_URL``), not
hardcoded.  This module contains no AWS credentials.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent.events import OP_CREATED, OP_DELETED, OP_MODIFIED, OP_MOVED, SyncEvent
from agent.sender import EventSender

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30

HttpPostFn = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def default_http_post(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> tuple[int, bytes]:
    """Perform an HTTP POST using the standard library."""
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        payload = exc.read() if exc.fp is not None else b""
        return int(exc.code), payload


def _multipart(
    fields: dict[str, Optional[str]],
    file_bytes: Optional[bytes],
    filename: str,
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        if value is None:
            continue
        parts.append(f"--{boundary}".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
        parts.append(b"")
        parts.append(str(value).encode("utf-8"))
    if file_bytes is not None:
        parts.append(f"--{boundary}".encode("utf-8"))
        disposition = (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"'
        )
        parts.append(disposition.encode("utf-8"))
        parts.append(b"Content-Type: application/octet-stream")
        parts.append(b"")
        parts.append(file_bytes)
    parts.append(f"--{boundary}--".encode("utf-8"))
    parts.append(b"")
    body = b"\r\n".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


class HttpEventSender(EventSender):
    """Concrete ``EventSender`` that delivers events to the M3 REST API."""

    def __init__(
        self,
        backend_url: str,
        sync_folder: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        api_key: Optional[str] = None,
        http_post: Optional[HttpPostFn] = None,
    ) -> None:
        url = (backend_url or "").strip().rstrip("/")
        if not url:
            raise ValueError(
                "BACKEND_URL is required for HttpEventSender. "
                "Set it to the deployed backend origin (not a hardcoded address)."
            )
        self.backend_url = url
        self.sync_folder = sync_folder
        self.timeout = timeout
        self.api_key = api_key if api_key is not None else os.environ.get("API_KEY", "")
        self._http_post = http_post or default_http_post
        self.last_status: Optional[int] = None
        self.last_error: Optional[str] = None
        self.last_conflict_path: Optional[str] = None
        self.last_cloud_hash: Optional[str] = None

    def send(self, event: SyncEvent) -> None:
        """Dispatch *event*.  HTTP failures are recorded and logged, not raised."""
        self.last_status = None
        self.last_error = None
        self.last_conflict_path = None
        self.last_cloud_hash = None
        try:
            if event.operation == OP_DELETED:
                status, body = self._send_delete(event)
            else:
                status, body = self._send_upload(event)
            self.last_status = status
            if status >= 400:
                snippet = body.decode("utf-8", errors="replace")[:500]
                self.last_error = f"HTTP {status}: {snippet}"
                logger.error(
                    "Backend rejected %s for %s: %s",
                    event.operation,
                    event.path,
                    self.last_error,
                )
            else:
                logger.info(
                    "Backend accepted %s for %s (HTTP %s)",
                    event.operation,
                    event.path,
                    status,
                )
                self._handle_upload_success(event, body)
        except URLError as exc:
            self.last_error = str(exc.reason if getattr(exc, "reason", None) else exc)
            logger.error("Network error sending %s for %s: %s", event.operation, event.path, self.last_error)
        except OSError as exc:
            self.last_error = str(exc)
            logger.error("I/O error sending %s for %s: %s", event.operation, event.path, self.last_error)
        except Exception as exc:  # pylint: disable=broad-except
            self.last_error = str(exc)
            logger.error("Unexpected sender error for %s: %s", event.operation, exc)

    def _send_delete(self, event: SyncEvent) -> tuple[int, bytes]:
        payload = event.to_dict()
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return self._http_post(
            f"{self.backend_url}/sync/delete",
            headers,
            body,
            self.timeout,
        )

    def _send_upload(self, event: SyncEvent) -> tuple[int, bytes]:
        fields: dict[str, Optional[str]] = {
            "operation": event.operation,
            "path": event.path,
            "timestamp": event.timestamp,
            "hash": event.hash,
            "size": None if event.size is None else str(event.size),
            "dest_path": event.dest_path,
            "base_hash": event.base_hash,
        }
        file_bytes: Optional[bytes] = None
        filename = os.path.basename(event.path) or "file"
        if event.operation in (OP_CREATED, OP_MODIFIED):
            file_bytes = self._read_local_file(event.path)
            if file_bytes is None:
                raise FileNotFoundError(
                    f"Cannot upload {event.path}: local file not found under SYNC_FOLDER"
                )
            filename = os.path.basename(event.path) or filename
        elif event.operation == OP_MOVED and event.dest_path:
            file_bytes = self._read_local_file(event.dest_path)
            filename = os.path.basename(event.dest_path) or filename

        body, content_type = _multipart(fields, file_bytes, filename)
        headers = {"Content-Type": content_type, "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return self._http_post(
            f"{self.backend_url}/sync/upload",
            headers,
            body,
            self.timeout,
        )


    def _read_local_file(self, relative_path: str) -> Optional[bytes]:
        local = Path(self.sync_folder) / relative_path.replace("/", os.sep)
        if not local.is_file():
            logger.warning("Local file missing for upload: %s", local)
            return None
        return local.read_bytes()

    def _handle_upload_success(self, event: SyncEvent, body: bytes) -> None:
        if event.operation not in (OP_CREATED, OP_MODIFIED):
            return
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return
        if not payload.get("conflict"):
            return
        conflict_path = payload.get("conflict_path")
        file_info = payload.get("file") or {}
        file_id = file_info.get("id")
        self.last_conflict_path = conflict_path
        self.last_cloud_hash = file_info.get("current_hash")
        from agent.conflict import copy_local_to_conflict
        from agent.state import SyncState

        local_hash = event.hash or ""
        copy_local_to_conflict(self.sync_folder, event.path, local_hash)
        if file_id is not None:
            content = self.download_file(file_id)
            if content is not None:
                local = Path(self.sync_folder) / event.path.replace("/", os.sep)
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(content)
        state = SyncState(self.sync_folder)
        if self.last_cloud_hash:
            state.update_file_state(event.path, self.last_cloud_hash, deleted=False)
        if conflict_path:
            state.update_file_state(conflict_path, event.hash, deleted=False)

    def get_changes(self, since: Optional[str] = None) -> list[dict]:
        url = f"{self.backend_url}/sync/changes"
        if since:
            import urllib.parse
            url += "?since=" + urllib.parse.quote(since)
        request = Request(url, headers={"X-API-Key": self.api_key} if self.api_key else {})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read())
                    return data.get("changes", [])
                logger.error("Failed to fetch changes: %s", response.status)
        except Exception as exc:
            logger.error("Error fetching changes: %s", exc)
        return []

    def download_file(self, file_id: int) -> Optional[bytes]:
        url = f"{self.backend_url}/files/{file_id}/content"
        request = Request(url, headers={"X-API-Key": self.api_key} if self.api_key else {})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status == 200:
                    return response.read()
                logger.error("Failed to download file %s: %s", file_id, response.status)
        except Exception as exc:
            logger.error("Error downloading file %s: %s", file_id, exc)
        return None
