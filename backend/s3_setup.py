"""
s3_setup.py — Module 4 operator helper.

Enables S3 Versioning on an existing bucket named by S3_BUCKET.
Does not create IAM, EC2, RDS, or the bucket itself.

Usage:
    python -m backend.s3_setup
"""

from __future__ import annotations

import sys

from backend.adapters.s3_storage import S3FileStorage
from backend.config import AWS_REGION, S3_BUCKET, S3_PREFIX


def main() -> int:
    if not S3_BUCKET or not AWS_REGION:
        print(
            "S3_BUCKET and AWS_REGION must be set in the environment or .env.",
            file=sys.stderr,
        )
        return 1
    storage = S3FileStorage(bucket=S3_BUCKET, region=AWS_REGION, prefix=S3_PREFIX)
    storage.ensure_versioning_enabled()
    print(f"S3 Versioning enabled on bucket {S3_BUCKET} (region {AWS_REGION}).")
    print(f"Object key prefix: {S3_PREFIX or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
