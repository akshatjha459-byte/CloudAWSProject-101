"""
repository.py — Metadata / change-feed abstraction.

M3 owns the interface.  M5 will provide the RDS implementation.
The in-memory adapter exists only so M3 can be developed and tested
without a database.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone
from typing import Optional

from backend.models import ChangeRecord, FileRecord, LogRecord, VersionRecord


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _filename(relative_path: str) -> str:
    return relative_path.rstrip("/").split("/")[-1] or relative_path


class MetadataRepository(abc.ABC):
    """Abstraction over relational metadata (RDS in production)."""

    @abc.abstractmethod
    def get_file_by_path(self, relative_path: str) -> Optional[FileRecord]:
        ...

    @abc.abstractmethod
    def get_file_by_id(self, file_id: int) -> Optional[FileRecord]:
        ...

    @abc.abstractmethod
    def list_files(self) -> list[FileRecord]:
        ...

    @abc.abstractmethod
    def upsert_file(
        self,
        relative_path: str,
        *,
        file_hash: Optional[str],
        size: Optional[int],
        storage_key: Optional[str],
        storage_version_id: Optional[str],
        deleted: bool = False,
        timestamp: Optional[str] = None,
    ) -> FileRecord:
        ...

    @abc.abstractmethod
    def rename_file(self, file_id: int, new_path: str, timestamp: Optional[str] = None) -> FileRecord:
        ...

    @abc.abstractmethod
    def mark_deleted(self, file_id: int, timestamp: Optional[str] = None) -> FileRecord:
        ...

    @abc.abstractmethod
    def set_file_status(
        self,
        file_id: int,
        status: str,
        timestamp: Optional[str] = None,
    ) -> FileRecord:
        ...

    @abc.abstractmethod
    def add_version(
        self,
        file_id: int,
        *,
        operation: str,
        file_hash: Optional[str],
        size: Optional[int],
        storage_version_id: Optional[str],
        timestamp: Optional[str] = None,
        source: str = "local",
    ) -> VersionRecord:
        ...

    @abc.abstractmethod
    def list_versions(self, file_id: int) -> list[VersionRecord]:
        ...

    @abc.abstractmethod
    def add_log(
        self,
        *,
        path: str,
        operation: str,
        status: str,
        file_id: Optional[int] = None,
        error_message: Optional[str] = None,
        timestamp: Optional[str] = None,
        source: str = "local",
        destination: str = "backend",
    ) -> LogRecord:
        ...

    @abc.abstractmethod
    def list_logs(self) -> list[LogRecord]:
        ...

    @abc.abstractmethod
    def add_change(
        self,
        *,
        path: str,
        operation: str,
        file_id: Optional[int] = None,
        dest_path: Optional[str] = None,
        file_hash: Optional[str] = None,
        size: Optional[int] = None,
        version_number: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> ChangeRecord:
        ...

    @abc.abstractmethod
    def list_changes(self, since: Optional[str] = None) -> list[ChangeRecord]:
        ...


class MemoryMetadataRepository(MetadataRepository):
    """Development adapter: metadata lives in process memory.

    This is NOT Amazon RDS.  M5 must replace this adapter.
    """

    def __init__(self) -> None:
        self._files: dict[int, FileRecord] = {}
        self._path_index: dict[str, int] = {}
        self._versions: list[VersionRecord] = []
        self._logs: list[LogRecord] = []
        self._changes: list[ChangeRecord] = []
        self._file_seq = 0
        self._version_seq = 0
        self._log_seq = 0
        self._change_seq = 0

    def get_file_by_path(self, relative_path: str) -> Optional[FileRecord]:
        file_id = self._path_index.get(relative_path)
        if file_id is None:
            return None
        return self._files[file_id]

    def get_file_by_id(self, file_id: int) -> Optional[FileRecord]:
        return self._files.get(file_id)

    def list_files(self) -> list[FileRecord]:
        return [self._files[k] for k in sorted(self._files)]

    def upsert_file(
        self,
        relative_path: str,
        *,
        file_hash: Optional[str],
        size: Optional[int],
        storage_key: Optional[str],
        storage_version_id: Optional[str],
        deleted: bool = False,
        timestamp: Optional[str] = None,
    ) -> FileRecord:
        now = timestamp or _utc_now()
        existing = self.get_file_by_path(relative_path)
        if existing is None:
            self._file_seq += 1
            record = FileRecord(
                id=self._file_seq,
                filename=_filename(relative_path),
                relative_path=relative_path,
                current_version=0,
                current_hash=file_hash,
                size=size,
                status="deleted" if deleted else "synced",
                deleted=deleted,
                created_at=now,
                updated_at=now,
                storage_key=storage_key,
                storage_version_id=storage_version_id,
            )
            self._files[record.id] = record
            self._path_index[relative_path] = record.id
            return record

        updated = existing.model_copy(
            update={
                "filename": _filename(relative_path),
                "current_hash": file_hash,
                "size": size,
                "status": "deleted" if deleted else "synced",
                "deleted": deleted,
                "updated_at": now,
                "storage_key": storage_key,
                "storage_version_id": storage_version_id,
            }
        )
        self._files[existing.id] = updated
        return updated

    def rename_file(self, file_id: int, new_path: str, timestamp: Optional[str] = None) -> FileRecord:
        record = self._files[file_id]
        self._path_index.pop(record.relative_path, None)
        now = timestamp or _utc_now()
        updated = record.model_copy(
            update={
                "relative_path": new_path,
                "filename": _filename(new_path),
                "updated_at": now,
                "deleted": False,
                "status": "synced",
            }
        )
        self._files[file_id] = updated
        self._path_index[new_path] = file_id
        return updated

    def mark_deleted(self, file_id: int, timestamp: Optional[str] = None) -> FileRecord:
        record = self._files[file_id]
        now = timestamp or _utc_now()
        updated = record.model_copy(
            update={"deleted": True, "status": "deleted", "updated_at": now}
        )
        self._files[file_id] = updated
        return updated

    def set_file_status(
        self,
        file_id: int,
        status: str,
        timestamp: Optional[str] = None,
    ) -> FileRecord:
        record = self._files[file_id]
        now = timestamp or _utc_now()
        updated = record.model_copy(update={"status": status, "updated_at": now})
        self._files[file_id] = updated
        return updated

    def add_version(
        self,
        file_id: int,
        *,
        operation: str,
        file_hash: Optional[str],
        size: Optional[int],
        storage_version_id: Optional[str],
        timestamp: Optional[str] = None,
        source: str = "local",
    ) -> VersionRecord:
        file_record = self._files[file_id]
        version_number = file_record.current_version + 1
        self._version_seq += 1
        now = timestamp or _utc_now()
        version = VersionRecord(
            id=self._version_seq,
            file_id=file_id,
            version_number=version_number,
            hash=file_hash,
            size=size,
            operation=operation,
            source=source,
            storage_version_id=storage_version_id,
            created_at=now,
            is_conflict=operation == "CONFLICT",
        )
        self._versions.append(version)
        self._files[file_id] = file_record.model_copy(
            update={"current_version": version_number, "updated_at": now}
        )
        return version

    def list_versions(self, file_id: int) -> list[VersionRecord]:
        return [v for v in self._versions if v.file_id == file_id]

    def add_log(
        self,
        *,
        path: str,
        operation: str,
        status: str,
        file_id: Optional[int] = None,
        error_message: Optional[str] = None,
        timestamp: Optional[str] = None,
        source: str = "local",
        destination: str = "backend",
    ) -> LogRecord:
        self._log_seq += 1
        record = LogRecord(
            id=self._log_seq,
            file_id=file_id,
            path=path,
            operation=operation,
            source=source,
            destination=destination,
            status=status,
            error_message=error_message,
            timestamp=timestamp or _utc_now(),
        )
        self._logs.append(record)
        return record

    def list_logs(self) -> list[LogRecord]:
        return list(self._logs)

    def add_change(
        self,
        *,
        path: str,
        operation: str,
        file_id: Optional[int] = None,
        dest_path: Optional[str] = None,
        file_hash: Optional[str] = None,
        size: Optional[int] = None,
        version_number: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> ChangeRecord:
        self._change_seq += 1
        record = ChangeRecord(
            id=self._change_seq,
            file_id=file_id,
            path=path,
            dest_path=dest_path,
            operation=operation,
            hash=file_hash,
            size=size,
            version_number=version_number,
            timestamp=timestamp or _utc_now(),
        )
        self._changes.append(record)
        return record

    def list_changes(self, since: Optional[str] = None) -> list[ChangeRecord]:
        if not since:
            return list(self._changes)
        return [c for c in self._changes if c.timestamp > since]
