"""
models.py — Module 3: Request/response schemas.

These models validate the HTTP contract defined in docs/module-contracts.md
and remain independent of S3 (M4) and RDS (M5).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

VALID_UPLOAD_OPERATIONS = {"CREATED", "MODIFIED", "MOVED"}
VALID_DELETE_OPERATIONS = {"DELETED"}


class DeleteRequest(BaseModel):
    """Body for POST /sync/delete — matches M2 SyncEvent fields."""

    operation: str
    path: str
    hash: Optional[str] = None
    size: Optional[int] = None
    timestamp: str
    dest_path: Optional[str] = None

    @field_validator("operation")
    @classmethod
    def _operation_must_be_deleted(cls, value: str) -> str:
        if value not in VALID_DELETE_OPERATIONS:
            raise ValueError("operation must be DELETED")
        return value

    @field_validator("path")
    @classmethod
    def _path_required(cls, value: str) -> str:
        value = value.replace("\\", "/").strip()
        if not value:
            raise ValueError("path is required")
        return value


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = "ok"


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "hybrid-cloud-sync-backend"


class FileRecord(BaseModel):
    id: int
    filename: str
    relative_path: str
    current_version: int
    current_hash: Optional[str] = None
    size: Optional[int] = None
    status: str
    deleted: bool = False
    created_at: str
    updated_at: str
    storage_key: Optional[str] = None
    storage_version_id: Optional[str] = None


class VersionRecord(BaseModel):
    id: int
    file_id: int
    version_number: int
    hash: Optional[str] = None
    size: Optional[int] = None
    operation: str
    source: str = "local"
    storage_version_id: Optional[str] = None
    created_at: str
    is_conflict: bool = False


class LogRecord(BaseModel):
    id: int
    file_id: Optional[int] = None
    path: str
    operation: str
    source: str = "local"
    destination: str = "backend"
    status: str
    error_message: Optional[str] = None
    timestamp: str


class ChangeRecord(BaseModel):
    """A cloud-side change the M2 agent can consume (M7 will apply these)."""

    id: int
    file_id: Optional[int] = None
    path: str
    dest_path: Optional[str] = None
    operation: str
    hash: Optional[str] = None
    size: Optional[int] = None
    version_number: Optional[int] = None
    timestamp: str


class UploadResult(BaseModel):
    success: bool = True
    message: str
    file: FileRecord
    version: VersionRecord
    idempotent: bool = False
    conflict: bool = False
    conflict_path: Optional[str] = None


class DeleteResult(BaseModel):
    success: bool = True
    message: str
    file: FileRecord


class StatusResponse(BaseModel):
    status: str
    storage_adapter: str
    metadata_adapter: str
    file_count: int
    deleted_count: int
    log_count: int
    change_count: int
    conflict_count: int = 0
    last_operation_at: Optional[str] = None
    notes: dict[str, Any] = Field(default_factory=dict)


class ChangesResponse(BaseModel):
    success: bool = True
    since: Optional[str] = None
    count: int
    changes: list[ChangeRecord]


class FilesResponse(BaseModel):
    success: bool = True
    count: int
    files: list[FileRecord]


class VersionsResponse(BaseModel):
    success: bool = True
    file_id: int
    count: int
    versions: list[VersionRecord]


class LogsResponse(BaseModel):
    success: bool = True
    count: int
    logs: list[LogRecord]


UploadOperation = Literal["CREATED", "MODIFIED", "MOVED"]
