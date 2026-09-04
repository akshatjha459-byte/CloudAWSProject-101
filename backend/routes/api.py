"""
api.py — Module 3 HTTP routes.

Implements the REST contract from docs/module-contracts.md.

Module 6 — Security:
  verify_api_key enforces X-API-Key header on protected endpoints.
  Enforcement is active only when APP_ENV=production (see backend/config.py).
  /health is always public (no authentication required).
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
    """Verify the X-API-Key header when running in production mode.

    In development mode (APP_ENV=development, the default), this dependency
    is a no-op — all protected endpoints are accessible without authentication.
    This is intentional for local testing and pytest.

    In production mode (APP_ENV=production), a non-empty API_KEY must be
    configured and all protected endpoints require a matching header.
    """
    if config.APP_ENV != "production":
        # Development / test mode — authentication is intentionally disabled.
        return
    # Production: API_KEY is guaranteed non-empty by config startup check.
    if not x_api_key or x_api_key != config.API_KEY:
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "error": "unauthorized",
                "detail": "Invalid or missing API key",
            },
        )


def get_service(request: Request) -> SyncService:
    return request.app.state.sync_service


# /health is intentionally public — no verify_api_key dependency.
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
    base_hash: Optional[str] = Form(None),
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
            base_hash=base_hash,
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


from fastapi.responses import Response

@router.get(
    "/files/{file_id}/content",
    responses={404: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
def download_file(
    file_id: int,
    version: Optional[int] = Query(
        default=None,
        description="Application version_number from FILE_VERSIONS; omit for current content.",
    ),
    service: SyncService = Depends(get_service),
) -> Response:
    try:
        content = service.download(file_id, version_number=version)
        return Response(content=content, media_type="application/octet-stream")
    except SyncNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"success": False, "error": "not_found", "detail": str(exc)},
        ) from exc


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
