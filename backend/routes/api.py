"""
api.py — Module 3 HTTP routes.

Implements the REST contract from docs/module-contracts.md.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile

from backend import config
from backend.models import (
    ChangesResponse,
    DeleteRequest,
    DeleteResult,
    ErrorResponse,
    FilesResponse,
    HealthResponse,
    LogsResponse,
    StatusResponse,
    UploadResult,
    VersionsResponse,
)
from backend.services.sync_service import SyncNotFoundError, SyncService, SyncValidationError

router = APIRouter()


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    if config.API_KEY and x_api_key != config.API_KEY:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "error": "unauthorized", "detail": "Invalid or missing API key"},
        )


def get_service(request: Request) -> SyncService:
    return request.app.state.sync_service


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()



@router.post(
    "/sync/upload",
    response_model=UploadResult,
    responses={400: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
async def sync_upload(
    operation: str = Form(...),
    path: str = Form(...),
    timestamp: str = Form(...),
    hash: Optional[str] = Form(None),
    size: Optional[int] = Form(None),
    dest_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    service: SyncService = Depends(get_service),
) -> UploadResult:
    content: Optional[bytes] = None
    if file is not None:
        content = await file.read()
    try:
        return service.upload(
            operation=operation,
            path=path,
            timestamp=timestamp,
            file_hash=hash,
            size=size,
            dest_path=dest_path,
            content=content,
        )
    except SyncValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "validation_error", "detail": str(exc)},
        ) from exc


@router.post(
    "/sync/delete",
    response_model=DeleteResult,
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
def sync_delete(
    body: DeleteRequest,
    service: SyncService = Depends(get_service),
) -> DeleteResult:
    try:
        return service.delete(body)
    except SyncValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "validation_error", "detail": str(exc)},
        ) from exc


@router.get(
    "/sync/changes",
    response_model=ChangesResponse,
    dependencies=[Depends(verify_api_key)],
)
def sync_changes(
    since: Optional[str] = Query(
        default=None,
        description="ISO-8601 UTC timestamp; only changes after this value are returned.",
    ),
    service: SyncService = Depends(get_service),
) -> ChangesResponse:
    changes = service.list_changes(since=since)
    return ChangesResponse(since=since, count=len(changes), changes=changes)


@router.get(
    "/files",
    response_model=FilesResponse,
    dependencies=[Depends(verify_api_key)],
)
def list_files(service: SyncService = Depends(get_service)) -> FilesResponse:
    files = service.list_files()
    return FilesResponse(count=len(files), files=files)


@router.get(
    "/files/{file_id}/versions",
    response_model=VersionsResponse,
    responses={404: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
def file_versions(
    file_id: int,
    service: SyncService = Depends(get_service),
) -> VersionsResponse:
    try:
        _, versions = service.list_versions(file_id)
    except SyncNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"success": False, "error": "not_found", "detail": str(exc)},
        ) from exc
    return VersionsResponse(file_id=file_id, count=len(versions), versions=versions)


@router.get(
    "/logs",
    response_model=LogsResponse,
    dependencies=[Depends(verify_api_key)],
)
def list_logs(service: SyncService = Depends(get_service)) -> LogsResponse:
    logs = service.list_logs()
    return LogsResponse(count=len(logs), logs=logs)


@router.get(
    "/status",
    response_model=StatusResponse,
    dependencies=[Depends(verify_api_key)],
)
def status(service: SyncService = Depends(get_service)) -> StatusResponse:
    return service.status()

