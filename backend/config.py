"""
config.py — Module 3: Backend configuration.

Reads settings from environment variables and an optional project-root .env
file.  No AWS credentials are loaded here.  S3/RDS settings belong to later
modules and are not consumed by M3.
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
# M3 ships with the in-memory adapter; M4 will replace it with S3.
STORAGE_ADAPTER: str = _env("STORAGE_ADAPTER", "memory")
METADATA_ADAPTER: str = _env("METADATA_ADAPTER", "memory")
