"""
s3_storage.py — Module 4: Amazon S3 file-content adapter.

Implements the M3 ``FileStorage`` interface.  S3 stores file bytes only;
relational metadata remains in the M5 repository (still in-memory until M5).

Object keys follow the architecture prefix:

    {S3_PREFIX}/{relative_path}

Default prefix is ``organization/files``, matching Architecture.md.

Deletion uses a versioned delete (delete marker) so prior S3 versions remain.
Credentials are never hardcoded; boto3 uses the default credential chain.
"""

from __future__ import annotations

from typing import Any, Optional

from botocore.exceptions import ClientError, BotoCoreError

from backend.adapters.storage import FileStorage, StoragePutResult

DEFAULT_S3_PREFIX = "organization/files"


def _is_not_found(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    http = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchVersion"} or http == 404


def object_key(relative_path: str, prefix: str = DEFAULT_S3_PREFIX) -> str:
    """Map an M3 relative path to an S3 object key."""
    relative = relative_path.replace("\\", "/").strip().lstrip("/")
    cleaned_prefix = prefix.replace("\\", "/").strip().strip("/")
    if not relative:
        raise ValueError("storage key/path must not be empty")
    if not cleaned_prefix:
        return relative
    if relative == cleaned_prefix or relative.startswith(cleaned_prefix + "/"):
        return relative
    return f"{cleaned_prefix}/{relative}"


class S3FileStorage(FileStorage):
    """S3-backed ``FileStorage``.  Inject ``client`` in tests."""

    def __init__(
        self,
        bucket: str,
        region: str,
        *,
        prefix: str = DEFAULT_S3_PREFIX,
        client: Any = None,
    ) -> None:
        bucket = (bucket or "").strip()
        region = (region or "").strip()
        if not bucket:
            raise ValueError("S3_BUCKET is required for S3FileStorage")
        if not region:
            raise ValueError("AWS_REGION is required for S3FileStorage")
        self.bucket = bucket
        self.region = region
        self.prefix = prefix.replace("\\", "/").strip().strip("/")
        self._client = client
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self.region)

    def _key(self, relative_path: str) -> str:
        return object_key(relative_path, self.prefix)

    def put(self, key: str, content: bytes) -> StoragePutResult:
        s3_key = self._key(key)
        try:
            response = self._client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=content,
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"S3 put failed for {s3_key}: {exc}") from exc
        version_id = response.get("VersionId") or ""
        return StoragePutResult(key=s3_key, version_id=str(version_id), size=len(content))

    def get(self, key: str) -> Optional[bytes]:
        s3_key = self._key(key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=s3_key)
            body = response["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)
        except ClientError as exc:
            if _is_not_found(exc):
                return None
            raise StorageError(f"S3 get failed for {s3_key}: {exc}") from exc

    def delete(self, key: str) -> None:
        """Delete the current object version (delete marker when versioning is on).

        Historical versions are retained by S3 Versioning.
        """
        s3_key = self._key(key)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=s3_key)
        except ClientError as exc:
            if _is_not_found(exc):
                return
            raise StorageError(f"S3 delete failed for {s3_key}: {exc}") from exc

    def copy(self, source_key: str, dest_key: str) -> Optional[StoragePutResult]:
        source = self._key(source_key)
        dest = self._key(dest_key)
        if not self.exists(source_key):
            return None
        try:
            response = self._client.copy_object(
                Bucket=self.bucket,
                Key=dest,
                CopySource={"Bucket": self.bucket, "Key": source},
            )
        except ClientError as exc:
            if _is_not_found(exc):
                return None
            raise StorageError(f"S3 copy failed {source} -> {dest}: {exc}") from exc
        self.delete(source_key)
        version_id = (
            (response.get("VersionId") or "")
            or (response.get("CopyObjectResult") or {}).get("VersionId")
            or ""
        )
        size = 0
        head = self._head(dest)
        if head is not None:
            size = int(head.get("ContentLength") or 0)
            version_id = version_id or head.get("VersionId") or ""
        return StoragePutResult(key=dest, version_id=str(version_id), size=size)

    def exists(self, key: str) -> bool:
        return self._head(self._key(key)) is not None

    def _head(self, s3_key: str) -> Optional[dict]:
        try:
            return self._client.head_object(Bucket=self.bucket, Key=s3_key)
        except ClientError as exc:
            if _is_not_found(exc):
                return None
            raise StorageError(f"S3 head failed for {s3_key}: {exc}") from exc

    def ensure_versioning_enabled(self) -> None:
        """Enable S3 Versioning on the configured bucket.  Does not create the bucket."""
        try:
            self._client.put_bucket_versioning(
                Bucket=self.bucket,
                VersioningConfiguration={"Status": "Enabled"},
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(
                f"Failed to enable versioning on bucket {self.bucket}: {exc}"
            ) from exc


class StorageError(RuntimeError):
    """Raised when an S3 operation fails for a reason other than 'not found'."""
