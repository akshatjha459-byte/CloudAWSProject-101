"""Conflict-copy path helper (Module 8).

Local and cloud copies of the same relative path are preserved by writing the
divergent local bytes to a sibling path derived from the local content hash:

    reports/file.txt  ->  reports/file.conflict-a1b2c3d4e5f6.txt

The original path keeps the cloud-canonical content.  Hash-based names make
retries deterministic: the same conflicting bytes reuse the same path.
"""

from __future__ import annotations


def conflict_relative_path(relative_path: str, local_hash: str) -> str:
    """Return a portable relative path for a conflict copy of *relative_path*."""
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
