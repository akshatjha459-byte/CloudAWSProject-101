"""
test_m3.py — Module 3 test suite.

Covers the FastAPI contract, in-memory adapters, HttpEventSender, M2 event
compatibility, HTTP error handling, and BACKEND_URL configuration.

No AWS credentials or network access are required.  TestClient talks to the
in-process app.  HttpEventSender uses an injectable HTTP transport.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent  # tests -> module-03 -> modules -> root
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("SYNC_FOLDER", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from agent.events import (  # noqa: E402
    OP_CREATED,
    OP_DELETED,
    OP_MODIFIED,
    OP_MOVED,
    make_event,
)
from agent.http_sender import HttpEventSender  # noqa: E402
from backend.main import create_app  # noqa: E402


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class _M3TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)


# ===========================================================================
# Health
# ===========================================================================

class TestHealth(_M3TestCase):
    def test_health_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("service", body)


# ===========================================================================
# Upload
# ===========================================================================

class TestUpload(_M3TestCase):
    def test_valid_created_upload(self) -> None:
        content = b"hello m3"
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "reports/hello.txt",
                "timestamp": "2026-09-03T00:00:00Z",
                "hash": _sha(content),
                "size": str(len(content)),
            },
            files={"file": ("hello.txt", content, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["file"]["relative_path"], "reports/hello.txt")
        self.assertEqual(body["file"]["current_version"], 1)
        self.assertFalse(body["idempotent"])

    def test_modified_creates_new_version(self) -> None:
        first = b"v1"
        second = b"v2-content"
        self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "doc.txt",
                "timestamp": "2026-09-03T00:00:00Z",
                "hash": _sha(first),
                "size": str(len(first)),
            },
            files={"file": ("doc.txt", first, "application/octet-stream")},
        )
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "MODIFIED",
                "path": "doc.txt",
                "timestamp": "2026-09-03T00:01:00Z",
                "hash": _sha(second),
                "size": str(len(second)),
            },
            files={"file": ("doc.txt", second, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["file"]["current_version"], 2)

    def test_idempotent_same_hash(self) -> None:
        content = b"same"
        payload = {
            "operation": "CREATED",
            "path": "same.txt",
            "timestamp": "2026-09-03T00:00:00Z",
            "hash": _sha(content),
            "size": str(len(content)),
        }
        files = {"file": ("same.txt", content, "application/octet-stream")}
        self.client.post("/sync/upload", data=payload, files=files)
        response = self.client.post("/sync/upload", data=payload, files=files)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["idempotent"])

    def test_missing_file_rejected(self) -> None:
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "missing.txt",
                "timestamp": "2026-09-03T00:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "validation_error")

    def test_invalid_operation_rejected(self) -> None:
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "UPLOADED",
                "path": "x.txt",
                "timestamp": "2026-09-03T00:00:00Z",
            },
            files={"file": ("x.txt", b"x", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)

    def test_hash_mismatch_rejected(self) -> None:
        content = b"actual"
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "badhash.txt",
                "timestamp": "2026-09-03T00:00:00Z",
                "hash": "0" * 64,
                "size": str(len(content)),
            },
            files={"file": ("badhash.txt", content, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)

    def test_size_mismatch_rejected(self) -> None:
        content = b"abc"
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "badsize.txt",
                "timestamp": "2026-09-03T00:00:00Z",
                "hash": _sha(content),
                "size": "99",
            },
            files={"file": ("badsize.txt", content, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_path_rejected(self) -> None:
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "   ",
                "timestamp": "2026-09-03T00:00:00Z",
            },
            files={"file": ("x.txt", b"x", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)

    def test_moved_without_dest_path_rejected(self) -> None:
        response = self.client.post(
            "/sync/upload",
            data={
                "operation": "MOVED",
                "path": "old.txt",
                "timestamp": "2026-09-03T00:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 400)


# ===========================================================================
# Delete
# ===========================================================================

class TestDelete(_M3TestCase):
    def test_valid_delete(self) -> None:
        content = b"bye"
        self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "gone.txt",
                "timestamp": "2026-09-03T00:00:00Z",
                "hash": _sha(content),
                "size": str(len(content)),
            },
            files={"file": ("gone.txt", content, "application/octet-stream")},
        )
        response = self.client.post(
            "/sync/delete",
            json={
                "operation": "DELETED",
                "path": "gone.txt",
                "hash": None,
                "size": None,
                "timestamp": "2026-09-03T00:05:00Z",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["file"]["deleted"])
        self.assertEqual(body["file"]["status"], "deleted")

    def test_delete_unknown_path_still_succeeds(self) -> None:
        response = self.client.post(
            "/sync/delete",
            json={
                "operation": "DELETED",
                "path": "never-existed.txt",
                "timestamp": "2026-09-03T00:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["file"]["deleted"])

    def test_invalid_delete_operation(self) -> None:
        response = self.client.post(
            "/sync/delete",
            json={
                "operation": "CREATED",
                "path": "x.txt",
                "timestamp": "2026-09-03T00:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"], "validation_error")

    def test_delete_missing_path(self) -> None:
        response = self.client.post(
            "/sync/delete",
            json={
                "operation": "DELETED",
                "timestamp": "2026-09-03T00:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 422)


# ===========================================================================
# Query endpoints
# ===========================================================================

class TestQueryEndpoints(_M3TestCase):
    def _seed(self) -> None:
        content = b"seed"
        self.client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": "seed.txt",
                "timestamp": "2026-09-03T00:00:00Z",
                "hash": _sha(content),
                "size": str(len(content)),
            },
            files={"file": ("seed.txt", content, "application/octet-stream")},
        )

    def test_sync_changes(self) -> None:
        self._seed()
        response = self.client.get("/sync/changes")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["count"], 1)
        self.assertEqual(body["changes"][0]["operation"], "CREATED")

    def test_sync_changes_since_filter(self) -> None:
        self._seed()
        later = self.client.get("/sync/changes", params={"since": "2099-01-01T00:00:00Z"})
        self.assertEqual(later.status_code, 200)
        self.assertEqual(later.json()["count"], 0)

    def test_files(self) -> None:
        self._seed()
        response = self.client.get("/files")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["files"][0]["filename"], "seed.txt")

    def test_file_versions(self) -> None:
        self._seed()
        file_id = self.client.get("/files").json()["files"][0]["id"]
        response = self.client.get(f"/files/{file_id}/versions")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["file_id"], file_id)
        self.assertGreaterEqual(body["count"], 1)
        self.assertEqual(body["versions"][0]["operation"], "CREATED")

    def test_file_versions_not_found(self) -> None:
        response = self.client.get("/files/999/versions")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["error"], "not_found")

    def test_logs(self) -> None:
        self._seed()
        response = self.client.get("/logs")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["count"], 1)
        self.assertEqual(body["logs"][0]["status"], "SUCCESS")

    def test_status(self) -> None:
        self._seed()
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["storage_adapter"], "memory")
        self.assertEqual(body["metadata_adapter"], "memory")
        self.assertEqual(body["file_count"], 1)
        self.assertIn("s3", body["notes"])
        self.assertIn("rds", body["notes"])


# ===========================================================================
# HTTP error handling
# ===========================================================================

class TestHttpErrors(_M3TestCase):
    def test_unknown_route(self) -> None:
        response = self.client.get("/not-a-real-route")
        self.assertEqual(response.status_code, 404)

    def test_method_not_allowed(self) -> None:
        response = self.client.delete("/health")
        self.assertEqual(response.status_code, 405)


# ===========================================================================
# HttpEventSender + M2 compatibility
# ===========================================================================

class _RecordingTransport:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.calls: List[Tuple[str, dict, bytes]] = []

    def __call__(self, url: str, headers: dict, body: bytes, timeout: float):
        self.calls.append((url, headers, body))
        path = urlparse(url).path
        response = self.client.request(
            "POST",
            path,
            content=body,
            headers=headers,
        )
        return response.status_code, response.content


class TestHttpEventSender(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.transport = _RecordingTransport(self.client)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _sender(self, url: str = "https://sync.example.internal") -> HttpEventSender:
        return HttpEventSender(
            backend_url=url,
            sync_folder=self._tmpdir,
            http_post=self.transport,
        )

    def test_created_event_uploads_content(self) -> None:
        path = Path(self._tmpdir) / "note.txt"
        path.write_bytes(b"from-agent")
        event = make_event(
            OP_CREATED,
            "note.txt",
            hash=_sha(b"from-agent"),
            size=len(b"from-agent"),
            timestamp="2026-09-03T12:00:00Z",
        )
        sender = self._sender()
        sender.send(event)
        self.assertEqual(sender.last_status, 200)
        self.assertIsNone(sender.last_error)
        self.assertTrue(self.transport.calls[0][0].endswith("/sync/upload"))
        files = self.client.get("/files").json()["files"]
        self.assertEqual(files[0]["relative_path"], "note.txt")

    def test_deleted_event_posts_json(self) -> None:
        event = make_event(OP_DELETED, "note.txt", timestamp="2026-09-03T12:00:00Z")
        sender = self._sender()
        sender.send(event)
        self.assertEqual(sender.last_status, 200)
        url, headers, body = self.transport.calls[0]
        self.assertTrue(url.endswith("/sync/delete"))
        self.assertIn("application/json", headers["Content-Type"])
        parsed = json.loads(body.decode("utf-8"))
        self.assertEqual(parsed["operation"], "DELETED")
        self.assertEqual(parsed["path"], "note.txt")
        self.assertNotIn("dest_path", parsed)

    def test_modified_event_compatibility(self) -> None:
        path = Path(self._tmpdir) / "note.txt"
        path.write_bytes(b"v1")
        sender = self._sender()
        sender.send(make_event(OP_CREATED, "note.txt", hash=_sha(b"v1"), size=2,
                               timestamp="2026-09-03T12:00:00Z"))
        path.write_bytes(b"v2!")
        sender.send(make_event(OP_MODIFIED, "note.txt", hash=_sha(b"v2!"), size=3,
                               timestamp="2026-09-03T12:01:00Z"))
        self.assertEqual(sender.last_status, 200)
        versions = self.client.get("/files/1/versions").json()
        self.assertEqual(versions["count"], 2)

    def test_moved_event_compatibility(self) -> None:
        src = Path(self._tmpdir) / "old.txt"
        dst = Path(self._tmpdir) / "new.txt"
        src.write_bytes(b"move-me")
        sender = self._sender()
        sender.send(make_event(OP_CREATED, "old.txt", hash=_sha(b"move-me"), size=7,
                               timestamp="2026-09-03T12:00:00Z"))
        src.rename(dst)
        sender.send(make_event(OP_MOVED, "old.txt", dest_path="new.txt",
                               timestamp="2026-09-03T12:02:00Z"))
        self.assertEqual(sender.last_status, 200)
        files = self.client.get("/files").json()["files"]
        self.assertEqual(files[0]["relative_path"], "new.txt")

    def test_http_error_is_recorded_not_raised(self) -> None:
        def failing_post(url, headers, body, timeout):
            return 500, b'{"success": false, "error": "internal_error"}'

        sender = HttpEventSender(
            backend_url="https://sync.example.internal",
            sync_folder=self._tmpdir,
            http_post=failing_post,
        )
        event = make_event(OP_DELETED, "x.txt", timestamp="2026-09-03T12:00:00Z")
        sender.send(event)  # must not raise
        self.assertEqual(sender.last_status, 500)
        self.assertIsNotNone(sender.last_error)
        self.assertIn("500", sender.last_error)

    def test_backend_url_required(self) -> None:
        with self.assertRaises(ValueError):
            HttpEventSender(backend_url="  ", sync_folder=self._tmpdir)

    def test_backend_url_from_environment_not_localhost_default(self) -> None:
        """Agent config exposes BACKEND_URL from the environment; no baked-in localhost."""
        from importlib import reload
        import agent.config as cfg

        previous = os.environ.get("BACKEND_URL")
        os.environ["BACKEND_URL"] = "https://ec2-example.compute.amazonaws.com"
        try:
            reload(cfg)
            self.assertEqual(cfg.BACKEND_URL, "https://ec2-example.compute.amazonaws.com")
            self.assertNotEqual(cfg.BACKEND_URL, "http://localhost:8000")
        finally:
            if previous is None:
                os.environ.pop("BACKEND_URL", None)
            else:
                os.environ["BACKEND_URL"] = previous
            reload(cfg)

    def test_empty_backend_url_env(self) -> None:
        from importlib import reload
        import agent.config as cfg

        previous = os.environ.get("BACKEND_URL")
        os.environ["BACKEND_URL"] = ""
        try:
            reload(cfg)
            self.assertEqual(cfg.BACKEND_URL, "")
        finally:
            if previous is None:
                os.environ.pop("BACKEND_URL", None)
            else:
                os.environ["BACKEND_URL"] = previous
            reload(cfg)

    def test_trailing_slash_stripped(self) -> None:
        sender = self._sender("https://sync.example.internal/")
        event = make_event(OP_DELETED, "z.txt", timestamp="2026-09-03T12:00:00Z")
        sender.send(event)
        self.assertEqual(self.transport.calls[0][0], "https://sync.example.internal/sync/delete")


if __name__ == "__main__":
    unittest.main()
