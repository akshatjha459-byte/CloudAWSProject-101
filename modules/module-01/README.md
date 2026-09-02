# Module 1 — Local File System / Organization Server

## Purpose

Module 1 establishes the simulated organization's local file system — the
portable local directory that the synchronization system will operate on.

Its sole responsibility is to provide the `organization/files/` directory as a
configurable, portable data source. Module 1 does **not** watch files, detect
changes, synchronize, or communicate with AWS.

## What M1 owns

| Artifact | Description |
|---|---|
| `organization/files/` | The tracked local directory representing the organization's on-premises files |
| `.env.example` | Project-wide portable configuration template |
| `.gitignore` | Repository ignore rules |
| `modules/module-01/validate_m1.py` | Minimal validation script |

## What M1 does NOT own

- Filesystem watching (→ Module 2)
- Change detection (→ Module 2)
- Synchronization logic (→ Module 2 / 3)
- SHA-256 hashing (→ Module 2)
- FastAPI / EC2 / S3 / RDS / IAM (→ Modules 3–6)
- Bidirectional synchronization (→ Module 7)
- Conflict resolution (→ Module 8)
- Monitoring, alerting (→ Module 9)
- Dashboard (→ Module 10)

## Directory structure

```
project-root/
├── organization/
│   └── files/          ← organization files live here
│       └── .gitkeep    ← keeps the directory tracked when empty
├── .env.example        ← copy to .env and configure
├── .gitignore
└── modules/
    └── module-01/
        ├── README.md   ← this file
        └── validate_m1.py
```

## Configuration

M1 uses a `.env` file (not committed) based on `.env.example`.

The key variable is:

```
SYNC_FOLDER=./organization/files
```

Using a relative path makes the project portable: any developer can clone the
repository and run it without modifying source code.

Do **not** hardcode an absolute path such as `C:\Users\someone\...` or
`/home/username/...`.

## Getting started

```bash
# 1. Clone the repository
git clone https://github.com/akshatjha459-byte/CloudAWSProject-101.git
cd CloudAWSProject-101

# 2. Copy the example env file and review it
copy .env.example .env      # Windows
# or: cp .env.example .env  # Linux/macOS

# 3. Validate Module 1
python modules/module-01/validate_m1.py
```

## Validation

Run:

```bash
python modules/module-01/validate_m1.py
```

Expected output on success:

```
[M1 VALIDATION]
SYNC_FOLDER resolved to: <absolute-path-to>/organization/files
Directory exists: True
Portability check: path is relative in config (OK)
Result: PASS
```

The script exits with code `0` on success and `1` on failure.

## Module contract (M1 → M2)

Module 2 (Synchronization Agent) will:
- Read `SYNC_FOLDER` from the environment or `.env` file.
- Attach a filesystem watcher to `SYNC_FOLDER`.
- Emit normalized events (`CREATED`, `MODIFIED`, `DELETED`, optionally `MOVED`).

M1 guarantees:
- `SYNC_FOLDER` resolves to a real directory.
- The path is configured, not hardcoded.
- No credentials or secrets are stored inside `organization/files/`.
