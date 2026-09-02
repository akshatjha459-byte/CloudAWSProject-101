"""
test_m5_integration.py — Opt-in Module 5 tests against a real RDS instance.

Skipped unless RUN_RDS_INTEGRATION=1 and RDS_HOST / RDS_DATABASE / RDS_USERNAME are set.
Never commit credentials.  These tests are NOT part of the default suite.
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.adapters.rds_repository import RdsMetadataRepository  # noqa: E402


def _integration_enabled() -> bool:
    flag = os.environ.get("RUN_RDS_INTEGRATION", "").strip() in {"1", "true", "TRUE", "yes"}
    return (
        flag
        and bool(os.environ.get("RDS_HOST"))
        and bool(os.environ.get("RDS_DATABASE"))
        and bool(os.environ.get("RDS_USERNAME"))
    )


@unittest.skipUnless(
    _integration_enabled(),
    "opt-in: set RUN_RDS_INTEGRATION=1 with RDS_HOST, RDS_DATABASE, RDS_USERNAME",
)
class TestRealRdsIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = RdsMetadataRepository.from_env(
            host=os.environ["RDS_HOST"],
            port=os.environ.get("RDS_PORT", "5432"),
            database=os.environ["RDS_DATABASE"],
            username=os.environ["RDS_USERNAME"],
            password=os.environ.get("RDS_PASSWORD", ""),
            sslmode=os.environ.get("RDS_SSLMODE", "require"),
        )
        self.path = f"m5-integration/{uuid.uuid4().hex}.txt"

    def test_roundtrip(self) -> None:
        created = self.repo.upsert_file(
            self.path,
            file_hash="00",
            size=1,
            storage_key=self.path,
            storage_version_id="integration",
        )
        found = self.repo.get_file_by_id(created.id)
        self.assertIsNotNone(found)
        self.repo.mark_deleted(created.id)


if __name__ == "__main__":
    unittest.main()
