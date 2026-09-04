import os
import json
import hashlib
import pytest
from pathlib import Path

from agent.state import SyncState
from agent.poller import CloudPoller
from agent.http_sender import HttpEventSender

class MockSender(HttpEventSender):
    def __init__(self):
        super().__init__("http://dummy", "/dummy")
        self.changes = []
        self.downloads = {}

    def get_changes(self, since=None):
        return self.changes
        
    def download_file(self, file_id, version_number=None):
        return self.downloads.get(file_id)

def test_sync_state_persistence(tmp_path):
    state = SyncState(str(tmp_path))
    assert state.get_last_sync_timestamp() is None
    
    state.set_last_sync_timestamp("2026-09-04T00:00:00Z")
    state.update_file_state("test.txt", "hash123")
    
    state2 = SyncState(str(tmp_path))
    assert state2.get_last_sync_timestamp() == "2026-09-04T00:00:00Z"
    assert state2.get_file_hash("test.txt") == "hash123"

def test_poller_downloads_new_file(tmp_path):
    sender = MockSender()
    sender.changes = [
        {
            "operation": "CREATED",
            "path": "new.txt",
            "file_hash": "hash123",
            "file_id": 1,
            "timestamp": "2026-09-04T00:00:00Z"
        }
    ]
    sender.downloads[1] = b"cloud content"
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    local_file = tmp_path / "new.txt"
    assert local_file.exists()
    assert local_file.read_bytes() == b"cloud content"
    
    state = SyncState(str(tmp_path))
    assert state.get_file_hash("new.txt") == "hash123"
    assert state.get_last_sync_timestamp() == "2026-09-04T00:00:00Z"

def test_poller_deletes_local_file(tmp_path):
    sender = MockSender()
    sender.changes = [
        {
            "operation": "DELETED",
            "path": "del.txt",
            "timestamp": "2026-09-04T00:00:01Z"
        }
    ]
    
    local_file = tmp_path / "del.txt"
    local_file.write_bytes(b"content")
    
    state = SyncState(str(tmp_path))
    state.update_file_state("del.txt", "hash")
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    assert not local_file.exists()
    assert poller.state.get_file_hash("del.txt") is None

def test_poller_skips_if_hash_matches(tmp_path):
    sender = MockSender()
    sender.changes = [
        {
            "operation": "MODIFIED",
            "path": "same.txt",
            "file_hash": "hash123",
            "file_id": 2,
            "timestamp": "2026-09-04T00:00:02Z"
        }
    ]
    sender.downloads[2] = b"should not download"
    
    local_file = tmp_path / "same.txt"
    local_file.write_bytes(b"local content")
    
    state = SyncState(str(tmp_path))
    state.update_file_state("same.txt", "hash123")
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    # Content should not be overwritten
    assert local_file.read_bytes() == b"local content"

def test_poller_stops_batch_on_failure_and_retries(tmp_path):
    sender = MockSender()
    sender.changes = [
        {"operation": "CREATED", "path": "A.txt", "file_hash": "hashA", "file_id": 1, "timestamp": "2026-09-04T00:00:01Z"},
        {"operation": "CREATED", "path": "B.txt", "file_hash": "hashB", "file_id": 2, "timestamp": "2026-09-04T00:00:02Z"},
        {"operation": "CREATED", "path": "C.txt", "file_hash": "hashC", "file_id": 3, "timestamp": "2026-09-04T00:00:03Z"},
    ]
    sender.downloads[1] = b"A"
    sender.downloads[3] = b"C"
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    assert (tmp_path / "A.txt").exists()
    assert not (tmp_path / "B.txt").exists()
    assert not (tmp_path / "C.txt").exists()
    assert poller.state.get_last_sync_timestamp() == "2026-09-04T00:00:01Z"
    
    sender.downloads[2] = b"B"
    sender.changes = [c for c in sender.changes if c["timestamp"] > poller.state.get_last_sync_timestamp()]
    
    poller._poll()
    
    assert (tmp_path / "B.txt").exists()
    assert (tmp_path / "C.txt").exists()
    assert poller.state.get_last_sync_timestamp() == "2026-09-04T00:00:03Z"

def test_identical_timestamps_failure(tmp_path):
    sender = MockSender()
    sender.changes = [
        {"operation": "CREATED", "path": "A.txt", "file_hash": "hashA", "file_id": 1, "timestamp": "2026-09-04T00:00:01Z"},
        {"operation": "CREATED", "path": "B.txt", "file_hash": "hashB", "file_id": 2, "timestamp": "2026-09-04T00:00:01Z"},
    ]
    sender.downloads[1] = b"A"
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    assert (tmp_path / "A.txt").exists()
    assert poller.state.get_last_sync_timestamp() is None
    
    sender.downloads[2] = b"B"
    poller._poll()
    
    assert (tmp_path / "B.txt").exists()
    assert poller.state.get_last_sync_timestamp() == "2026-09-04T00:00:01Z"

def test_move_operation_idempotency_and_failure(tmp_path):
    sender = MockSender()
    sender.changes = [
        {"operation": "MOVED", "path": "A.txt", "dest_path": "B.txt", "file_hash": "hash", "file_id": 1, "timestamp": "2026-09-04T00:00:01Z"}
    ]
    (tmp_path / "A.txt").write_bytes(b"content")
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    assert not (tmp_path / "A.txt").exists()
    assert (tmp_path / "B.txt").exists()
    
    poller._poll()
    assert (tmp_path / "B.txt").exists()
    
def test_deleted_operation_idempotency(tmp_path):
    sender = MockSender()
    sender.changes = [
        {"operation": "DELETED", "path": "A.txt", "timestamp": "2026-09-04T00:00:01Z"}
    ]
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    assert poller.state.get_last_sync_timestamp() == "2026-09-04T00:00:01Z"
    
def test_move_overwrite_incorrect_dest(tmp_path):
    sender = MockSender()
    sender.changes = [
        {"operation": "MOVED", "path": "A.txt", "dest_path": "B.txt", "file_hash": "expected_hash", "file_id": 1, "timestamp": "2026-09-04T00:00:01Z"}
    ]
    
    (tmp_path / "A.txt").write_bytes(b"correct content")
    from agent.hashing import sha256_file
    expected = sha256_file(str(tmp_path / "A.txt"))
    sender.changes[0]["file_hash"] = expected
    
    (tmp_path / "B.txt").write_bytes(b"wrong content")
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    assert not (tmp_path / "A.txt").exists()
    assert (tmp_path / "B.txt").read_bytes() == b"correct content"

def test_agent_restart_after_partial_processing(tmp_path):
    sender = MockSender()
    sender.changes = [
        {"operation": "CREATED", "path": "A.txt", "file_hash": "hashA", "file_id": 1, "timestamp": "2026-09-04T00:00:01Z"},
    ]
    sender.downloads[1] = b"A"
    
    # Simulate a crash right after write by modifying the file but not the state
    (tmp_path / "A.txt").write_bytes(b"A")
    # State has no knowledge of A.txt or timestamp
    
    poller = CloudPoller(sender, str(tmp_path), interval=1)
    poller._poll()
    
    # It should re-download and succeed, and update state
    assert (tmp_path / "A.txt").read_bytes() == b"A"
    assert poller.state.get_last_sync_timestamp() == "2026-09-04T00:00:01Z"
    assert poller.state.get_file_hash("A.txt") == "hashA"


def test_historical_created_replay_after_delete(tmp_path):
    from backend.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    content = b"hello there, this is the demo for r.txt"
    file_hash = hashlib.sha256(content).hexdigest()

    upload = client.post(
        "/sync/upload",
        data={
            "operation": "CREATED",
            "path": "r.txt",
            "timestamp": "2026-09-04T21:50:00Z",
            "hash": file_hash,
            "size": str(len(content)),
        },
        files={"file": ("r.txt", content, "application/octet-stream")},
    )
    assert upload.status_code == 200
    file_id = upload.json()["file"]["id"]

    client.post(
        "/sync/delete",
        json={
            "operation": "DELETED",
            "path": "r.txt",
            "hash": file_hash,
            "size": str(len(content)),
            "timestamp": "2026-09-04T21:51:00Z",
        },
    )

    class ApiSender(HttpEventSender):
        def __init__(self):
            super().__init__("http://dummy", str(tmp_path))

        def get_changes(self, since=None):
            return client.get("/sync/changes").json()["changes"]

        def download_file(self, file_id, version_number=None):
            params = {"version": version_number} if version_number is not None else {}
            resp = client.get(f"/files/{file_id}/content", params=params)
            if resp.status_code == 200:
                return resp.content
            return None

    poller = CloudPoller(ApiSender(), str(tmp_path), interval=1)
    poller._poll()

    assert poller.state.get_last_sync_timestamp() == "2026-09-04T21:51:00Z"
    downloaded = client.get(f"/files/{file_id}/content", params={"version": 1}).content
    assert downloaded == content


def test_historical_version_replay_after_delete(tmp_path):
    from backend.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    v1 = b"version-one"
    v2 = b"version-two"
    h1 = hashlib.sha256(v1).hexdigest()
    h2 = hashlib.sha256(v2).hexdigest()

    first = client.post(
        "/sync/upload",
        data={
            "operation": "CREATED",
            "path": "doc.txt",
            "timestamp": "2026-09-04T21:00:00Z",
            "hash": h1,
            "size": str(len(v1)),
        },
        files={"file": ("doc.txt", v1, "application/octet-stream")},
    )
    assert first.status_code == 200
    file_id = first.json()["file"]["id"]

    client.post(
        "/sync/upload",
        data={
            "operation": "MODIFIED",
            "path": "doc.txt",
            "timestamp": "2026-09-04T21:01:00Z",
            "hash": h2,
            "size": str(len(v2)),
            "base_hash": h1,
        },
        files={"file": ("doc.txt", v2, "application/octet-stream")},
    )

    client.post(
        "/sync/delete",
        json={
            "operation": "DELETED",
            "path": "doc.txt",
            "hash": h2,
            "size": str(len(v2)),
            "timestamp": "2026-09-04T21:02:00Z",
        },
    )

    class ApiSender(HttpEventSender):
        def __init__(self):
            super().__init__("http://dummy", str(tmp_path))

        def get_changes(self, since=None):
            return client.get("/sync/changes").json()["changes"]

        def download_file(self, file_id, version_number=None):
            params = {"version": version_number} if version_number is not None else {}
            resp = client.get(f"/files/{file_id}/content", params=params)
            if resp.status_code == 200:
                return resp.content
            return None

    poller = CloudPoller(ApiSender(), str(tmp_path), interval=1)
    poller._poll()

    assert poller.state.get_last_sync_timestamp() == "2026-09-04T21:02:00Z"

    v1_download = client.get(f"/files/{file_id}/content", params={"version": 1}).content
    assert v1_download == v1

    v2_download = client.get(f"/files/{file_id}/content", params={"version": 2}).content
    assert v2_download == v2
