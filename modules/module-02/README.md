# Module 2 — Synchronisation Agent

## Purpose

Module 2 is the local synchronisation agent.

It sits between the local file system (M1) and the FastAPI backend (M3):

```
LOCAL FILE SYSTEM (M1)
        ↓
SYNCHRONISATION AGENT (M2)  ← this module
        ↓
FASTAPI BACKEND (M3)
```

M2 monitors the `SYNC_FOLDER` directory, detects filesystem changes, normalises
them into the contract-defined event structure, and dispatches them to M3 (or,
during development, to the `LoggingEventSender` stub).

## What M2 owns

| File | Description |
|---|---|
| `agent/__init__.py` | Package marker |
| `agent/config.py` | Reads `SYNC_FOLDER` (and `LOG_LEVEL`) from `.env` / environment |
| `agent/hashing.py` | SHA-256 file digest (chunked, stdlib only) |
| `agent/events.py` | `SyncEvent` dataclass + factory helpers; enforces the M1→M2 contract |
| `agent/sender.py` | `EventSender` abstract interface + `LoggingEventSender` stub for M3 |
| `agent/watcher.py` | `watchdog`-based filesystem observer → produces `SyncEvent` objects |
| `agent/agent.py` | Entry point — starts watcher, handles Ctrl-C / SIGTERM |
| `agent/requirements.txt` | Runtime dependency: `watchdog>=3.0.0` |
| `modules/module-02/README.md` | This file |
| `modules/module-02/tests/test_m2.py` | M2 test suite |

## What M2 does NOT own

- The `organization/files/` directory → Module 1
- FastAPI backend → Module 3
- S3 uploads → Module 4
- RDS persistence → Module 5
- IAM / security → Module 6
- Bidirectional sync (cloud → local) → Module 7
- Conflict resolution → Module 8
- CloudWatch / SNS / CloudTrail → Module 9
- Dashboard → Module 10

## Event structure (docs/module-contracts.md §M1→M2)

```json
{
  "operation": "MODIFIED",
  "path": "reports/test.txt",
  "hash": "e3b0c44298fc1c149afb...",
  "size": 1234,
  "timestamp": "2026-09-03T00:00:00Z"
}
```

For `MOVED` events an additional field is present:

```json
{
  "operation": "MOVED",
  "path": "old_name.txt",
  "dest_path": "new_name.txt",
  "hash": null,
  "size": null,
  "timestamp": "2026-09-03T00:00:00Z"
}
```

All paths are **relative to `SYNC_FOLDER`** and use **forward slashes** regardless
of the host OS.

## Configuration

`SYNC_FOLDER` is required.  `BACKEND_URL` is optional until M3 is used.

```
SYNC_FOLDER=./organization/files   # relative to project root
LOG_LEVEL=INFO                     # optional; default INFO
BACKEND_URL=                       # M3 origin; empty → LoggingEventSender
```

Copy `.env.example` to `.env` and set values before running.

## Getting started

```bash
# Install runtime dependency
pip install -r agent/requirements.txt

# Run the agent (watches SYNC_FOLDER, logs events to stdout)
python -m agent.agent

# Or equivalently
python agent/agent.py
```

Create, modify, or delete files inside `organization/files/` and watch events
appear in the console.

## Running the tests

```bash
pip install -r agent/requirements.txt
python -m pytest modules/module-02/tests/test_m2.py -v
```

No AWS credentials, no M3 server, and no network access are required.

## M2 → M3 interface

When `BACKEND_URL` is set, `agent.py` uses `HttpEventSender` from
`agent/http_sender.py` (Module 3).  When it is empty, `LoggingEventSender`
is used so the agent can still run without a backend.

No changes to `watcher.py` or `events.py` are required.

## Dependency

| Package | Version | Purpose |
|---|---|---|
| `watchdog` | `>=3.0.0` | Cross-platform filesystem event detection |

`watchdog` is the only third-party runtime dependency for M2.  Tests use only
the Python standard library plus `pytest` (dev dependency only).

## Known limitations (M2 scope)

- If `BACKEND_URL` is unset, events go to `LoggingEventSender` (logged, not HTTP).
- No durable retry / queue — HTTP failures are logged by `HttpEventSender`.
- `MOVED` events within `SYNC_FOLDER` are supported.  Cross-device moves
  (to a path outside `SYNC_FOLDER`) are treated as `DELETED` + `CREATED` by
  watchdog.
