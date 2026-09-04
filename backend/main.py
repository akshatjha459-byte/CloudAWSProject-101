"""
main.py — Module 3 FastAPI application.

Run locally (development):

    uvicorn backend.main:app --host 0.0.0.0 --port 8000

The bind host/port are configurable via BACKEND_HOST / BACKEND_PORT.
This module does not provision EC2 and does not talk to S3 or RDS.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.adapters.repository import MemoryMetadataRepository, MetadataRepository
from backend.adapters.storage import FileStorage, MemoryFileStorage
from backend.config import (
    AWS_REGION,
    METADATA_ADAPTER,
    RDS_DATABASE,
    RDS_HOST,
    RDS_PASSWORD,
    RDS_PORT,
    RDS_SSLMODE,
    RDS_USERNAME,
    S3_BUCKET,
    S3_PREFIX,
    STORAGE_ADAPTER,
)
from backend.routes.api import router
from backend.services.observability import Observability
from backend.services.sync_service import SyncService


def build_file_storage(adapter_name: str) -> tuple[FileStorage, str]:
    """Select the file-content adapter.  Default is still in-memory (M3)."""
    name = (adapter_name or "memory").strip().lower()
    if name == "s3":
        from backend.adapters.s3_storage import S3FileStorage

        return (
            S3FileStorage(bucket=S3_BUCKET, region=AWS_REGION, prefix=S3_PREFIX),
            "s3",
        )
    return MemoryFileStorage(), "memory"


def build_metadata_repository(adapter_name: str) -> tuple[MetadataRepository, str]:
    """Select the metadata adapter.  Default is still in-memory (M3)."""
    name = (adapter_name or "memory").strip().lower()
    if name == "rds":
        from backend.adapters.rds_repository import RdsMetadataRepository

        return (
            RdsMetadataRepository.from_env(
                host=RDS_HOST,
                port=RDS_PORT,
                database=RDS_DATABASE,
                username=RDS_USERNAME,
                password=RDS_PASSWORD,
                sslmode=RDS_SSLMODE,
            ),
            "rds",
        )
    return MemoryMetadataRepository(), "memory"


def create_app(
    *,
    storage=None,
    repository=None,
    storage_adapter_name: str | None = None,
    metadata_adapter_name: str | None = None,
    observability=None,
) -> FastAPI:
    """Application factory so tests can inject adapters."""

    adapter_name = storage_adapter_name or STORAGE_ADAPTER
    if storage is None:
        storage, adapter_name = build_file_storage(adapter_name)

    meta_name = metadata_adapter_name or METADATA_ADAPTER
    if repository is None:
        repository, meta_name = build_metadata_repository(meta_name)

    if observability is None:
        observability = Observability.from_env()

    service = SyncService(
        storage,
        repository,
        storage_adapter_name=adapter_name,
        metadata_adapter_name=meta_name,
        observability=observability,
    )

    app = FastAPI(
        title="Hybrid Cloud File Sync Backend",
        description="Module 3 FastAPI API layer. Storage and metadata are adapter-backed.",
        version="0.3.0",
    )
    app.state.sync_service = service
    app.state.observability = observability
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for item in exc.errors():
            cleaned = dict(item)
            ctx = cleaned.get("ctx")
            if isinstance(ctx, dict):
                cleaned["ctx"] = {key: str(value) for key, value in ctx.items()}
            errors.append(cleaned)
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "validation_error",
                "detail": errors,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return await http_exception_handler(request, exc)
        obs = getattr(request.app.state, "observability", None)
        if obs is not None:
            try:
                obs.on_application_error(error=type(exc).__name__, event="application.error")
            except Exception:
                pass
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "internal_error",
                "detail": str(exc),
            },
        )

    return app


app = create_app()
