"""
test_m10.py — Module 10: Frontend Dashboard.

Covers:
- Static file serving at /dashboard/
- Dashboard HTML/CSS/JS presence and basic structure
- Backend API contract preservation
- Forbidden direct AWS/RDS access in dashboard code
- Auth handling behavior
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("SYNC_FOLDER", ".")


def test_dashboard_index_served() -> None:
    from backend.main import create_app

    app = create_app()
    client = TestClient(app)
    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "").lower()
    assert b"Hybrid Cloud Sync Dashboard" in response.content


def test_dashboard_static_assets_served() -> None:
    from backend.main import create_app

    app = create_app()
    client = TestClient(app)

    css = client.get("/dashboard/styles.css")
    assert css.status_code == 200
    assert "text/css" in css.headers.get("content-type", "").lower()

    js = client.get("/dashboard/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers.get("content-type", "").lower()


def test_dashboard_html_structure() -> None:
    from backend.main import create_app

    app = create_app()
    client = TestClient(app)
    response = client.get("/dashboard/")
    body = response.text

    assert '<main id="main-content"' in body
    assert '<div id="auth-banner"' in body
    assert '<table id="files-table"' in body
    assert '<table id="logs-table"' in body
    assert '<table id="changes-table"' in body
    assert '<dialog id="versions-modal"' in body
    assert 'src="/dashboard/app.js"' in body
    assert 'href="/dashboard/styles.css"' in body


def test_dashboard_js_does_not_reference_direct_aws_or_rds() -> None:
    js_path = _PROJECT_ROOT / "dashboard" / "app.js"
    content = js_path.read_text(encoding="utf-8")

    forbidden = [
        "boto3",
        "require('aws-sdk')",
        "require('aws_sdk')",
        "new AWS.",
        "s3client",
        "s3.create",
        "cloudwatch",
        "sns.publish",
        "new RDS",
        "require('pg')",
        "require('mysql')",
        "psycopg2",
        "mysql2",
    ]

    lowered = content.lower()
    for term in forbidden:
        assert term not in lowered, f"Dashboard JS references forbidden term: {term}"


def test_dashboard_html_does_not_reference_direct_aws_or_rds() -> None:
    html_path = _PROJECT_ROOT / "dashboard" / "index.html"
    content = html_path.read_text(encoding="utf-8").lower()

    forbidden = [
        "boto3",
        "aws-sdk",
        "aws sdk",
        "rds_host",
        "rds_password",
        "s3_bucket",
    ]

    for term in forbidden:
        assert term not in content, f"Dashboard HTML references forbidden term: {term}"


def test_dashboard_api_key_header_sent() -> None:
    from backend.main import create_app
    from backend import config

    original_key = getattr(config, "API_KEY", "")
    original_env = getattr(config, "APP_ENV", "development")

    try:
        config.API_KEY = "test-dashboard-key"
        config.APP_ENV = "production"

        app = create_app()
        client = TestClient(app)

        health_response = client.get("/health")
        assert health_response.status_code == 200

        files_response = client.get("/files", headers={"X-API-Key": "test-dashboard-key"})
        assert files_response.status_code == 200

        bad_response = client.get("/files", headers={"X-API-Key": "wrong-key"})
        assert bad_response.status_code == 401
    finally:
        config.API_KEY = original_key
        config.APP_ENV = original_env


def test_existing_api_contracts_preserved() -> None:
    from backend.main import create_app

    app = create_app()
    client = TestClient(app)

    expected_routes = [
        ("/health", "get", 200),
        ("/status", "get", 200),
        ("/files", "get", 200),
    ]

    for route, method, expected_status in expected_routes:
        if method == "get":
            response = client.get(route)
        else:
            response = client.post(route)

        assert response.status_code == expected_status, (
            f"Route {method.upper()} {route} returned {response.status_code}, expected {expected_status}"
        )
