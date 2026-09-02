"""
rds_setup.py — Module 5 operator helper.

Creates the metadata schema on the configured RDS (or other SQLAlchemy URL).
Does not provision the RDS instance, IAM, or EC2.

Usage:
    python -m backend.rds_setup
"""

from __future__ import annotations

import sys

from backend.adapters.rds_repository import RdsMetadataRepository, build_rds_url
from backend.config import (
    RDS_DATABASE,
    RDS_HOST,
    RDS_PASSWORD,
    RDS_PORT,
    RDS_SSLMODE,
    RDS_USERNAME,
)


def main() -> int:
    try:
        url = build_rds_url(
            host=RDS_HOST,
            port=RDS_PORT,
            database=RDS_DATABASE,
            username=RDS_USERNAME,
            password=RDS_PASSWORD,
            sslmode=RDS_SSLMODE,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        print("Set RDS_HOST, RDS_DATABASE, RDS_USERNAME (and RDS_PASSWORD) in .env.", file=sys.stderr)
        return 1
    repo = RdsMetadataRepository(url, create_schema=True)
    repo.create_schema()
    print(f"Metadata schema created/verified on {RDS_HOST}:{RDS_PORT}/{RDS_DATABASE}")
    print("Tables: files, file_versions, sync_logs, sync_changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
