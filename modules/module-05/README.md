# Module 5 — Amazon RDS Database

## Purpose

Module 5 persists **synchronization metadata** in Amazon RDS (PostgreSQL).

S3 (Module 4) continues to store **file bytes**.  RDS never stores file contents.

```
M3 SyncService
     |
     +--> FileStorage        (memory or S3)
     +--> MetadataRepository
              |
              +-- MemoryMetadataRepository   (default / tests)
              +-- RdsMetadataRepository      (this module)
                     |
                     v
              Amazon RDS PostgreSQL
                 files
                 file_versions
                 sync_logs
                 sync_changes
```

## Entities

| Table | Role |
|---|---|
| `files` | Current logical file state (`FileRecord`) |
| `file_versions` | Application version history (`VersionRecord`); `version_number` is not S3 VersionId |
| `sync_logs` | Synchronization activity (`LogRecord`) |
| `sync_changes` | Change feed for later cloud→local sync (`ChangeRecord`) |

Reference SQL: `database/schema.sql`.  Runtime schema is created by SQLAlchemy
`create_all` (`python -m backend.rds_setup`).

## Configuration

```
METADATA_ADAPTER=rds
RDS_HOST=
RDS_PORT=5432
RDS_DATABASE=
RDS_USERNAME=
RDS_PASSWORD=
RDS_SSLMODE=require
```

Leave `METADATA_ADAPTER` unset or `memory` for local/dev without RDS.
Never commit `RDS_PASSWORD`.

## Initialization

```bash
python -m backend.rds_setup
```

This creates/verifies tables.  It does **not** create the RDS instance.

## AWS Console / manual setup

1. In AWS Academy, create an RDS **PostgreSQL** instance (private if possible).
2. Note host, port (5432), database name, username, and password.
3. Security group: allow the EC2 backend (M3) to connect.  Prefer not making RDS public.
4. Put connection values in `.env` on the backend host (not in Git).
5. Run `python -m backend.rds_setup`.
6. Set `METADATA_ADAPTER=rds` and restart FastAPI.

IAM instance-role details belong to Module 6.

## Tests

Unit tests use an isolated SQLite file (SQLAlchemy).  No AWS RDS required:

```bash
pip install -r backend/requirements.txt
python -m pytest modules/module-05/tests/test_m5.py -v
```

Opt-in real RDS:

```bash
set RUN_RDS_INTEGRATION=1
python -m pytest modules/module-05/tests/test_m5_integration.py -v
```

## Adapter selection

`backend.main.build_metadata_repository` chooses memory vs RDS from
`METADATA_ADAPTER`.  Routes still go `API → SyncService → MetadataRepository`.

## Security

- Credentials only from environment / `.env` (gitignored).
- Default SSL mode for RDS is `require`.
- No file payloads in the database.

## Known limitations

- The RDS *instance* is provisioned in AWS Console, not by this repository.
- SQLite in unit tests is a stand-in dialect; production is PostgreSQL.
- Application auth/IAM policies are Module 6.
