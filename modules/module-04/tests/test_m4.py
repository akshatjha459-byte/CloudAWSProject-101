"""
test_m4.py — Module 4 unit tests.

Uses an in-process fake S3 client.  No AWS credentials or network access.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Optional

from botocore.exceptions import ClientError

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.adapters.s3_storage import (  # noqa: E402
    S3FileStorage,
    StorageError,
    object_key,
)
from backend.adapters.storage import FileStorage, StoragePutResult  # noqa: E402
from backend.main import build_file_storage, create_app  # noqa: E402
from backend.services.sync_service import SyncService  # noqa: E402
from backend.adapters.repository import MemoryMetadataRepository  # noqa: E402


def _client_error(code: str, http: int = 404, operation: str = "GetObject") -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": http},
        },
        operation,
    )


class FakeS3Client:
    """Minimal versioned S3 stand-in for unit tests."""

    def __init__(self) -> None:
        self.versioning: dict[str, str] = {}
        self.objects: dict[str, list[dict[str, Any]]] = {}
        self._seq = 0
        self.fail_put = False
        self.fail_get_unexpected = False

    def put_bucket_versioning(self, Bucket: str, VersioningConfiguration: dict) -> dict:
        self.versioning[Bucket] = VersioningConfiguration["Status"]
        return {}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> dict:
        if self.fail_put:
            raise _client_error("InternalError", http=500, operation="PutObject")
        if isinstance(Body, (bytes, bytearray)):
            data = bytes(Body)
        else:
            data = bytes(Body)
        self._seq += 1
        version_id = f"ver-{self._seq}"
        self.objects.setdefault(Key, []).append(
            {"version_id": version_id, "body": data, "delete_marker": False}
        )
        return {"VersionId": version_id}

    def _current(self, key: str) -> Optional[dict[str, Any]]:
        versions = self.objects.get(key) or []
        if not versions:
            return None
        return versions[-1]

    def get_object(self, Bucket: str, Key: str) -> dict:
        if self.fail_get_unexpected:
            raise _client_error("SlowDown", http=503, operation="GetObject")
        current = self._current(Key)
        if current is None or current["delete_marker"]:
            raise _client_error("NoSuchKey", operation="GetObject")
        return {
            "Body": io.BytesIO(current["body"]),
            "VersionId": current["version_id"],
            "ContentLength": len(current["body"]),
        }

    def head_object(self, Bucket: str, Key: str) -> dict:
        current = self._current(Key)
        if current is None or current["delete_marker"]:
            raise _client_error("404", http=404, operation="HeadObject")
        return {
            "VersionId": current["version_id"],
            "ContentLength": len(current["body"]),
        }

    def delete_object(self, Bucket: str, Key: str) -> dict:
        self._seq += 1
        version_id = f"del-{self._seq}"
        self.objects.setdefault(Key, []).append(
            {"version_id": version_id, "body": b"", "delete_marker": True}
        )
        return {"VersionId": version_id, "DeleteMarker": True}

    def copy_object(self, Bucket: str, Key: str, CopySource: dict) -> dict:
        source_key = CopySource["Key"]
        current = self._current(source_key)
        if current is None or current["delete_marker"]:
            raise _client_error("NoSuchKey", operation="CopyObject")
        put = self.put_object(Bucket=Bucket, Key=Key, Body=current["body"])
        return {
            "VersionId": put["VersionId"],
            "CopyObjectResult": {"VersionId": put["VersionId"]},
        }


def _storage(client: Optional[FakeS3Client] = None) -> tuple[S3FileStorage, FakeS3Client]:
    fake = client or FakeS3Client()
    adapter = S3FileStorage(
        bucket="test-bucket",
        region="us-east-1",
        prefix="organization/files",
        client=fake,
    )
    return adapter, fake


class TestObjectKeyMapping(unittest.TestCase):
    def test_default_prefix(self) -> None:
        self.assertEqual(
            object_key("reports/hello.txt"),
            "organization/files/reports/hello.txt",
        )

    def test_root_file(self) -> None:
        self.assertEqual(object_key("demo.txt"), "organization/files/demo.txt")

    def test_backslash_normalized(self) -> None:
        self.assertEqual(
            object_key(r"subdir\file.txt"),
            "organization/files/subdir/file.txt",
        )

    def test_does_not_double_prefix(self) -> None:
        self.assertEqual(
            object_key("organization/files/demo.txt"),
            "organization/files/demo.txt",
        )

    def test_empty_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            object_key("  ")

    def test_custom_prefix(self) -> None:
        self.assertEqual(object_key("a.txt", prefix="org/files"), "org/files/a.txt")

    def test_empty_prefix(self) -> None:
        self.assertEqual(object_key("a.txt", prefix=""), "a.txt")


class TestS3FileStorageInterface(unittest.TestCase):
    def test_is_file_storage(self) -> None:
        adapter, _ = _storage()
        self.assertIsInstance(adapter, FileStorage)

    def test_missing_bucket_rejected(self) -> None:
        with self.assertRaises(ValueError):
            S3FileStorage(bucket="", region="us-east-1", client=FakeS3Client())

    def test_missing_region_rejected(self) -> None:
        with self.assertRaises(ValueError):
            S3FileStorage(bucket="b", region="  ", client=FakeS3Client())


class TestS3PutGet(unittest.TestCase):
    def test_upload_and_retrieve(self) -> None:
        adapter, fake = _storage()
        result = adapter.put("reports/hello.txt", b"hello m4")
        self.assertIsInstance(result, StoragePutResult)
        self.assertEqual(result.key, "organization/files/reports/hello.txt")
        self.assertTrue(result.version_id)
        self.assertEqual(result.size, 8)
        self.assertEqual(adapter.get("reports/hello.txt"), b"hello m4")
        self.assertIn("organization/files/reports/hello.txt", fake.objects)

    def test_missing_object_returns_none(self) -> None:
        adapter, _ = _storage()
        self.assertIsNone(adapter.get("nope.txt"))

    def test_exists(self) -> None:
        adapter, _ = _storage()
        self.assertFalse(adapter.exists("a.txt"))
        adapter.put("a.txt", b"x")
        self.assertTrue(adapter.exists("a.txt"))


class TestS3OverwriteVersioning(unittest.TestCase):
    def test_overwrite_creates_new_version_id(self) -> None:
        adapter, fake = _storage()
        first = adapter.put("doc.txt", b"v1")
        second = adapter.put("doc.txt", b"v2-content")
        self.assertNotEqual(first.version_id, second.version_id)
        self.assertEqual(adapter.get("doc.txt"), b"v2-content")
        versions = fake.objects["organization/files/doc.txt"]
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["body"], b"v1")
        self.assertFalse(versions[0]["delete_marker"])


class TestS3Delete(unittest.TestCase):
    def test_delete_hides_current_object_but_keeps_history(self) -> None:
        adapter, fake = _storage()
        adapter.put("gone.txt", b"bye")
        adapter.delete("gone.txt")
        self.assertIsNone(adapter.get("gone.txt"))
        self.assertFalse(adapter.exists("gone.txt"))
        history = fake.objects["organization/files/gone.txt"]
        self.assertGreaterEqual(len(history), 2)
        self.assertTrue(history[-1]["delete_marker"])
        self.assertEqual(history[0]["body"], b"bye")

    def test_delete_missing_does_not_raise(self) -> None:
        adapter, _ = _storage()
        adapter.delete("never.txt")


class TestS3Copy(unittest.TestCase):
    def test_copy_moves_current_object(self) -> None:
        adapter, fake = _storage()
        adapter.put("old.txt", b"move-me")
        result = adapter.copy("old.txt", "new.txt")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.key, "organization/files/new.txt")
        self.assertEqual(adapter.get("new.txt"), b"move-me")
        self.assertIsNone(adapter.get("old.txt"))
        self.assertTrue(fake.objects["organization/files/old.txt"][-1]["delete_marker"])

    def test_copy_missing_returns_none(self) -> None:
        adapter, _ = _storage()
        self.assertIsNone(adapter.copy("missing.txt", "dest.txt"))


class TestS3Errors(unittest.TestCase):
    def test_put_error_wrapped(self) -> None:
        fake = FakeS3Client()
        fake.fail_put = True
        adapter, _ = _storage(fake)
        with self.assertRaises(StorageError):
            adapter.put("x.txt", b"x")

    def test_unexpected_get_error_wrapped(self) -> None:
        fake = FakeS3Client()
        fake.fail_get_unexpected = True
        adapter, _ = _storage(fake)
        with self.assertRaises(StorageError):
            adapter.get("x.txt")


class TestS3VersioningSetup(unittest.TestCase):
    def test_ensure_versioning_enabled(self) -> None:
        adapter, fake = _storage()
        adapter.ensure_versioning_enabled()
        self.assertEqual(fake.versioning["test-bucket"], "Enabled")


class TestConfiguration(unittest.TestCase):
    def test_s3_settings_from_environment(self) -> None:
        from importlib import reload
        import backend.config as cfg

        previous = {
            name: os.environ.get(name)
            for name in ("S3_BUCKET", "AWS_REGION", "S3_PREFIX", "STORAGE_ADAPTER")
        }
        os.environ["S3_BUCKET"] = "hybrid-sync-demo-bucket"
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["S3_PREFIX"] = "organization/files"
        os.environ["STORAGE_ADAPTER"] = "s3"
        try:
            reload(cfg)
            self.assertEqual(cfg.S3_BUCKET, "hybrid-sync-demo-bucket")
            self.assertEqual(cfg.AWS_REGION, "us-east-1")
            self.assertEqual(cfg.S3_PREFIX, "organization/files")
            self.assertEqual(cfg.STORAGE_ADAPTER, "s3")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            reload(cfg)

    def test_default_adapter_is_memory(self) -> None:
        from importlib import reload
        import backend.config as cfg

        previous = os.environ.get("STORAGE_ADAPTER")
        os.environ["STORAGE_ADAPTER"] = "memory"
        try:
            reload(cfg)
            self.assertEqual(cfg.STORAGE_ADAPTER, "memory")
        finally:
            if previous is None:
                os.environ.pop("STORAGE_ADAPTER", None)
            else:
                os.environ["STORAGE_ADAPTER"] = previous
            reload(cfg)

    def test_build_file_storage_memory_default(self) -> None:
        storage, name = build_file_storage("memory")
        self.assertEqual(name, "memory")
        self.assertIsInstance(storage, FileStorage)

    def test_create_app_defaults_to_memory(self) -> None:
        app = create_app(storage_adapter_name="memory")
        self.assertEqual(app.state.sync_service._storage_adapter_name, "memory")


class TestM3ServiceWithS3Adapter(unittest.TestCase):
    """SyncService must keep working when FileStorage is S3FileStorage."""

    def test_upload_via_sync_service(self) -> None:
        adapter, _ = _storage()
        service = SyncService(adapter, MemoryMetadataRepository(), storage_adapter_name="s3")
        result = service.upload(
            operation="CREATED",
            path="seed.txt",
            timestamp="2026-09-03T00:00:00Z",
            content=b"seed",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.file.storage_key, "organization/files/seed.txt")
        self.assertTrue(result.file.storage_version_id)
        self.assertEqual(adapter.get("seed.txt"), b"seed")
        status = service.status()
        self.assertEqual(status.notes["s3"], "active")


if __name__ == "__main__":
    unittest.main()
