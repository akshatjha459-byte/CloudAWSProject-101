"""
rds_repository.py — Module 5: RDS-backed MetadataRepository.

Implements the M3 ``MetadataRepository`` contract with SQLAlchemy.
PostgreSQL (Amazon RDS) is the production dialect; SQLite is used in unit tests.

File bytes are never stored here.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.adapters.rds_models import Base, ChangeRow, FileRow, LogRow, VersionRow
from backend.adapters.repository import MetadataRepository, _filename, _utc_now
from backend.models import ChangeRecord, FileRecord, LogRecord, VersionRecord


def build_rds_url(
    *,
    host: str,
    port: str | int,
    database: str,
    username: str,
    password: str,
    sslmode: str = "require",
) -> str:
    """Build a SQLAlchemy PostgreSQL URL.  Password is URL-encoded."""
    host = (host or "").strip()
    database = (database or "").strip()
    username = (username or "").strip()
    if not host or not database or not username:
        raise ValueError("RDS_HOST, RDS_DATABASE, and RDS_USERNAME are required")
    user = quote_plus(username)
    pwd = quote_plus(password or "")
    port_s = str(port or "5432").strip() or "5432"
    mode = (sslmode or "require").strip() or "require"
    return (
        f"postgresql+psycopg2://{user}:{pwd}@{host}:{port_s}/{database}"
        f"?sslmode={quote_plus(mode)}"
    )


def _to_file(row: FileRow) -> FileRecord:
    return FileRecord(
        id=row.id,
        filename=row.filename,
        relative_path=row.relative_path,
        current_version=row.current_version,
        current_hash=row.current_hash,
        size=row.size,
        status=row.status,
        deleted=row.deleted,
        created_at=row.created_at,
        updated_at=row.updated_at,
        storage_key=row.storage_key,
        storage_version_id=row.storage_version_id,
    )


def _to_version(row: VersionRow) -> VersionRecord:
    return VersionRecord(
        id=row.id,
        file_id=row.file_id,
        version_number=row.version_number,
        hash=row.hash,
        size=row.size,
        operation=row.operation,
        source=row.source,
        storage_version_id=row.storage_version_id,
        created_at=row.created_at,
        is_conflict=row.operation == "CONFLICT",
    )


def _to_log(row: LogRow) -> LogRecord:
    return LogRecord(
        id=row.id,
        file_id=row.file_id,
        path=row.path,
        operation=row.operation,
        source=row.source,
        destination=row.destination,
        status=row.status,
        error_message=row.error_message,
        timestamp=row.timestamp,
    )


def _to_change(row: ChangeRow) -> ChangeRecord:
    return ChangeRecord(
        id=row.id,
        file_id=row.file_id,
        path=row.path,
        dest_path=row.dest_path,
        operation=row.operation,
        hash=row.hash,
        size=row.size,
        version_number=row.version_number,
        timestamp=row.timestamp,
    )


class RdsMetadataRepository(MetadataRepository):
    """Persistent metadata repository for Amazon RDS PostgreSQL (or SQLite in tests)."""

    def __init__(
        self,
        database_url: str,
        *,
        engine: Engine | None = None,
        create_schema: bool = True,
    ) -> None:
        if engine is not None:
            self._engine = engine
        else:
            connect_args = {}
            if database_url.startswith("sqlite"):
                connect_args["check_same_thread"] = False
            self._engine = create_engine(database_url, future=True, connect_args=connect_args)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False, future=True)
        if create_schema:
            Base.metadata.create_all(self._engine)

    @classmethod
    def from_env(
        cls,
        *,
        host: str,
        port: str | int,
        database: str,
        username: str,
        password: str,
        sslmode: str = "require",
    ) -> "RdsMetadataRepository":
        url = build_rds_url(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            sslmode=sslmode,
        )
        return cls(url)

    def create_schema(self) -> None:
        Base.metadata.create_all(self._engine)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_file_by_path(self, relative_path: str) -> Optional[FileRecord]:
        with self._session() as session:
            row = session.scalar(select(FileRow).where(FileRow.relative_path == relative_path))
            return _to_file(row) if row is not None else None

    def get_file_by_id(self, file_id: int) -> Optional[FileRecord]:
        with self._session() as session:
            row = session.get(FileRow, file_id)
            return _to_file(row) if row is not None else None

    def list_files(self) -> list[FileRecord]:
        with self._session() as session:
            rows = session.scalars(select(FileRow).order_by(FileRow.id)).all()
            return [_to_file(r) for r in rows]

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
        with self._session() as session:
            row = session.scalar(select(FileRow).where(FileRow.relative_path == relative_path))
            if row is None:
                row = FileRow(
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
                session.add(row)
                session.flush()
            else:
                row.filename = _filename(relative_path)
                row.current_hash = file_hash
                row.size = size
                row.status = "deleted" if deleted else "synced"
                row.deleted = deleted
                row.updated_at = now
                row.storage_key = storage_key
                row.storage_version_id = storage_version_id
            session.flush()
            return _to_file(row)

    def rename_file(self, file_id: int, new_path: str, timestamp: Optional[str] = None) -> FileRecord:
        now = timestamp or _utc_now()
        with self._session() as session:
            row = session.get(FileRow, file_id)
            if row is None:
                raise KeyError(f"file {file_id} not found")
            row.relative_path = new_path
            row.filename = _filename(new_path)
            row.updated_at = now
            row.deleted = False
            row.status = "synced"
            session.flush()
            return _to_file(row)

    def mark_deleted(self, file_id: int, timestamp: Optional[str] = None) -> FileRecord:
        now = timestamp or _utc_now()
        with self._session() as session:
            row = session.get(FileRow, file_id)
            if row is None:
                raise KeyError(f"file {file_id} not found")
            row.deleted = True
            row.status = "deleted"
            row.updated_at = now
            session.flush()
            return _to_file(row)

    def set_file_status(
        self,
        file_id: int,
        status: str,
        timestamp: Optional[str] = None,
    ) -> FileRecord:
        now = timestamp or _utc_now()
        with self._session() as session:
            row = session.get(FileRow, file_id)
            if row is None:
                raise KeyError(f"file {file_id} not found")
            row.status = status
            row.updated_at = now
            session.flush()
            return _to_file(row)

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
        now = timestamp or _utc_now()
        with self._session() as session:
            file_row = session.get(FileRow, file_id)
            if file_row is None:
                raise KeyError(f"file {file_id} not found")
            version_number = file_row.current_version + 1
            version = VersionRow(
                file_id=file_id,
                version_number=version_number,
                hash=file_hash,
                size=size,
                operation=operation,
                source=source,
                storage_version_id=storage_version_id,
                created_at=now,
            )
            session.add(version)
            file_row.current_version = version_number
            file_row.updated_at = now
            session.flush()
            return _to_version(version)

    def list_versions(self, file_id: int) -> list[VersionRecord]:
        with self._session() as session:
            rows = session.scalars(
                select(VersionRow)
                .where(VersionRow.file_id == file_id)
                .order_by(VersionRow.version_number, VersionRow.id)
            ).all()
            return [_to_version(r) for r in rows]

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
        with self._session() as session:
            row = LogRow(
                file_id=file_id,
                path=path,
                operation=operation,
                source=source,
                destination=destination,
                status=status,
                error_message=error_message,
                timestamp=timestamp or _utc_now(),
            )
            session.add(row)
            session.flush()
            return _to_log(row)

    def list_logs(self) -> list[LogRecord]:
        with self._session() as session:
            rows = session.scalars(select(LogRow).order_by(LogRow.id)).all()
            return [_to_log(r) for r in rows]

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
        with self._session() as session:
            row = ChangeRow(
                file_id=file_id,
                path=path,
                dest_path=dest_path,
                operation=operation,
                hash=file_hash,
                size=size,
                version_number=version_number,
                timestamp=timestamp or _utc_now(),
            )
            session.add(row)
            session.flush()
            return _to_change(row)

    def list_changes(self, since: Optional[str] = None) -> list[ChangeRecord]:
        with self._session() as session:
            stmt = select(ChangeRow).order_by(ChangeRow.id)
            if since:
                stmt = stmt.where(ChangeRow.timestamp > since)
            rows = session.scalars(stmt).all()
            return [_to_change(r) for r in rows]
