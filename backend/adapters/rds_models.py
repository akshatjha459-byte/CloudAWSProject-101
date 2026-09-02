"""
rds_models.py — Module 5 SQLAlchemy tables for RDS metadata.

These tables store information ABOUT files, never file bytes.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FileRow(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("relative_path", name="uq_files_relative_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="synced")
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_version_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    versions: Mapped[list["VersionRow"]] = relationship(back_populates="file")


class VersionRow(Base):
    __tablename__ = "file_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    storage_version_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    file: Mapped[FileRow] = relationship(back_populates="versions")


class LogRow(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    destination: Mapped[str] = mapped_column(String(64), nullable=False, default="backend")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


class ChangeRow(Base):
    __tablename__ = "sync_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    dest_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
