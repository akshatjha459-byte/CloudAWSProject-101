"""
test_m6.py — Unit tests for Module 6: AWS IAM / Security.

Tests:
1. IAM policy JSON files validation (syntax, valid version, expected statements).
2. API Key authentication middleware enforcement on backend routes.
3. HttpEventSender header propagation when API_KEY is set.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.events import SyncEvent
from agent.http_sender import HttpEventSender
from backend import config
from backend.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def test_iam_s3_policy_json_validity() -> None:
    policy_path = REPO_ROOT / "infrastructure" / "iam_policies" / "ec2_s3_policy.json"
    assert policy_path.is_file(), "ec2_s3_policy.json must exist"

    data = json.loads(policy_path.read_text(encoding="utf-8"))
    assert data.get("Version") == "2012-10-17"
    statements = data.get("Statement", [])
    assert len(statements) >= 2

    actions = set()
    for stmt in statements:
        assert stmt.get("Effect") == "Allow"
        actions.update(stmt.get("Action", []))

    assert "s3:GetObject" in actions
    assert "s3:PutObject" in actions
    assert "s3:DeleteObject" in actions
    assert "s3:ListBucket" in actions


def test_iam_trust_policy_json_validity() -> None:
    policy_path = REPO_ROOT / "infrastructure" / "iam_policies" / "trust_policy_ec2.json"
    assert policy_path.is_file(), "trust_policy_ec2.json must exist"

    data = json.loads(policy_path.read_text(encoding="utf-8"))
    assert data.get("Version") == "2012-10-17"
    statements = data.get("Statement", [])
    assert len(statements) >= 1
    assert statements[0]["Principal"]["Service"] == "ec2.amazonaws.com"
    assert statements[0]["Action"] == "sts:AssumeRole"


def test_api_key_authentication_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "API_KEY", "secret-test-key")
    client = TestClient(app)

    # Health endpoint remains public
    res_health = client.get("/health")
    assert res_health.status_code == 200

    # Protected endpoint without key returns 401
    res_unauth = client.get("/files")
    assert res_unauth.status_code == 401
    assert res_unauth.json()["detail"]["error"] == "unauthorized"

    # Protected endpoint with invalid key returns 401
    res_bad = client.get("/files", headers={"X-API-Key": "wrong-key"})
    assert res_bad.status_code == 401

    # Protected endpoint with valid key returns 200
    res_ok = client.get("/files", headers={"X-API-Key": "secret-test-key"})
    assert res_ok.status_code == 200


def test_agent_http_sender_header_propagation() -> None:
    captured_headers: dict[str, str] = {}

    def fake_post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
        nonlocal captured_headers
        captured_headers = headers
        return 200, b'{"success": true}'

    sender = HttpEventSender(
        backend_url="http://testbackend:8000",
        sync_folder="organization/files",
        api_key="my-api-key",
        http_post=fake_post,
    )
    event = SyncEvent(operation="DELETED", path="test.txt", hash=None, size=None, timestamp="2026-09-03T10:00:00Z")

    sender.send(event)

    assert sender.last_status == 200
    assert captured_headers.get("X-API-Key") == "my-api-key"
