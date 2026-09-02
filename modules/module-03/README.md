# Module 3 — FastAPI Backend / EC2

## Purpose

Module 3 is the HTTP API layer between the local synchronisation agent (M2)
and later AWS storage/database modules:

```
SYNCHRONISATION AGENT (M2)
        ↓  HTTP/HTTPS
FASTAPI BACKEND (M3)          ← this module
       / \
      v   v
    S3   RDS                  ← M4 / M5 (not implemented here)
```

M3 validates requests, exposes the REST contract, and talks to **adapters**
for file content and metadata.  The adapters shipped with M3 are in-memory
development implementations so the API can run without AWS.

## What M3 owns

| Path | Description |
|---|---|
| `backend/main.py` | FastAPI application factory (`create_app`) |
| `backend/config.py` | Host/port/adapter names from environment |
| `backend/models.py` | Pydantic request/response models |
| `backend/routes/api.py` | REST routes from `docs/module-contracts.md` |
| `backend/services/sync_service.py` | Upload/delete/query orchestration |
| `backend/adapters/storage.py` | `FileStorage` interface + `MemoryFileStorage` |
| `backend/adapters/repository.py` | Metadata interface + `MemoryMetadataRepository` |
| `backend/requirements.txt` | FastAPI, uvicorn, python-multipart |
| `agent/http_sender.py` | `HttpEventSender` used by M2 |
| `modules/module-03/tests/test_m3.py` | M3 test suite |

## What M3 does NOT own

- S3 uploads, versioning configuration, or bucket setup → Module 4
- RDS schema, connections, or SQL persistence → Module 5
- IAM roles and security groups → Module 6
- Cloud-to-local apply logic → Module 7
- Conflict resolution → Module 8
- CloudWatch / SNS / CloudTrail → Module 9
- Dashboard UI → Module 10
- EC2 instance provisioning (this module only supplies the application that
  will later run on EC2)

## REST contract

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Backend liveness |
| POST | `/sync/upload` | Local create/modify/move (multipart form) |
| POST | `/sync/delete` | Local delete (JSON `SyncEvent` body) |
| GET | `/sync/changes` | Cloud-side change feed (`?since=` optional) |
| GET | `/files` | File metadata |
| GET | `/files/{id}/versions` | Version records for a file |
| GET | `/logs` | Application synchronisation logs |
| GET | `/status` | Adapter names and counts |

### POST `/sync/upload`

`multipart/form-data` fields:

- `operation` — `CREATED`, `MODIFIED`, or `MOVED`
- `path` — relative path (forward slashes)
- `timestamp` — ISO-8601 UTC (`...Z`)
- `hash` — SHA-256 hex (optional; validated against content when both present)
- `size` — byte size (optional; validated against content when both present)
- `dest_path` — required for `MOVED`
- `file` — file bytes (required for `CREATED` / `MODIFIED`)

### POST `/sync/delete`

JSON body matching M2 `SyncEvent`:

```json
{
  "operation": "DELETED",
  "path": "reports/test.txt",
  "hash": null,
  "size": null,
  "timestamp": "2026-09-03T00:00:00Z"
}
```

## Configuration

```
BACKEND_URL=https://your-ec2-origin.example
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

`BACKEND_URL` is consumed by the **agent**, not hardcoded in source.
Leave it empty to keep `LoggingEventSender` (M2 local-only mode).

Copy `.env.example` to `.env`.  Do not commit `.env`.

## Getting started

```bash
pip install -r backend/requirements.txt
pip install -r agent/requirements.txt

# API server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Agent talking to that backend (set BACKEND_URL in .env)
python -m agent.agent
```

## Running the tests

```bash
pip install -r backend/requirements.txt
pip install pytest httpx
python -m pytest modules/module-03/tests/test_m3.py modules/module-02/tests/test_m2.py -v
python modules/module-01/validate_m1.py
```

No AWS credentials are required.  Storage and metadata stay in memory.

## M2 integration

`agent.http_sender.HttpEventSender` implements `EventSender`.

- Reads `BACKEND_URL` from the environment / `.env` via `agent.config`
- Posts `CREATED`/`MODIFIED`/`MOVED` to `/sync/upload`
- Posts `DELETED` to `/sync/delete`
- Logs HTTP and network errors instead of crashing the watcher
- Accepts an injectable `http_post` callable for tests

## Known limitations (M3 scope)

- File bytes are stored in `MemoryFileStorage`, not S3.
- Metadata/versions/logs live in `MemoryMetadataRepository`, not RDS.
- Process restart loses in-memory state.
- Authentication is not implemented (IAM / app auth belong to M6).
- EC2 provisioning is out of scope; only the FastAPI application is provided.
