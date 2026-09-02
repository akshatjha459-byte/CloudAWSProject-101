"""
test_m4_integration.py — Opt-in Module 4 tests against a real S3 bucket.

Skipped unless RUN_S3_INTEGRATION=1 and S3_BUCKET / AWS_REGION are set.
These tests are NOT part of the default suite.
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

from backend.adapters.s3_storage import S3FileStorage  # noqa: E402


def _integration_enabled() -> bool:
    flag = os.environ.get("RUN_S3_INTEGRATION", "").strip() in {"1", "true", "TRUE", "yes"}
    return flag and bool(os.environ.get("S3_BUCKET")) and bool(os.environ.get("AWS_REGION"))


@unittest.skipUnless(_integration_enabled(), "opt-in: set RUN_S3_INTEGRATION=1 with S3_BUCKET and AWS_REGION")
class TestRealS3Integration(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = S3FileStorage(
            bucket=os.environ["S3_BUCKET"],
            region=os.environ["AWS_REGION"],
            prefix=os.environ.get("S3_PREFIX", "organization/files"),
        )
        self.key = f"m4-integration/{uuid.uuid4().hex}.txt"

    def tearDown(self) -> None:
        try:
            self.storage.delete(self.key)
        except Exception:
            pass

    def test_put_get_delete_roundtrip(self) -> None:
        payload = b"m4-integration-payload"
        put = self.storage.put(self.key, payload)
        self.assertTrue(put.version_id)
        self.assertEqual(self.storage.get(self.key), payload)
        self.storage.delete(self.key)
        self.assertIsNone(self.storage.get(self.key))


if __name__ == "__main__":
    unittest.main()
