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
from backend.services.conflict import conflict_relative_path, is_conflict_copy_path
from backend.services.observability import Observability, sanitize_value


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
        observability: Optional[Observability] = None,
    ) -> None:
        self._storage = storage
        self._repo = repository
        self._storage_adapter_name = storage_adapter_name
        self._metadata_adapter_name = metadata_adapter_name
        self._obs = observability

    def _safe_add_log(self, **kwargs) -> Optional[LogRecord]:
        """RDS/SYNC_LOGS write that never fails the caller."""
        try:
            return self._repo.add_log(**kwargs)
        except Exception:
            if self._obs is not None:
                try:
                    self._obs.structured.emit(
                        "ERROR",
                        "logging.failure",
                        success=False,
                        path=kwargs.get("path"),
                        operation=kwargs.get("operation"),
                    )
                except Exception:
                    pass
            return None

    def _observe_success(self, operation: str, path: str, result: UploadResult) -> None:
        if self._obs is None:
            return
        try:
            self._obs.on_file_event(
                operation=operation, path=path, file_id=result.file.id
            )
            self._obs.on_sync_success(
                operation="CONFLICT" if result.conflict else operation,
                path=path,
                file_id=result.file.id,
                conflict=result.conflict,
                conflict_path=result.conflict_path,
                idempotent=result.idempotent,
            )
        except Exception:
            return

    def _observe_delete_success(self, path: str, result: DeleteResult) -> None:
        if self._obs is None:
            return
        try:
            self._obs.on_file_event(
                operation="DELETED", path=path, file_id=result.file.id
            )
            self._obs.on_sync_success(
                operation="DELETED",
                path=path,
                file_id=result.file.id,
            )
        except Exception:
            return

    def _observe_failure(
        self, operation: str, path: str, error: str, *, critical: bool
    ) -> None:
        safe_error = str(sanitize_value(error))[:500]
        self._safe_add_log(
            path=path or "",
            operation=(operation or "UNKNOWN").upper(),
            status="FAILURE",
            error_message=safe_error or None,
        )
        if self._obs is None:
            return
        try:
            self._obs.on_sync_failure(
                operation=operation, path=path or "", error=safe_error, critical=critical
            )
        except Exception:
            return

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
        base_hash: Optional[str] = None,
    ) -> UploadResult:
        try:
            result = self._upload_impl(
                operation=operation,
                path=path,
                timestamp=timestamp,
                file_hash=file_hash,
                size=size,
                dest_path=dest_path,
                content=content,
                base_hash=base_hash,
            )
            self._observe_success(operation.upper(), path, result)
            return result
        except SyncValidationError as exc:
            self._observe_failure(operation, path, str(exc), critical=False)
            raise
        except Exception as exc:
            self._observe_failure(operation, path, str(exc), critical=False)
            raise

    def _upload_impl(
        self,
        *,
        operation: str,
        path: str,
        timestamp: str,
        file_hash: Optional[str] = None,
        size: Optional[int] = None,
        dest_path: Optional[str] = None,
        content: Optional[bytes] = None,
        base_hash: Optional[str] = None,
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
            self._safe_add_log(
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

        if (
            existing is not None
            and not existing.deleted
            and existing.current_hash
            and existing.current_hash != actual_hash
            and not is_conflict_copy_path(path)
            and self._is_divergent_conflict(existing.current_hash, actual_hash, base_hash)
        ):
            return self._preserve_conflict(
                existing=existing,
                local_content=content,
                local_hash=actual_hash,
                local_size=actual_size,
                timestamp=timestamp,
                operation=operation,
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
        self._safe_add_log(
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

    @staticmethod
    def _is_divergent_conflict(
        cloud_hash: str,
        local_hash: str,
        base_hash: Optional[str],
    ) -> bool:
        """True when local and cloud both moved away from a shared base hash."""
        if not base_hash:
            return False
        return (
            local_hash != cloud_hash
            and base_hash != cloud_hash
            and base_hash != local_hash
        )

    def _preserve_conflict(
        self,
        *,
        existing,
        local_content: bytes,
        local_hash: str,
        local_size: int,
        timestamp: str,
        operation: str,
    ) -> UploadResult:
        conflict_path = conflict_relative_path(existing.relative_path, local_hash)
        conflict_file = self._repo.get_file_by_path(conflict_path)
        if (
            conflict_file is not None
            and not conflict_file.deleted
            and conflict_file.current_hash == local_hash
        ):
            original = self._repo.set_file_status(
                existing.id, "conflict", timestamp=timestamp
            )
            versions = self._repo.list_versions(conflict_file.id)
            latest = versions[-1] if versions else self._repo.add_version(
                conflict_file.id,
                operation="CONFLICT",
                file_hash=local_hash,
                size=local_size,
                storage_version_id=conflict_file.storage_version_id,
                timestamp=timestamp,
                source="local",
            )
            self._safe_add_log(
                path=existing.relative_path,
                operation="CONFLICT",
                status="SUCCESS",
                file_id=existing.id,
                timestamp=timestamp,
                error_message=(
                    f"idempotent conflict; local preserved at {conflict_path}; "
                    f"cloud_hash={existing.current_hash}; local_hash={local_hash}"
                ),
            )
            return UploadResult(
                message="conflict preserved (idempotent)",
                file=original,
                version=latest,
                idempotent=True,
                conflict=True,
                conflict_path=conflict_path,
            )

        put = self._storage.put(conflict_path, local_content)
        conflict_file = self._repo.upsert_file(
            conflict_path,
            file_hash=local_hash,
            size=local_size,
            storage_key=put.key,
            storage_version_id=put.version_id,
            deleted=False,
            timestamp=timestamp,
        )
        version = self._repo.add_version(
            conflict_file.id,
            operation="CONFLICT",
            file_hash=local_hash,
            size=local_size,
            storage_version_id=put.version_id,
            timestamp=timestamp,
            source="local",
        )
        conflict_file = self._repo.get_file_by_id(conflict_file.id)
        assert conflict_file is not None
        original = self._repo.set_file_status(
            existing.id, "conflict", timestamp=timestamp
        )
        detail = (
            f"local preserved at {conflict_path}; "
            f"cloud_hash={existing.current_hash}; local_hash={local_hash}; "
            f"operation={operation}"
        )
        self._safe_add_log(
            path=existing.relative_path,
            operation="CONFLICT",
            status="SUCCESS",
            file_id=existing.id,
            timestamp=timestamp,
            error_message=detail,
        )
        self._safe_add_log(
            path=conflict_path,
            operation="CONFLICT",
            status="SUCCESS",
            file_id=conflict_file.id,
            timestamp=timestamp,
            error_message=detail,
        )
        self._repo.add_change(
            path=conflict_path,
            operation="CREATED",
            file_id=conflict_file.id,
            file_hash=local_hash,
            size=local_size,
            timestamp=timestamp,
        )
        return UploadResult(
            message="conflict preserved",
            file=original,
            version=version,
            conflict=True,
            conflict_path=conflict_path,
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
        self._safe_add_log(
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
        try:
            result = self._delete_impl(request, path)
            self._observe_delete_success(path, result)
            return result
        except SyncValidationError as exc:
            self._observe_failure("DELETED", path, str(exc), critical=False)
            raise
        except Exception as exc:
            self._observe_failure("DELETED", path, str(exc), critical=False)
            raise

    def _delete_impl(self, request: DeleteRequest, path: str) -> DeleteResult:
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
        self._safe_add_log(
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

    def download(self, file_id: int, version_number: Optional[int] = None) -> bytes:
        file_record = self._repo.get_file_by_id(file_id)
        if file_record is None:
            raise SyncNotFoundError(f"file {file_id} not found")
        if file_record.deleted and version_number is None:
            raise SyncNotFoundError(f"file {file_id} is deleted")

        storage_version_id = None
        if version_number is not None:
            versions = self._repo.list_versions(file_id)
            match = next((v for v in versions if v.version_number == version_number), None)
            if match is None:
                raise SyncNotFoundError(
                    f"version {version_number} not found for file {file_id}"
                )
            storage_version_id = match.storage_version_id

        content = self._storage.get(file_record.storage_key, storage_version_id)
        if content is None and storage_version_id:
            content = self._storage.get(file_record.relative_path, storage_version_id)
        if content is None and version_number is None:
            content = self._storage.get(file_record.relative_path)
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
        conflict_count = sum(
            1
            for f in files
            if not f.deleted
            and (f.status == "conflict" or is_conflict_copy_path(f.relative_path))
        )
        return StatusResponse(
            status="ok",
            storage_adapter=self._storage_adapter_name,
            metadata_adapter=self._metadata_adapter_name,
            file_count=sum(1 for f in files if not f.deleted),
            deleted_count=sum(1 for f in files if f.deleted),
            log_count=len(logs),
            change_count=len(changes),
            conflict_count=conflict_count,
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
                **(self._obs.status_notes() if self._obs is not None else {}),
            },
        )
