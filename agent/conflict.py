"""Agent-side conflict copy helpers (Module 8).

Kept in the agent package so the watcher/poller do not import backend code.
The naming scheme matches ``backend.services.conflict.conflict_relative_path``.
"""

from __future__ import annotations

import os
from pathlib import Path


def conflict_relative_path(relative_path: str, local_hash: str) -> str:
    normalized = relative_path.replace("\\", "/").strip().lstrip("/")
    if "/" in normalized:
        parent, name = normalized.rsplit("/", 1)
    else:
        parent, name = "", normalized
    if "." in name and not name.startswith("."):
        stem, ext = name.rsplit(".", 1)
        ext = "." + ext
    else:
        stem, ext = name, ""
    token = (local_hash or "unknown").lower()
    token = "".join(ch for ch in token if ch.isalnum())[:12] or "unknown"
    conflict_name = f"{stem}.conflict-{token}{ext}"
    if parent:
        return f"{parent}/{conflict_name}"
    return conflict_name


def is_conflict_copy_path(relative_path: str) -> bool:
    name = relative_path.replace("\\", "/").rsplit("/", 1)[-1]
    return ".conflict-" in name


def copy_local_to_conflict(sync_folder: str, relative_path: str, local_hash: str) -> str | None:
    """Copy the local file to its conflict path.  Return the relative conflict path."""
    src = Path(sync_folder) / relative_path.replace("/", os.sep)
    if not src.is_file():
        return None
    rel = conflict_relative_path(relative_path, local_hash)
    dest = Path(sync_folder) / rel.replace("/", os.sep)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(src.read_bytes())
    return rel
