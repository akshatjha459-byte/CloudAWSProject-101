"""
storage.py — File-content storage abstraction.

M3 owns the interface.  M4 will provide the S3 implementation.
The in-memory adapter exists only so M3 can be developed and tested
without AWS.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StoragePutResult:
    """Result of storing file content.

    ``version_id`` is a storage-layer version token.  For the memory adapter
    this is a simple incrementing identifier.  M4 will populate it from S3
    Versioning.
    """

    key: str
    version_id: str
    size: int


class FileStorage(abc.ABC):
    """Abstraction over cloud object storage (S3 in production)."""

    @abc.abstractmethod
    def put(self, key: str, content: bytes) -> StoragePutResult:
        """Store or replace object content at *key*."""

    @abc.abstractmethod
    def get(self, key: str, version_id: Optional[str] = None) -> Optional[bytes]:
        """Return object bytes, or None if missing.

        When *version_id* is provided, return that stored version rather than
        the current object (S3 Versioning / in-memory history).
        """

    @abc.abstractmethod
    def delete(self, key: str) -> None:
        """Remove or logically delete the object at *key*.

        The memory adapter deletes the object.  M4 will apply the documented
        S3 deletion strategy (retain versions vs. delete marker).
        """

    @abc.abstractmethod
    def copy(self, source_key: str, dest_key: str) -> Optional[StoragePutResult]:
        """Copy *source_key* to *dest_key*.  Return None if source is missing."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if *key* currently exists."""


class MemoryFileStorage(FileStorage):
    """Development adapter: objects live in process memory.

    This is NOT Amazon S3.  M4 must replace this adapter.
    """

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._versions: dict[str, int] = {}
        self._history: dict[str, dict[str, bytes]] = {}

    def put(self, key: str, content: bytes) -> StoragePutResult:
        self._versions[key] = self._versions.get(key, 0) + 1
        version_id = str(self._versions[key])
        self._objects[key] = content
        self._history.setdefault(key, {})[version_id] = content
        return StoragePutResult(
            key=key,
            version_id=version_id,
            size=len(content),
        )

    def get(self, key: str, version_id: Optional[str] = None) -> Optional[bytes]:
        if version_id:
            return self._history.get(key, {}).get(str(version_id))
        return self._objects.get(key)

    def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    def copy(self, source_key: str, dest_key: str) -> Optional[StoragePutResult]:
        content = self._objects.get(source_key)
        if content is None:
            return None
        result = self.put(dest_key, content)
        self._objects.pop(source_key, None)
        return result

    def exists(self, key: str) -> bool:
        return key in self._objects
