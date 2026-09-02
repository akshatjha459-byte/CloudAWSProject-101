"""
config.py — Module 2: Synchronization Agent configuration.

Reads agent configuration from environment variables and/or a .env file.
Uses only Python standard library — no third-party dependencies.

Resolved values (all public):
    SYNC_FOLDER : str   — absolute path to the watched directory
    LOG_LEVEL   : str   — logging level (default: INFO)
"""

import logging
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Minimal .env loader (no python-dotenv dependency)
# ---------------------------------------------------------------------------

def _load_dotenv(dotenv_path: Path) -> None:
    """Load KEY=VALUE pairs from *dotenv_path* into os.environ.

    Only sets keys that are not already present in the environment, so real
    environment variables always take precedence over the file.
    Blank lines and lines starting with ``#`` are ignored.
    """
    if not dotenv_path.is_file():
        return
    with dotenv_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


# Attempt to load .env from the project root (two levels above agent/).
_project_root = Path(__file__).resolve().parent.parent
_load_dotenv(_project_root / ".env")


# ---------------------------------------------------------------------------
# Public configuration values
# ---------------------------------------------------------------------------

def _resolve_sync_folder() -> str:
    """Return the absolute path to the synchronisation directory.

    Resolution order:
    1. ``SYNC_FOLDER`` environment variable / .env entry.
    2. Default ``./organization/files`` relative to the project root.
    """
    raw = os.environ.get("SYNC_FOLDER", "")
    if not raw:
        raw = "./organization/files"
    path = (_project_root / raw).resolve()
    return str(path)


SYNC_FOLDER: str = _resolve_sync_folder()
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Logging (configured once on import)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
