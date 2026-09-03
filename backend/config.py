"""
config.py — Module 3: Backend configuration.

Reads settings from environment variables and an optional project-root .env
file.  AWS credentials are never loaded here; boto3 uses the default chain
when STORAGE_ADAPTER=s3.  RDS passwords come only from the environment.

Module 6 — Security:
  API_KEY controls request authentication on protected endpoints.
  APP_ENV distinguishes deployment from local development.

  APP_ENV=development  → authentication is OFF by default (safe for local dev/testing).
  APP_ENV=production   → API_KEY MUST be set; the application refuses to start
                         unprotected.  See modules/module-06/README.md for
                         the full deployment checklist.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> None:
    """Load KEY=VALUE pairs from *dotenv_path* into os.environ.

    Existing environment variables take precedence over the file.
    """
    if not dotenv_path.is_file():
        return
    with dotenv_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(_PROJECT_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

BACKEND_HOST: str = _env("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT: int = int(_env("BACKEND_PORT", "8000") or "8000")
LOG_LEVEL: str = _env("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Storage adapters
# ---------------------------------------------------------------------------

# Default remains "memory" so M3 tests and local development need no AWS.
# Set STORAGE_ADAPTER=s3 to use Module 4 Amazon S3 storage.
# Set METADATA_ADAPTER=rds to use Module 5 Amazon RDS metadata.
STORAGE_ADAPTER: str = _env("STORAGE_ADAPTER", "memory")
METADATA_ADAPTER: str = _env("METADATA_ADAPTER", "memory")

# ---------------------------------------------------------------------------
# Module 4 — Amazon S3
# ---------------------------------------------------------------------------

# Credentials come from the default AWS chain (env vars, shared config, or
# EC2 instance role).  Never hardcode AWS_ACCESS_KEY_ID here.
AWS_REGION: str = _env("AWS_REGION")
S3_BUCKET: str = _env("S3_BUCKET")
S3_PREFIX: str = _env("S3_PREFIX", "organization/files")

# ---------------------------------------------------------------------------
# Module 5 — Amazon RDS PostgreSQL
# ---------------------------------------------------------------------------

# Never commit RDS_PASSWORD.  Set it in the local .env or via an EC2
# environment variable / Secrets Manager.
RDS_HOST: str = _env("RDS_HOST")
RDS_PORT: str = _env("RDS_PORT", "5432")
RDS_DATABASE: str = _env("RDS_DATABASE")
RDS_USERNAME: str = _env("RDS_USERNAME")
RDS_PASSWORD: str = _env("RDS_PASSWORD")
RDS_SSLMODE: str = _env("RDS_SSLMODE", "require")

# ---------------------------------------------------------------------------
# Module 6 — Security & API Authentication
# ---------------------------------------------------------------------------

# APP_ENV controls the authentication enforcement mode.
#
#   "development" (default) — API_KEY enforcement is OFF.
#       Use this for local testing with pytest and local backend runs.
#       Protected endpoints are accessible without an API key.
#
#   "production"  — API_KEY enforcement is ON.
#       API_KEY must be set to a non-empty value or the application will
#       refuse to start (fail-safe).  All protected endpoints require a
#       matching X-API-Key header.  The /health endpoint remains public.
#
# In practice, the EC2 deployment sets APP_ENV=production and API_KEY=<value>
# as environment variables (not from .env, which is never committed).
#
APP_ENV: str = _env("APP_ENV", "development").lower()

# API key for protected endpoint authentication.
# Must be non-empty when APP_ENV=production.
API_KEY: str = _env("API_KEY", "")

# Validate at startup: refuse to run production without a key.
if APP_ENV == "production" and not API_KEY:
    print(
        "[FATAL] APP_ENV=production but API_KEY is not set. "
        "Set API_KEY in the environment before starting the backend. "
        "See modules/module-06/README.md.",
        file=sys.stderr,
    )
    sys.exit(1)
