"""
sync_service.py — Module 3 application service.

Orchestrates validation, the file-storage adapter, and the metadata
repository.  Contains no AWS SDK calls.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from backend.adapters.repository import MetadataRepository
from backend.adapters.storage import FileStorage
from backend.models import (
    ChangeRecord,
    DeleteRequest,
    DeleteResult,
    FileRecord,
    LogRecord,
    StatusResponse,
    UploadResult,
    VALID_UPLOAD_OPERATIONS,
    VersionRecord,
)


class SyncValidationError(ValueError):
    """Raised when an upload/delete request fails business validation."""


class SyncNotFoundError(LookupError):
    """Raised when a requested file id does not exist."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("/")


class SyncService:
    def __init__(
        self,
        storage: FileStorage,
        repository: MetadataRepository,
        *,
        storage_adapter_name: str = "memory",
        metadata_adapter_name: str = "memory",
    ) -> None:
        self._storage = storage
        self._repo = repository
        self._storage_adapter_name = storage_adapter_name
        self._metadata_adapter_name = metadata_adapter_name

    def upload(
        self,
        *,
        operation: str,
        path: str,
        timestamp: str,
        file_hash: Optional[str] = None,
        size: Optional[int] = None,
        dest_path: Optional[str] = None,
        content: Optional[bytes] = None,
    ) -> UploadResult:
        operation = operation.upper()
        if operation not in VALID_UPLOAD_OPERATIONS:
            raise SyncValidationError(
                f"operation must be one of {sorted(VALID_UPLOAD_OPERATIONS)}"
            )

        path = _normalize_path(path)
        if not path:
            raise SyncValidationError("path is required")
        if dest_path:
            dest_path = _normalize_path(dest_path)

        if operation == "MOVED":
            return self._handle_move(path, dest_path, timestamp, file_hash, size, content)

        if content is None:
            raise SyncValidationError("file content is required for CREATED and MODIFIED")

        actual_hash = _sha256(content)
        actual_size = len(content)
        if size is not None and size != actual_size:
            raise SyncValidationError(
                f"declared size {size} does not match content length {actual_size}"
            )
        if file_hash and file_hash.lower() != actual_hash:
            raise SyncValidationError("declared hash does not match file content")

        existing = self._repo.get_file_by_path(path)
        if (
            existing is not None
            and not existing.deleted
            and existing.current_hash == actual_hash
        ):
            self._repo.add_log(
                path=path,
                operation=operation,
                status="SUCCESS",
                file_id=existing.id,
                timestamp=timestamp,
            )
            versions = self._repo.list_versions(existing.id)
            latest = versions[-1] if versions else self._repo.add_version(
                existing.id,
                operation=operation,
                file_hash=actual_hash,
                size=actual_size,
                storage_version_id=existing.storage_version_id,
                timestamp=timestamp,
            )
            return UploadResult(
                message="already synchronized (idempotent)",
                file=existing,
                version=latest,
                idempotent=True,
            )

        put = self._storage.put(path, content)
        file_record = self._repo.upsert_file(
            path,
            file_hash=actual_hash,
            size=actual_size,
            storage_key=put.key,
            storage_version_id=put.version_id,
            deleted=False,
            timestamp=timestamp,
        )
        version = self._repo.add_version(
            file_record.id,
            operation=operation,
            file_hash=actual_hash,
            size=actual_size,
            storage_version_id=put.version_id,
            timestamp=timestamp,
        )
        # upsert_file may have reset current_version; re-read after add_version
        file_record = self._repo.get_file_by_id(file_record.id)
        assert file_record is not None
        self._repo.add_log(
            path=path,
            operation=operation,
            status="SUCCESS",
            file_id=file_record.id,
            timestamp=timestamp,
        )
        self._repo.add_change(
            path=path,
            operation=operation,
            file_id=file_record.id,
            file_hash=actual_hash,
            size=actual_size,
            timestamp=timestamp,
        )
        return UploadResult(
            message="synchronized",
            file=file_record,
            version=version,
        )

    def _handle_move(
        self,
        path: str,
        dest_path: Optional[str],
        timestamp: str,
        file_hash: Optional[str],
        size: Optional[int],
        content: Optional[bytes],
    ) -> UploadResult:
        if not dest_path:
            raise SyncValidationError("MOVED events must supply dest_path")

        existing = self._repo.get_file_by_path(path)
        copied = self._storage.copy(path, dest_path)
        if copied is None and content is not None:
            copied = self._storage.put(dest_path, content)

        storage_key = copied.key if copied else dest_path
        storage_version_id = copied.version_id if copied else None
        if content is not None:
            file_hash = _sha256(content)
            size = len(content)

        if existing is not None:
            if file_hash is None:
                file_hash = existing.current_hash
            if size is None:
                size = existing.size
            file_record = self._repo.rename_file(existing.id, dest_path, timestamp=timestamp)
            file_record = self._repo.upsert_file(
                dest_path,
                file_hash=file_hash,
                size=size,
                storage_key=storage_key,
                storage_version_id=storage_version_id,
                deleted=False,
                timestamp=timestamp,
            )
        else:
            file_record = self._repo.upsert_file(
                dest_path,
                file_hash=file_hash,
                size=size,
                storage_key=storage_key,
                storage_version_id=storage_version_id,
                deleted=False,
                timestamp=timestamp,
            )

        version = self._repo.add_version(
            file_record.id,
            operation="MOVED",
            file_hash=file_hash,
            size=size,
            storage_version_id=storage_version_id,
            timestamp=timestamp,
        )
        file_record = self._repo.get_file_by_id(file_record.id)
        assert file_record is not None
        self._repo.add_log(
            path=path,
            operation="MOVED",
            status="SUCCESS",
            file_id=file_record.id,
            timestamp=timestamp,
        )
        self._repo.add_change(
            path=path,
            operation="MOVED",
            file_id=file_record.id,
            dest_path=dest_path,
            file_hash=file_hash,
            size=size,
            timestamp=timestamp,
        )
        return UploadResult(
            message="moved",
            file=file_record,
            version=version,
        )

    def delete(self, request: DeleteRequest) -> DeleteResult:
        path = _normalize_path(request.path)
        self._storage.delete(path)
        existing = self._repo.get_file_by_path(path)
        if existing is None:
            file_record = self._repo.upsert_file(
                path,
                file_hash=request.hash,
                size=request.size,
                storage_key=path,
                storage_version_id=None,
                deleted=True,
                timestamp=request.timestamp,
            )
        else:
            file_record = self._repo.mark_deleted(existing.id, timestamp=request.timestamp)

        self._repo.add_version(
            file_record.id,
            operation="DELETED",
            file_hash=request.hash,
            size=request.size,
            storage_version_id=None,
            timestamp=request.timestamp,
        )
        file_record = self._repo.get_file_by_id(file_record.id)
        assert file_record is not None
        self._repo.add_log(
            path=path,
            operation="DELETED",
            status="SUCCESS",
            file_id=file_record.id,
            timestamp=request.timestamp,
        )
        self._repo.add_change(
            path=path,
            operation="DELETED",
            file_id=file_record.id,
            file_hash=request.hash,
            size=request.size,
            timestamp=request.timestamp,
        )
        return DeleteResult(message="deleted", file=file_record)

    def list_changes(self, since: Optional[str] = None) -> list[ChangeRecord]:
        return self._repo.list_changes(since=since)

    def list_files(self) -> list[FileRecord]:
        return self._repo.list_files()

    def download(self, file_id: int) -> bytes:
        file_record = self._repo.get_file_by_id(file_id)
        if file_record is None:
            raise SyncNotFoundError(f"file {file_id} not found")
        if file_record.deleted:
            raise SyncNotFoundError(f"file {file_id} is deleted")
        
        content = self._storage.get(file_record.storage_key)
        if content is None:
            raise SyncNotFoundError(f"file content for {file_id} not found in storage")
        return content

    def list_versions(self, file_id: int) -> tuple[FileRecord, list[VersionRecord]]:
        file_record = self._repo.get_file_by_id(file_id)
        if file_record is None:
            raise SyncNotFoundError(f"file {file_id} not found")
        return file_record, self._repo.list_versions(file_id)

    def list_logs(self) -> list[LogRecord]:
        return self._repo.list_logs()

    def status(self) -> StatusResponse:
        files = self._repo.list_files()
        logs = self._repo.list_logs()
        changes = self._repo.list_changes()
        last = None
        if logs:
            last = logs[-1].timestamp
        elif changes:
            last = changes[-1].timestamp
        return StatusResponse(
            status="ok",
            storage_adapter=self._storage_adapter_name,
            metadata_adapter=self._metadata_adapter_name,
            file_count=sum(1 for f in files if not f.deleted),
            deleted_count=sum(1 for f in files if f.deleted),
            log_count=len(logs),
            change_count=len(changes),
            last_operation_at=last,
            notes={
                "s3": "active" if self._storage_adapter_name == "s3" else "not selected",
                "rds": "active" if self._metadata_adapter_name == "rds" else "not selected",
                "storage": (
                    "amazon s3"
                    if self._storage_adapter_name == "s3"
                    else "in-memory development adapter"
                ),
                "metadata": (
                    "amazon rds"
                    if self._metadata_adapter_name == "rds"
                    else "in-memory development adapter"
                ),
            },
        )
