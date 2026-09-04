"""
events.py — Module 2: Synchronisation event definition and normalisation.

Defines the canonical ``SyncEvent`` structure agreed in docs/module-contracts.md:

    {
        "operation": "MODIFIED",
        "path": "reports/test.txt",
        "hash": "...",
        "size": 1234,
        "timestamp": "2026-09-03T00:00:00Z"
    }

All paths in a ``SyncEvent`` are relative to the configured sync folder and
use forward slashes regardless of the host operating system.

Permitted operations (string constants defined below):
    OP_CREATED   = "CREATED"
    OP_MODIFIED  = "MODIFIED"
    OP_DELETED   = "DELETED"
    OP_MOVED     = "MOVED"
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Operation constants
# ---------------------------------------------------------------------------

OP_CREATED = "CREATED"
OP_MODIFIED = "MODIFIED"
OP_DELETED = "DELETED"
OP_MOVED = "MOVED"

VALID_OPERATIONS = {OP_CREATED, OP_MODIFIED, OP_DELETED, OP_MOVED}


# ---------------------------------------------------------------------------
# SyncEvent
# ---------------------------------------------------------------------------

@dataclass
class SyncEvent:
    """A single normalised filesystem synchronisation event.

    Attributes:
        operation:  One of CREATED, MODIFIED, DELETED, MOVED.
        path:       File path relative to the sync folder, with forward slashes.
        hash:       Lowercase hex SHA-256 of the file content, or ``None`` for
                    DELETED events where the file no longer exists.
        size:       File size in bytes, or ``None`` for DELETED events.
        timestamp:  ISO-8601 UTC timestamp string (e.g. ``2026-09-03T12:00:00Z``).
        dest_path:  For MOVED events only — the new relative path.  ``None``
                    for all other operations.
    """

    operation: str
    path: str
    hash: Optional[str]
    size: Optional[int]
    timestamp: str
    dest_path: Optional[str] = field(default=None)
    base_hash: Optional[str] = field(default=None)

    def __post_init__(self) -> None:
        if self.operation not in VALID_OPERATIONS:
            raise ValueError(
                f"Invalid operation {self.operation!r}. "
                f"Must be one of {sorted(VALID_OPERATIONS)}."
            )
        if self.operation == OP_MOVED and self.dest_path is None:
            raise ValueError("MOVED events must supply dest_path.")

    def to_dict(self) -> dict:
        """Return a plain dict representation matching the contract JSON shape."""
        d = asdict(self)
        # Remove dest_path from non-MOVED events to keep the payload clean.
        if self.operation != OP_MOVED:
            d.pop("dest_path", None)
        if not d.get("base_hash"):
            d.pop("base_hash", None)
        return d

    def to_json(self, indent: int | None = None) -> str:
        """Serialise the event to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string ending in ``Z``."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _portable_path(path: str) -> str:
    """Replace OS-specific separators with forward slashes."""
    return path.replace("\\", "/")


def make_event(
    operation: str,
    relative_path: str,
    *,
    hash: Optional[str] = None,
    size: Optional[int] = None,
    timestamp: Optional[str] = None,
    dest_path: Optional[str] = None,
    base_hash: Optional[str] = None,
) -> SyncEvent:
    """Construct a ``SyncEvent`` with sensible defaults.

    Args:
        operation:     One of the OP_* constants.
        relative_path: Path relative to the sync folder.
        hash:          SHA-256 hex digest.  May be ``None`` for DELETED events.
        size:          File size in bytes.  May be ``None`` for DELETED events.
        timestamp:     ISO-8601 UTC string.  Defaults to the current time.
        dest_path:     Required for MOVED events.

    Returns:
        A validated :class:`SyncEvent` instance.
    """
    return SyncEvent(
        operation=operation,
        path=_portable_path(relative_path),
        hash=hash,
        size=size,
        timestamp=timestamp or _utc_now(),
        dest_path=_portable_path(dest_path) if dest_path is not None else None,
        base_hash=base_hash,
    )
