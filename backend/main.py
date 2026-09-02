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

from backend.adapters.repository import MemoryMetadataRepository
from backend.adapters.storage import MemoryFileStorage
from backend.config import METADATA_ADAPTER, STORAGE_ADAPTER
from backend.routes.api import router
from backend.services.sync_service import SyncService


def create_app(
    *,
    storage=None,
    repository=None,
    storage_adapter_name: str | None = None,
    metadata_adapter_name: str | None = None,
) -> FastAPI:
    """Application factory so tests can inject fresh in-memory adapters."""

    storage = storage or MemoryFileStorage()
    repository = repository or MemoryMetadataRepository()
    service = SyncService(
        storage,
        repository,
        storage_adapter_name=storage_adapter_name or STORAGE_ADAPTER,
        metadata_adapter_name=metadata_adapter_name or METADATA_ADAPTER,
    )

    app = FastAPI(
        title="Hybrid Cloud File Sync Backend",
        description="Module 3 FastAPI API layer. Storage and metadata are adapter-backed.",
        version="0.3.0",
    )
    app.state.sync_service = service
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
