"""
test_m9.py — Module 9: monitoring, logging, and alerting.

No live CloudWatch or SNS calls. AWS clients are mocked.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("SYNC_FOLDER", tempfile.mkdtemp())

from backend import config  # noqa: E402
from backend.adapters.repository import MemoryMetadataRepository  # noqa: E402
from backend.adapters.storage import MemoryFileStorage  # noqa: E402
from backend.main import create_app  # noqa: E402
from backend.services.observability import (  # noqa: E402
    ALERT_CRITICAL_APPLICATION_ERROR,
    ALERT_REPEATED_AUTH_FAILURES,
    ALERT_REPEATED_SYNC_FAILURES,
    METRIC_CONFLICT_EVENTS,
    METRIC_SYNC_FAILURE,
    METRIC_SYNC_SUCCESS,
    CloudWatchMetrics,
    Observability,
    SnsAlerter,
    StructuredLogger,
    sanitize_record,
)


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class RecordingCloudWatch:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_metric_data(self, **kwargs):
        self.calls.append(kwargs)
        return {}


class ExplodingCloudWatch:
    def put_metric_data(self, **kwargs):
        raise RuntimeError("cloudwatch throttled")


class RecordingSNS:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": "test-message-id"}


class ExplodingSNS:
    def publish(self, **kwargs):
        raise RuntimeError("sns unavailable")


class ExplodingStorage(MemoryFileStorage):
    def put(self, key: str, content: bytes):
        raise RuntimeError("storage exploded")


class ExplodingLogRepository(MemoryMetadataRepository):
    def add_log(self, **kwargs):
        raise RuntimeError("rds logs unavailable")


def _observability(
    *,
    cloudwatch=None,
    sns=None,
    sync_threshold: int = 3,
    auth_threshold: int = 3,
) -> Observability:
    return Observability(
        structured=StructuredLogger(),
        metrics=CloudWatchMetrics(
            region="ap-south-1",
            client=cloudwatch if cloudwatch is not None else RecordingCloudWatch(),
            enabled=True,
        ),
        alerts=SnsAlerter(
            topic_arn="arn:aws:sns:ap-south-1:123456789012:cloudaws-alerts",
            region="ap-south-1",
            client=sns if sns is not None else RecordingSNS(),
            enabled=True,
            sync_failure_threshold=sync_threshold,
            auth_failure_threshold=auth_threshold,
        ),
    )


def _client(observability=None, storage=None, repository=None) -> TestClient:
    app = create_app(
        observability=observability or _observability(),
        storage=storage,
        repository=repository,
    )
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


# 1. Health endpoint still works.
def test_01_health_endpoint_still_works():
    response = _client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "service" in body


# 2. Status endpoint still works.
def test_02_status_endpoint_still_works():
    response = _client().get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["storage_adapter"] == "memory"
    assert body["metadata_adapter"] == "memory"
    assert "file_count" in body
    assert "notes" in body
    assert "s3" in body["notes"]
    assert "rds" in body["notes"]
    assert body["notes"]["monitoring"] == "module-09"


# 3. Expected operations generate logs.
def test_03_expected_operations_generate_logs():
    obs = _observability()
    client = _client(obs)
    created = _upload(client, "ops.txt", b"created", "CREATED", "2026-09-04T20:00:00Z")
    assert created.status_code == 200
    _upload(client, "ops.txt", b"modified", "MODIFIED", "2026-09-04T20:01:00Z", base_hash=_sha(b"created"))
    client.post(
        "/sync/delete",
        json={
            "operation": "DELETED",
            "path": "ops.txt",
            "timestamp": "2026-09-04T20:02:00Z",
        },
    )

    rds_logs = client.get("/logs").json()["logs"]
    operations = {log["operation"] for log in rds_logs}
    assert "CREATED" in operations
    assert "MODIFIED" in operations
    assert "DELETED" in operations
    assert all(log["status"] == "SUCCESS" for log in rds_logs)

    events = {record["event"] for record in obs.structured.records}
    assert "file.created" in events
    assert "file.modified" in events
    assert "file.deleted" in events
    assert "sync.success" in events


# 4. Synchronization failures are logged.
def test_04_synchronization_failures_are_logged():
    obs = _observability()
    client = _client(obs)
    response = client.post(
        "/sync/upload",
        data={
            "operation": "CREATED",
            "path": "bad.txt",
            "timestamp": "2026-09-04T20:03:00Z",
            "hash": "0" * 64,
            "size": "4",
        },
        files={"file": ("bad.txt", b"data", "application/octet-stream")},
    )
    assert response.status_code == 400

    failure_logs = [log for log in client.get("/logs").json()["logs"] if log["status"] == "FAILURE"]
    assert failure_logs
    assert any(log["path"] == "bad.txt" for log in failure_logs)

    events = [record for record in obs.structured.records if record["event"] == "sync.failure"]
    assert events
    assert events[0]["success"] is False


# 5. Conflicts are logged.
def test_05_conflicts_are_logged():
    obs = _observability()
    client = _client(obs)
    base, local_a, cloud_b = b"base", b"local", b"cloud"
    _upload(client, "conflict.txt", base, "CREATED", "2026-09-04T20:04:00Z")
    _upload(client, "conflict.txt", cloud_b, "MODIFIED", "2026-09-04T20:05:00Z", base_hash=_sha(base))
    conflict = _upload(
        client,
        "conflict.txt",
        local_a,
        "MODIFIED",
        "2026-09-04T20:06:00Z",
        base_hash=_sha(base),
    )
    assert conflict.status_code == 200
    body = conflict.json()
    assert body["conflict"] is True
    conflict_path = body["conflict_path"]

    rds_logs = client.get("/logs").json()["logs"]
    conflict_logs = [log for log in rds_logs if log["operation"] == "CONFLICT"]
    assert len(conflict_logs) >= 2
    assert any(log["path"] == "conflict.txt" for log in conflict_logs)
    assert any(log["path"] == conflict_path for log in conflict_logs)

    events = {record["event"] for record in obs.structured.records}
    assert "conflict.detected" in events
    assert "conflict.logged" in events


# 6. Secrets are not present in logs.
def test_06_secrets_are_not_present_in_logs(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "super-secret-api-key-value")
    monkeypatch.setattr(config, "RDS_PASSWORD", "super-secret-db-password")
    obs = _observability()
    obs.structured.emit(
        "ERROR",
        "sync.failure",
        password="should-not-appear",
        api_key="super-secret-api-key-value",
        error="failed with super-secret-api-key-value and super-secret-db-password",
        database_url="postgresql://user:hunter2@rds.example:5432/sync",
    )
    record = obs.structured.records[-1]
    serialized = json.dumps(record)
    assert "super-secret-api-key-value" not in serialized
    assert "super-secret-db-password" not in serialized
    assert "hunter2" not in serialized
    assert record["api_key"] == "[REDACTED]"
    assert record["password"] == "[REDACTED]"
    assert record["database_url"] in {"[REDACTED]", "[REDACTED_URL]"}

    sanitized = sanitize_record({"AWS_SECRET_ACCESS_KEY": "abc", "path": "ok.txt"})
    assert sanitized["AWS_SECRET_ACCESS_KEY"] == "[REDACTED]"
    assert sanitized["path"] == "ok.txt"


# 7. CloudWatch metric emission works.
def test_07_cloudwatch_metric_emission_works():
    cw = RecordingCloudWatch()
    obs = _observability(cloudwatch=cw)
    client = _client(obs)
    response = _upload(client, "metrics.txt", b"hello", "CREATED", "2026-09-04T20:07:00Z")
    assert response.status_code == 200
    assert cw.calls
    names = [item["MetricName"] for call in cw.calls for item in call["MetricData"]]
    assert METRIC_SYNC_SUCCESS in names
    assert any(call["Namespace"] == "CloudAWSProject/Sync" for call in cw.calls)


# 8. CloudWatch failure does not break synchronization.
def test_08_cloudwatch_failure_does_not_break_synchronization():
    obs = _observability(cloudwatch=ExplodingCloudWatch())
    client = _client(obs)
    response = _upload(client, "cw-fail.txt", b"still-ok", "CREATED", "2026-09-04T20:08:00Z")
    assert response.status_code == 200
    assert response.json()["success"] is True
    files = client.get("/files").json()["files"]
    assert any(item["relative_path"] == "cw-fail.txt" for item in files)


# 9. SNS alerting is triggered for defined critical/repeated failures.
def test_09_sns_alerting_for_critical_and_repeated_failures(monkeypatch):
    sns = RecordingSNS()
    obs = _observability(sns=sns, sync_threshold=3, auth_threshold=3)
    client = _client(obs)

    for index in range(3):
        response = client.post(
            "/sync/upload",
            data={
                "operation": "CREATED",
                "path": f"fail-{index}.txt",
                "timestamp": f"2026-09-04T21:0{index}:00Z",
                "hash": "0" * 64,
                "size": "4",
            },
            files={"file": (f"fail-{index}.txt", b"data", "application/octet-stream")},
        )
        assert response.status_code == 400

    reasons = [item["reason"] for item in obs.alerts.published]
    assert ALERT_REPEATED_SYNC_FAILURES in reasons
    assert sns.calls
    assert any(ALERT_REPEATED_SYNC_FAILURES in call["Message"] for call in sns.calls)

    boom = _client(obs, storage=ExplodingStorage())
    exploded = _upload(boom, "critical.txt", b"x", "CREATED", "2026-09-04T21:10:00Z")
    assert exploded.status_code == 500
    assert any(item["reason"] == ALERT_CRITICAL_APPLICATION_ERROR for item in obs.alerts.published)

    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "API_KEY", "correct-key")
    auth_sns = RecordingSNS()
    auth_obs = _observability(sns=auth_sns, auth_threshold=3)
    auth_client = _client(auth_obs)
    for _ in range(3):
        denied = auth_client.get("/files", headers={"X-API-Key": "wrong-key"})
        assert denied.status_code == 401
    assert any(item["reason"] == ALERT_REPEATED_AUTH_FAILURES for item in auth_obs.alerts.published)


# 10. Normal successful operations do not create alert spam.
def test_10_normal_successful_operations_do_not_create_alert_spam():
    sns = RecordingSNS()
    obs = _observability(sns=sns)
    client = _client(obs)
    for index in range(5):
        response = _upload(
            client,
            f"ok-{index}.txt",
            f"payload-{index}".encode(),
            "CREATED",
            f"2026-09-04T22:0{index}:00Z",
        )
        assert response.status_code == 200
    assert obs.alerts.published == []
    assert sns.calls == []


# 11. SNS failure does not break synchronization.
def test_11_sns_failure_does_not_break_synchronization():
    obs = _observability(sns=ExplodingSNS(), sync_threshold=1)
    client = _client(obs)
    failed = client.post(
        "/sync/upload",
        data={
            "operation": "CREATED",
            "path": "sns-fail.txt",
            "timestamp": "2026-09-04T22:10:00Z",
            "hash": "0" * 64,
            "size": "4",
        },
        files={"file": ("sns-fail.txt", b"data", "application/octet-stream")},
    )
    assert failed.status_code == 400
    ok = _upload(client, "after-sns.txt", b"ok", "CREATED", "2026-09-04T22:11:00Z")
    assert ok.status_code == 200
    assert ok.json()["success"] is True


# 12. Existing M8 conflict behavior remains intact.
def test_12_m8_conflict_behavior_remains_intact():
    client = _client()
    base, local_a, cloud_b = b"base", b"local-edit", b"cloud-edit"
    created = _upload(client, "m8.txt", base, "CREATED", "2026-09-04T23:00:00Z")
    file_id = created.json()["file"]["id"]
    _upload(client, "m8.txt", cloud_b, "MODIFIED", "2026-09-04T23:01:00Z", base_hash=_sha(base))
    conflict = _upload(
        client,
        "m8.txt",
        local_a,
        "MODIFIED",
        "2026-09-04T23:02:00Z",
        base_hash=_sha(base),
    )
    body = conflict.json()
    assert body["conflict"] is True
    conflict_path = body["conflict_path"]
    assert client.get(f"/files/{file_id}/content").content == cloud_b
    files = {item["relative_path"]: item for item in client.get("/files").json()["files"]}
    assert files["m8.txt"]["status"] == "conflict"
    conflict_id = files[conflict_path]["id"]
    assert client.get(f"/files/{conflict_id}/content").content == local_a
    versions = client.get(f"/files/{conflict_id}/versions").json()["versions"]
    assert versions[0]["operation"] == "CONFLICT"
    assert versions[0]["is_conflict"] is True
    status = client.get("/status").json()
    assert status["conflict_count"] >= 1


def test_13_rds_log_failure_does_not_break_synchronization():
    obs = _observability()
    client = _client(obs, repository=ExplodingLogRepository())
    response = _upload(client, "nolog.txt", b"bytes", "CREATED", "2026-09-04T23:10:00Z")
    assert response.status_code == 200
    assert response.json()["file"]["relative_path"] == "nolog.txt"
    assert any(record["event"] == "logging.failure" for record in obs.structured.records)


def test_14_monitoring_iam_policy_is_least_privilege():
    policy_path = _PROJECT_ROOT / "infrastructure" / "iam_policies" / "ec2_monitoring_policy.json"
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    assert data["Version"] == "2012-10-17"
    actions = set()
    for statement in data["Statement"]:
        action = statement["Action"]
        if isinstance(action, list):
            actions.update(action)
        else:
            actions.add(action)
    assert "cloudwatch:PutMetricData" in actions
    assert "sns:Publish" in actions
    assert "sns:CreateTopic" not in actions
    assert not any(item.endswith(":*") for item in actions)
