"""
test_m8.py — Module 8: versioning and conflict handling.

No AWS credentials required. Uses in-memory storage/metadata adapters.
Covers all 14 required M8 test points.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("SYNC_FOLDER", tempfile.mkdtemp())

from agent.conflict import conflict_relative_path, is_conflict_copy_path, copy_local_to_conflict  # noqa: E402
from agent.poller import CloudPoller  # noqa: E402
from agent.state import SyncState  # noqa: E402
from agent.http_sender import HttpEventSender  # noqa: E402
from backend.main import create_app  # noqa: E402


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _upload(client: TestClient, path: str, content: bytes, operation: str, timestamp: str, base_hash=None):
    data = {
        "operation": operation,
        "path": path,
        "timestamp": timestamp,
        "hash": _sha(content),
        "size": str(len(content)),
    }
    if base_hash:
        data["base_hash"] = base_hash
    return client.post(
        "/sync/upload",
        data=data,
        files={"file": (Path(path).name, content, "application/octet-stream")},
    )


# 1. New file creation still works.
def test_01_new_file_creation_still_works(client):
    content = b"hello m8"
    response = _upload(client, "new.txt", content, "CREATED", "2026-09-04T10:00:00Z")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["idempotent"] is False
    assert body["conflict"] is False
    assert body["file"]["current_version"] == 1
    assert body["file"]["current_hash"] == _sha(content)


# 2. Existing file modification creates a new version.
def test_02_existing_file_modification_creates_new_version(client):
    v1, v2 = b"version-one", b"version-two"
    first = _upload(client, "doc.txt", v1, "CREATED", "2026-09-04T10:00:00Z")
    file_id = first.json()["file"]["id"]
    second = _upload(
        client,
        "doc.txt",
        v2,
        "MODIFIED",
        "2026-09-04T10:01:00Z",
        base_hash=_sha(v1),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["file"]["id"] == file_id
    assert body["file"]["current_version"] == 2
    assert body["file"]["current_hash"] == _sha(v2)
    assert body["conflict"] is False


# 3. Previous version remains available.
def test_03_previous_version_remains_available(client):
    v1, v2 = b"version-one", b"version-two"
    first = _upload(client, "avail.txt", v1, "CREATED", "2026-09-04T10:00:00Z")
    file_id = first.json()["file"]["id"]
    _upload(
        client,
        "avail.txt",
        v2,
        "MODIFIED",
        "2026-09-04T10:01:00Z",
        base_hash=_sha(v1),
    )
    current = client.get(f"/files/{file_id}/content")
    assert current.status_code == 200
    assert current.content == v2
    previous = client.get(f"/files/{file_id}/content", params={"version": 1})
    assert previous.status_code == 200
    assert previous.content == v1


# 4. Version history endpoint works.
def test_04_version_history_endpoint_works(client):
    v1, v2 = b"data-1", b"data-2"
    first = _upload(client, "hist.txt", v1, "CREATED", "2026-09-04T10:00:00Z")
    file_id = first.json()["file"]["id"]
    _upload(client, "hist.txt", v2, "MODIFIED", "2026-09-04T10:01:00Z", base_hash=_sha(v1))

    response = client.get(f"/files/{file_id}/versions")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["count"] == 2
    assert len(data["versions"]) == 2


# 5. Version hashes/metadata persist correctly.
def test_05_version_hashes_and_metadata_persist_correctly(client):
    v1, v2 = b"first", b"second"
    first = _upload(client, "meta.txt", v1, "CREATED", "2026-09-04T10:00:00Z")
    file_id = first.json()["file"]["id"]
    _upload(client, "meta.txt", v2, "MODIFIED", "2026-09-04T10:01:00Z", base_hash=_sha(v1))

    history = client.get(f"/files/{file_id}/versions").json()
    assert history["versions"][0]["hash"] == _sha(v1)
    assert history["versions"][1]["hash"] == _sha(v2)
    assert history["versions"][0]["operation"] == "CREATED"
    assert history["versions"][1]["operation"] == "MODIFIED"
    assert history["versions"][0]["source"] == "local"
    assert history["versions"][1]["source"] == "local"
    assert history["versions"][0]["storage_version_id"]
    assert history["versions"][1]["storage_version_id"]
    assert history["versions"][0]["created_at"] == "2026-09-04T10:00:00Z"
    assert history["versions"][1]["created_at"] == "2026-09-04T10:01:00Z"
    assert history["versions"][0]["is_conflict"] is False
    assert history["versions"][1]["is_conflict"] is False


# 6. Multiple sequential modifications create multiple versions.
def test_06_multiple_sequential_modifications_create_multiple_versions(client):
    v1, v2, v3, v4 = b"seq-1", b"seq-2", b"seq-3", b"seq-4"
    created = _upload(client, "multi.txt", v1, "CREATED", "2026-09-04T11:00:00Z")
    file_id = created.json()["file"]["id"]
    _upload(client, "multi.txt", v2, "MODIFIED", "2026-09-04T11:01:00Z", base_hash=_sha(v1))
    _upload(client, "multi.txt", v3, "MODIFIED", "2026-09-04T11:02:00Z", base_hash=_sha(v2))
    _upload(client, "multi.txt", v4, "MODIFIED", "2026-09-04T11:03:00Z", base_hash=_sha(v3))

    history = client.get(f"/files/{file_id}/versions").json()
    assert history["count"] == 4
    numbers = [item["version_number"] for item in history["versions"]]
    assert numbers == [1, 2, 3, 4]
    hashes = [item["hash"] for item in history["versions"]]
    assert hashes == [_sha(v1), _sha(v2), _sha(v3), _sha(v4)]

    files = client.get("/files").json()["files"]
    match = next(f for f in files if f["id"] == file_id)
    assert match["current_version"] == 4
    assert match["current_hash"] == _sha(v4)


# 7. M7 bidirectional synchronization remains functional.
def test_07_m7_bidirectional_synchronization_remains_functional(tmp_path):
    content = b"already-here"
    local = tmp_path / "m7_sync.txt"
    local.write_bytes(content)
    state = SyncState(str(tmp_path))
    digest = _sha(content)
    state.update_file_state("m7_sync.txt", digest)

    class MockSender(HttpEventSender):
        def __init__(self):
            super().__init__("http://dummy", str(tmp_path))
            self.changes = [
                {
                    "operation": "MODIFIED",
                    "path": "m7_sync.txt",
                    "hash": digest,
                    "file_id": 3,
                    "timestamp": "2026-09-04T16:01:00Z",
                }
            ]
            self.downloaded = False

        def get_changes(self, since=None):
            return self.changes

        def download_file(self, file_id):
            self.downloaded = True
            return b"should-not-download"

    sender = MockSender()
    CloudPoller(sender, str(tmp_path), interval=1)._poll()
    assert local.read_bytes() == content
    assert sender.downloaded is False


# 8. Genuine conflicts are detected.
def test_08_genuine_conflicts_are_detected(client):
    base, local_a, cloud_b = b"shared-base", b"local-divergent", b"cloud-divergent"
    _upload(client, "detect_conflict.txt", base, "CREATED", "2026-09-04T13:00:00Z")
    _upload(
        client,
        "detect_conflict.txt",
        cloud_b,
        "MODIFIED",
        "2026-09-04T13:01:00Z",
        base_hash=_sha(base),
    )
    conflict = _upload(
        client,
        "detect_conflict.txt",
        local_a,
        "MODIFIED",
        "2026-09-04T13:02:00Z",
        base_hash=_sha(base),
    )
    assert conflict.status_code == 200
    body = conflict.json()
    assert body["conflict"] is True
    assert body["idempotent"] is False
    assert body["conflict_path"] == conflict_relative_path("detect_conflict.txt", _sha(local_a))


# 9. Conflicts never silently overwrite either version.
def test_09_conflicts_never_silently_overwrite_either_version(client):
    base, local_a, cloud_b = b"base-v", b"local-val", b"cloud-val"
    created = _upload(client, "no_overwrite.txt", base, "CREATED", "2026-09-04T13:00:00Z")
    file_id = created.json()["file"]["id"]
    _upload(
        client,
        "no_overwrite.txt",
        cloud_b,
        "MODIFIED",
        "2026-09-04T13:01:00Z",
        base_hash=_sha(base),
    )
    conflict = _upload(
        client,
        "no_overwrite.txt",
        local_a,
        "MODIFIED",
        "2026-09-04T13:02:00Z",
        base_hash=_sha(base),
    )
    body = conflict.json()
    conflict_path = body["conflict_path"]

    # Cloud original is NOT overwritten by local edit
    orig_content = client.get(f"/files/{file_id}/content").content
    assert orig_content == cloud_b

    # Local edit is NOT lost; preserved under conflict path
    files = {f["relative_path"]: f for f in client.get("/files").json()["files"]}
    conflict_id = files[conflict_path]["id"]
    conflict_content = client.get(f"/files/{conflict_id}/content").content
    assert conflict_content == local_a


# 10. Both conflicting versions remain preserved.
def test_10_both_conflicting_versions_remain_preserved(client):
    base, local_a, cloud_b = b"base", b"local", b"cloud"
    created = _upload(client, "preserve.txt", base, "CREATED", "2026-09-04T13:00:00Z")
    file_id = created.json()["file"]["id"]
    _upload(client, "preserve.txt", cloud_b, "MODIFIED", "2026-09-04T13:01:00Z", base_hash=_sha(base))
    conflict_resp = _upload(client, "preserve.txt", local_a, "MODIFIED", "2026-09-04T13:02:00Z", base_hash=_sha(base))
    conflict_path = conflict_resp.json()["conflict_path"]

    files = {f["relative_path"]: f for f in client.get("/files").json()["files"]}
    assert "preserve.txt" in files
    assert conflict_path in files
    assert files["preserve.txt"]["current_hash"] == _sha(cloud_b)
    assert files[conflict_path]["current_hash"] == _sha(local_a)


# 11. Conflict information persists.
def test_11_conflict_information_persists(client):
    base, local_a, cloud_b = b"base", b"local", b"cloud"
    created = _upload(client, "persist_conflict.txt", base, "CREATED", "2026-09-04T13:00:00Z")
    file_id = created.json()["file"]["id"]
    _upload(client, "persist_conflict.txt", cloud_b, "MODIFIED", "2026-09-04T13:01:00Z", base_hash=_sha(base))
    conflict_resp = _upload(client, "persist_conflict.txt", local_a, "MODIFIED", "2026-09-04T13:02:00Z", base_hash=_sha(base))
    conflict_path = conflict_resp.json()["conflict_path"]

    # Canonical file is marked status="conflict"
    files = {f["relative_path"]: f for f in client.get("/files").json()["files"]}
    assert files["persist_conflict.txt"]["status"] == "conflict"

    # Conflict copy has operation="CONFLICT" and is_conflict=True
    conflict_id = files[conflict_path]["id"]
    conflict_versions = client.get(f"/files/{conflict_id}/versions").json()["versions"]
    assert len(conflict_versions) == 1
    assert conflict_versions[0]["operation"] == "CONFLICT"
    assert conflict_versions[0]["is_conflict"] is True

    # Status response includes conflict_count
    status = client.get("/status").json()
    assert status["conflict_count"] >= 1


# 12. Conflict events are logged.
def test_12_conflict_events_are_logged(client):
    base, local_a, cloud_b = b"base", b"local", b"cloud"
    _upload(client, "logged_conflict.txt", base, "CREATED", "2026-09-04T13:00:00Z")
    _upload(client, "logged_conflict.txt", cloud_b, "MODIFIED", "2026-09-04T13:01:00Z", base_hash=_sha(base))
    conflict_resp = _upload(client, "logged_conflict.txt", local_a, "MODIFIED", "2026-09-04T13:02:00Z", base_hash=_sha(base))
    conflict_path = conflict_resp.json()["conflict_path"]

    logs = client.get("/logs").json()["logs"]
    conflict_logs = [log for log in logs if log["operation"] == "CONFLICT"]
    assert len(conflict_logs) >= 2
    assert any(log["path"] == "logged_conflict.txt" for log in conflict_logs)
    assert any(log["path"] == conflict_path for log in conflict_logs)
    assert any(conflict_path in (log.get("error_message") or "") for log in conflict_logs)


# 13. Repeated/retried operations are idempotent.
def test_13_repeated_retried_operations_are_idempotent(client):
    # 13a: Normal upload idempotent retry
    content = b"same-bytes"
    _upload(client, "idemp.txt", content, "CREATED", "2026-09-04T12:00:00Z")
    again = _upload(client, "idemp.txt", content, "MODIFIED", "2026-09-04T12:01:00Z")
    assert again.json()["idempotent"] is True
    file_id = again.json()["file"]["id"]
    history = client.get(f"/files/{file_id}/versions").json()
    assert history["count"] == 1

    # 13b: Conflict upload idempotent retry
    base, local_a, cloud_b = b"base", b"local-a", b"cloud-b"
    _upload(client, "dup.txt", base, "CREATED", "2026-09-04T14:00:00Z")
    _upload(client, "dup.txt", cloud_b, "MODIFIED", "2026-09-04T14:01:00Z", base_hash=_sha(base))
    first = _upload(client, "dup.txt", local_a, "MODIFIED", "2026-09-04T14:02:00Z", base_hash=_sha(base))
    second = _upload(client, "dup.txt", local_a, "MODIFIED", "2026-09-04T14:03:00Z", base_hash=_sha(base))
    assert first.json()["conflict"] is True
    assert second.json()["conflict"] is True
    assert second.json()["idempotent"] is True
    assert first.json()["conflict_path"] == second.json()["conflict_path"]

    files = [f for f in client.get("/files").json()["files"] if not f["deleted"]]
    conflict_files = [f for f in files if is_conflict_copy_path(f["relative_path"])]
    assert len(conflict_files) == 1
    cid = conflict_files[0]["id"]
    assert client.get(f"/files/{cid}/versions").json()["count"] == 1


# 14. No synchronization loops are introduced.
def test_14_no_synchronization_loops_are_introduced(client, tmp_path):
    content = b"loop-check"
    uploaded = _upload(client, "loop.txt", content, "CREATED", "2026-09-04T17:00:00Z")
    file_id = uploaded.json()["file"]["id"]
    (tmp_path / "loop.txt").write_bytes(content)

    class ApiSender(HttpEventSender):
        def __init__(self):
            super().__init__("http://dummy", str(tmp_path))

        def get_changes(self, since=None):
            return client.get("/sync/changes").json()["changes"]

        def download_file(self, fid):
            return client.get(f"/files/{fid}/content").content

    poller = CloudPoller(ApiSender(), str(tmp_path), interval=1)
    poller._poll()
    poller._poll()

    assert client.get(f"/files/{file_id}/versions").json()["count"] == 1
    assert (tmp_path / "loop.txt").read_bytes() == content
    retry = _upload(client, "loop.txt", content, "MODIFIED", "2026-09-04T17:02:00Z")
    assert retry.json()["idempotent"] is True
    assert client.get(f"/files/{file_id}/versions").json()["count"] == 1


# Additional tests: Backward compatibility & poller conflict
def test_without_base_hash_sequential_local_edit_is_not_a_conflict(client):
    """M7-compatible path: omitted base_hash remains a normal new version."""
    v1, v2 = b"one", b"two"
    created = _upload(client, "compat.txt", v1, "CREATED", "2026-09-04T15:00:00Z")
    file_id = created.json()["file"]["id"]
    modified = _upload(client, "compat.txt", v2, "MODIFIED", "2026-09-04T15:01:00Z")
    assert modified.json()["conflict"] is False
    assert modified.json()["file"]["current_version"] == 2
    assert client.get(f"/files/{file_id}/content").content == v2


def test_poller_conflict_does_not_overwrite_local_bytes(tmp_path):
    base = b"base-bytes"
    local = b"local-divergent"
    cloud = b"cloud-divergent"
    path = tmp_path / "both.txt"
    path.write_bytes(local)

    state = SyncState(str(tmp_path))
    state.update_file_state("both.txt", _sha(base), deleted=False)

    class MockSender(HttpEventSender):
        def __init__(self):
            super().__init__("http://dummy", str(tmp_path))
            self.changes = [
                {
                    "operation": "MODIFIED",
                    "path": "both.txt",
                    "hash": _sha(cloud),
                    "file_id": 9,
                    "timestamp": "2026-09-04T16:00:00Z",
                }
            ]
            self.downloads = {9: cloud}

        def get_changes(self, since=None):
            return self.changes

        def download_file(self, file_id):
            return self.downloads.get(file_id)

    poller = CloudPoller(MockSender(), str(tmp_path), interval=1)
    poller._poll()

    assert path.read_bytes() == cloud
    conflict_rel = conflict_relative_path("both.txt", _sha(local))
    conflict_file = tmp_path / conflict_rel.replace("/", os.sep)
    assert conflict_file.exists()
    assert conflict_file.read_bytes() == local
    assert poller.state.get_file_hash("both.txt") == _sha(cloud)
    assert poller.state.get_file_hash(conflict_rel) == _sha(local)


def test_conflict_helpers():
    rel = conflict_relative_path("docs/sub/report.pdf", "a1b2c3d4e5f67890")
    assert rel == "docs/sub/report.conflict-a1b2c3d4e5f6.pdf"
    assert is_conflict_copy_path(rel) is True
    assert is_conflict_copy_path("docs/sub/report.pdf") is False
