"""
test_m5.py — Module 5 unit tests.

Uses an isolated SQLite database via SQLAlchemy.  No AWS RDS credentials.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

from botocore.exceptions import ClientError

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.adapters.rds_repository import (  # noqa: E402
    RdsMetadataRepository,
    build_rds_url,
)
from backend.adapters.repository import MetadataRepository  # noqa: E402
from backend.adapters.s3_storage import S3FileStorage  # noqa: E402
from backend.adapters.storage import MemoryFileStorage  # noqa: E402
from backend.main import build_metadata_repository, create_app  # noqa: E402
from backend.models import DeleteRequest  # noqa: E402
from backend.services.sync_service import SyncService  # noqa: E402


def _client_error(code: str, http: int = 404, operation: str = "GetObject") -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": http},
        },
        operation,
    )


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, list[dict[str, Any]]] = {}
        self._seq = 0

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> dict:
        self._seq += 1
        version_id = f"s3ver-{self._seq}"
        data = bytes(Body)
        self.objects.setdefault(Key, []).append(
            {"version_id": version_id, "body": data, "delete_marker": False}
        )
        return {"VersionId": version_id}

    def _current(self, key: str) -> Optional[dict[str, Any]]:
        versions = self.objects.get(key) or []
        return versions[-1] if versions else None

    def get_object(self, Bucket: str, Key: str) -> dict:
        current = self._current(Key)
        if current is None or current["delete_marker"]:
            raise _client_error("NoSuchKey")
        return {"Body": io.BytesIO(current["body"]), "VersionId": current["version_id"]}

    def head_object(self, Bucket: str, Key: str) -> dict:
        current = self._current(Key)
        if current is None or current["delete_marker"]:
            raise _client_error("404", http=404, operation="HeadObject")
        return {"VersionId": current["version_id"], "ContentLength": len(current["body"])}

    def delete_object(self, Bucket: str, Key: str) -> dict:
        self._seq += 1
        self.objects.setdefault(Key, []).append(
            {"version_id": f"del-{self._seq}", "body": b"", "delete_marker": True}
        )
        return {"DeleteMarker": True}

    def copy_object(self, Bucket: str, Key: str, CopySource: dict) -> dict:
        source = self._current(CopySource["Key"])
        if source is None or source["delete_marker"]:
            raise _client_error("NoSuchKey", operation="CopyObject")
        put = self.put_object(Bucket=Bucket, Key=Key, Body=source["body"])
        return {"VersionId": put["VersionId"], "CopyObjectResult": {"VersionId": put["VersionId"]}}


class _RdsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        handle.close()
        self._db_path = handle.name
        self.repo = RdsMetadataRepository(f"sqlite:///{self._db_path}")

    def tearDown(self) -> None:
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def _reopen(self) -> RdsMetadataRepository:
        return RdsMetadataRepository(f"sqlite:///{self._db_path}", create_schema=False)


class TestInterface(_RdsTestCase):
    def test_is_metadata_repository(self) -> None:
        self.assertIsInstance(self.repo, MetadataRepository)


class TestFiles(_RdsTestCase):
    def test_create_and_get_by_id_and_path(self) -> None:
        created = self.repo.upsert_file(
            "reports/a.txt",
            file_hash="abc",
            size=3,
            storage_key="organization/files/reports/a.txt",
            storage_version_id="s3ver-1",
            timestamp="2026-09-03T00:00:00Z",
        )
        self.assertGreater(created.id, 0)
        self.assertEqual(created.filename, "a.txt")
        self.assertEqual(created.current_version, 0)
        by_id = self.repo.get_file_by_id(created.id)
        by_path = self.repo.get_file_by_path("reports/a.txt")
        self.assertIsNotNone(by_id)
        self.assertIsNotNone(by_path)
        assert by_id is not None and by_path is not None
        self.assertEqual(by_id.storage_key, "organization/files/reports/a.txt")
        self.assertEqual(by_path.storage_version_id, "s3ver-1")

    def test_list_files(self) -> None:
        self.repo.upsert_file("a.txt", file_hash="h", size=1, storage_key="a", storage_version_id="1")
        self.repo.upsert_file("b.txt", file_hash="h", size=1, storage_key="b", storage_version_id="1")
        files = self.repo.list_files()
        self.assertEqual(len(files), 2)

    def test_upsert_updates_same_path(self) -> None:
        first = self.repo.upsert_file(
            "x.txt", file_hash="old", size=1, storage_key="k", storage_version_id="v1"
        )
        second = self.repo.upsert_file(
            "x.txt", file_hash="new", size=4, storage_key="k", storage_version_id="v2"
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.current_hash, "new")
        self.assertEqual(second.storage_version_id, "v2")
        self.assertEqual(len(self.repo.list_files()), 1)

    def test_rename_file(self) -> None:
        created = self.repo.upsert_file(
            "old.txt", file_hash="h", size=1, storage_key="k", storage_version_id="v"
        )
        renamed = self.repo.rename_file(created.id, "new.txt", timestamp="2026-09-03T01:00:00Z")
        self.assertEqual(renamed.relative_path, "new.txt")
        self.assertIsNone(self.repo.get_file_by_path("old.txt"))
        self.assertIsNotNone(self.repo.get_file_by_path("new.txt"))

    def test_mark_deleted_keeps_row(self) -> None:
        created = self.repo.upsert_file(
            "gone.txt", file_hash="h", size=1, storage_key="k", storage_version_id="v"
        )
        deleted = self.repo.mark_deleted(created.id, timestamp="2026-09-03T02:00:00Z")
        self.assertTrue(deleted.deleted)
        self.assertEqual(deleted.status, "deleted")
        still = self.repo.get_file_by_id(created.id)
        self.assertIsNotNone(still)
        assert still is not None
        self.assertTrue(still.deleted)
        self.assertEqual(len(self.repo.list_files()), 1)


class TestVersions(_RdsTestCase):
    def test_version_numbering_and_s3_id(self) -> None:
        file_row = self.repo.upsert_file(
            "doc.txt", file_hash="h1", size=2, storage_key="k", storage_version_id="s3-a"
        )
        v1 = self.repo.add_version(
            file_row.id,
            operation="CREATED",
            file_hash="h1",
            size=2,
            storage_version_id="s3-a",
        )
        v2 = self.repo.add_version(
            file_row.id,
            operation="MODIFIED",
            file_hash="h2",
            size=3,
            storage_version_id="s3-b",
        )
        self.assertEqual(v1.version_number, 1)
        self.assertEqual(v2.version_number, 2)
        self.assertNotEqual(v1.storage_version_id, v2.storage_version_id)
        refreshed = self.repo.get_file_by_id(file_row.id)
        assert refreshed is not None
        self.assertEqual(refreshed.current_version, 2)
        versions = self.repo.list_versions(file_row.id)
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[1].storage_version_id, "s3-b")


class TestLogs(_RdsTestCase):
    def test_create_and_list_logs_with_error(self) -> None:
        log_ok = self.repo.add_log(
            path="a.txt",
            operation="CREATED",
            status="SUCCESS",
            file_id=None,
        )
        log_err = self.repo.add_log(
            path="b.txt",
            operation="CREATED",
            status="FAILED",
            error_message="hash mismatch",
        )
        logs = self.repo.list_logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(log_ok.status, "SUCCESS")
        self.assertEqual(log_err.error_message, "hash mismatch")
        self.assertEqual(logs[1].error_message, "hash mismatch")


class TestChanges(_RdsTestCase):
    def test_create_list_and_since_filter(self) -> None:
        self.repo.add_change(
            path="a.txt",
            operation="CREATED",
            timestamp="2026-09-03T00:00:00Z",
        )
        self.repo.add_change(
            path="b.txt",
            operation="MODIFIED",
            timestamp="2026-09-03T02:00:00Z",
        )
        all_changes = self.repo.list_changes()
        self.assertEqual(len(all_changes), 2)
        later = self.repo.list_changes(since="2026-09-03T01:00:00Z")
        self.assertEqual(len(later), 1)
        self.assertEqual(later[0].path, "b.txt")
        none = self.repo.list_changes(since="2099-01-01T00:00:00Z")
        self.assertEqual(none, [])


class TestPersistence(_RdsTestCase):
    def test_data_survives_new_repository_instance(self) -> None:
        created = self.repo.upsert_file(
            "persist.txt",
            file_hash="deadbeef",
            size=9,
            storage_key="organization/files/persist.txt",
            storage_version_id="s3-persist",
            timestamp="2026-09-03T00:00:00Z",
        )
        self.repo.add_version(
            created.id,
            operation="CREATED",
            file_hash="deadbeef",
            size=9,
            storage_version_id="s3-persist",
            timestamp="2026-09-03T00:00:00Z",
        )
        self.repo.add_log(
            path="persist.txt",
            operation="CREATED",
            status="SUCCESS",
            file_id=created.id,
            timestamp="2026-09-03T00:00:00Z",
        )
        self.repo.add_change(
            path="persist.txt",
            operation="CREATED",
            file_id=created.id,
            timestamp="2026-09-03T00:00:00Z",
        )
        other = self._reopen()
        file_row = other.get_file_by_path("persist.txt")
        self.assertIsNotNone(file_row)
        assert file_row is not None
        self.assertEqual(file_row.current_hash, "deadbeef")
        self.assertEqual(file_row.storage_version_id, "s3-persist")
        self.assertEqual(file_row.current_version, 1)
        self.assertEqual(len(other.list_versions(file_row.id)), 1)
        self.assertEqual(len(other.list_logs()), 1)
        self.assertEqual(len(other.list_changes()), 1)


class TestConfiguration(unittest.TestCase):
    def test_build_rds_url_encodes_password(self) -> None:
        url = build_rds_url(
            host="db.example.internal",
            port=5432,
            database="syncdb",
            username="syncuser",
            password="p@ss/w:rd",
            sslmode="require",
        )
        self.assertTrue(url.startswith("postgresql+psycopg2://"))
        self.assertIn("db.example.internal:5432/syncdb", url)
        self.assertIn("sslmode=require", url)
        self.assertNotIn("p@ss/w:rd", url)

    def test_missing_host_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_rds_url(host="", port=5432, database="db", username="u", password="p")

    def test_env_config_names(self) -> None:
        from importlib import reload
        import backend.config as cfg

        keys = (
            "METADATA_ADAPTER",
            "RDS_HOST",
            "RDS_PORT",
            "RDS_DATABASE",
            "RDS_USERNAME",
            "RDS_PASSWORD",
            "RDS_SSLMODE",
        )
        previous = {name: os.environ.get(name) for name in keys}
        os.environ["METADATA_ADAPTER"] = "rds"
        os.environ["RDS_HOST"] = "rds.example.internal"
        os.environ["RDS_PORT"] = "5432"
        os.environ["RDS_DATABASE"] = "hybrid_sync"
        os.environ["RDS_USERNAME"] = "appuser"
        os.environ["RDS_PASSWORD"] = "not-a-real-secret-for-repo"
        os.environ["RDS_SSLMODE"] = "require"
        try:
            reload(cfg)
            self.assertEqual(cfg.METADATA_ADAPTER, "rds")
            self.assertEqual(cfg.RDS_HOST, "rds.example.internal")
            self.assertEqual(cfg.RDS_DATABASE, "hybrid_sync")
            self.assertEqual(cfg.RDS_SSLMODE, "require")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            reload(cfg)

    def test_build_metadata_repository_memory_default(self) -> None:
        repo, name = build_metadata_repository("memory")
        self.assertEqual(name, "memory")
        self.assertIsInstance(repo, MetadataRepository)

    def test_create_app_defaults_to_memory_metadata(self) -> None:
        app = create_app(storage_adapter_name="memory", metadata_adapter_name="memory")
        self.assertEqual(app.state.sync_service._metadata_adapter_name, "memory")


class TestM3Integration(_RdsTestCase):
    def test_sync_service_with_memory_storage_and_rds(self) -> None:
        service = SyncService(
            MemoryFileStorage(),
            self.repo,
            storage_adapter_name="memory",
            metadata_adapter_name="rds",
        )
        result = service.upload(
            operation="CREATED",
            path="seed.txt",
            timestamp="2026-09-03T00:00:00Z",
            content=b"seed",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.file.current_version, 1)
        persisted = self._reopen()
        self.assertIsNotNone(persisted.get_file_by_path("seed.txt"))
        self.assertEqual(len(persisted.list_versions(result.file.id)), 1)
        self.assertEqual(len(persisted.list_changes()), 1)
        status = service.status()
        self.assertEqual(status.notes["rds"], "active")

    def test_sync_service_with_s3_double_and_rds(self) -> None:
        storage = S3FileStorage(
            bucket="test-bucket",
            region="us-east-1",
            client=FakeS3Client(),
        )
        service = SyncService(
            storage,
            self.repo,
            storage_adapter_name="s3",
            metadata_adapter_name="rds",
        )
        uploaded = service.upload(
            operation="CREATED",
            path="combo.txt",
            timestamp="2026-09-03T00:00:00Z",
            content=b"combo",
        )
        self.assertTrue(uploaded.file.storage_key.endswith("combo.txt"))
        self.assertTrue(uploaded.file.storage_version_id)
        self.assertEqual(storage.get("combo.txt"), b"combo")
        service.delete(
            DeleteRequest(
                operation="DELETED",
                path="combo.txt",
                timestamp="2026-09-03T00:05:00Z",
            )
        )
        other = self._reopen()
        row = other.get_file_by_path("combo.txt")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertTrue(row.deleted)
        versions = other.list_versions(row.id)
        self.assertGreaterEqual(len(versions), 2)
        self.assertEqual(versions[-1].operation, "DELETED")


if __name__ == "__main__":
    unittest.main()
