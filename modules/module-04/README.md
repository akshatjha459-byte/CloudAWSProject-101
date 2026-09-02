# Module 4 — Amazon S3 Storage

## Purpose

Module 4 stores **file content** in Amazon S3.  It implements the existing
M3 `FileStorage` interface (`put`, `get`, `delete`, `copy`, `exists`).

```
M3 SyncService
     |
     v
FileStorage
     |
     +-- MemoryFileStorage   (M3 default / local development)
     +-- S3FileStorage       (this module)
            |
            v
         Amazon S3
```

RDS, IAM, EC2, CloudWatch, CloudTrail, SNS, and the dashboard are out of scope.

## What M4 owns

| Path | Description |
|---|---|
| `backend/adapters/s3_storage.py` | `S3FileStorage` + S3 key mapping |
| `backend/s3_setup.py` | Enable S3 Versioning on an existing bucket |
| `modules/module-04/tests/test_m4.py` | Unit tests with a fake S3 client |
| `modules/module-04/tests/test_m4_integration.py` | Opt-in real-AWS tests |

## Object keys

M3 passes relative paths such as `reports/hello.txt`.  M4 maps them to:

```
{S3_PREFIX}/{relative_path}
```

Default `S3_PREFIX` is `organization/files`, matching Architecture.md:

```
bucket/organization/files/reports/hello.txt
```

## Deletion

`delete()` calls S3 `delete_object` **without** a `VersionId`.  On a
versioned bucket this creates a delete marker: the current object is hidden,
historical versions remain.

## Configuration

```
STORAGE_ADAPTER=s3
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
S3_PREFIX=organization/files
```

Leave `STORAGE_ADAPTER` unset or `memory` to keep the M3 in-memory adapter.

Do **not** put AWS access keys in the repository.  Use the default credential
chain (environment, shared config, or EC2 instance role — IAM is Module 6).

## AWS Console / manual setup

1. Create an S3 bucket in your AWS Academy region (do not commit the name).
2. Enable **Bucket Versioning** on that bucket (or run `python -m backend.s3_setup`).
3. Set `S3_BUCKET`, `AWS_REGION`, and `STORAGE_ADAPTER=s3` on the backend host.
4. Restart the FastAPI process.

`python -m backend.s3_setup` only enables versioning.  It does not create the
bucket, IAM roles, or EC2 instances.

## Tests

```bash
pip install -r backend/requirements.txt
python -m pytest modules/module-04/tests/test_m4.py -v
```

Real AWS is not required.  Opt-in integration tests:

```bash
set RUN_S3_INTEGRATION=1
python -m pytest modules/module-04/tests/test_m4_integration.py -v
```

## Known limitations

- Metadata still uses `MemoryMetadataRepository` until Module 5.
- Bucket creation and IAM least-privilege policies are not automated here.
- Version history in the REST API still comes from the metadata adapter, not
  from listing S3 versions (M5/M8).
