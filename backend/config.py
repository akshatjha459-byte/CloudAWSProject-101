"""
config.py — Module 3: Backend configuration.

Reads settings from environment variables and an optional project-root .env
file.  AWS credentials are never loaded here; boto3 uses the default chain
when STORAGE_ADAPTER=s3.  RDS passwords come only from the environment.
"""

from __future__ import annotations

import os
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


# Bind address for the local/dev server.  Deployment (EC2) should set these
# via environment variables rather than code changes.
BACKEND_HOST: str = _env("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT: int = int(_env("BACKEND_PORT", "8000") or "8000")
LOG_LEVEL: str = _env("LOG_LEVEL", "INFO").upper()

# Identifier used in /status so operators can see which storage adapter is live.
# Default remains "memory" so M3 tests and local development need no AWS.
# Set STORAGE_ADAPTER=s3 to use Module 4 Amazon S3 storage.
# Set METADATA_ADAPTER=rds to use Module 5 Amazon RDS metadata.
STORAGE_ADAPTER: str = _env("STORAGE_ADAPTER", "memory")
METADATA_ADAPTER: str = _env("METADATA_ADAPTER", "memory")

# Module 4 — Amazon S3 (file content only).  Credentials come from the
# default AWS chain (env vars, shared config, or EC2 instance role).
AWS_REGION: str = _env("AWS_REGION")
S3_BUCKET: str = _env("S3_BUCKET")
S3_PREFIX: str = _env("S3_PREFIX", "organization/files")

# Module 5 — Amazon RDS PostgreSQL (metadata only; never file bytes).
RDS_HOST: str = _env("RDS_HOST")
RDS_PORT: str = _env("RDS_PORT", "5432")
RDS_DATABASE: str = _env("RDS_DATABASE")
RDS_USERNAME: str = _env("RDS_USERNAME")
RDS_PASSWORD: str = _env("RDS_PASSWORD")
RDS_SSLMODE: str = _env("RDS_SSLMODE", "require")
