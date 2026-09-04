# Module Contracts

This document defines the interfaces between the 10 project modules. Antigravity must implement modules against these contracts and must not silently change an interface without updating this document.

## Module Map

1. Local File System / Organization Server
2. Synchronization Agent
3. FastAPI Backend / EC2
4. Amazon S3 Storage
5. Amazon RDS Database
6. AWS IAM / Security
7. Bidirectional Synchronization
8. Versioning & Conflict Handling
9. Monitoring, Logging & Alerting
10. Frontend Dashboard

**Module boundary rule:** AWS infrastructure deployment and verification are part of completing M6's security contract. They do not create a separate M7. M7 remains **Bidirectional Synchronization**.

## Connection Contracts

### M1 -> M2: Local File Events
M1 exposes filesystem activity to M2. M2 must receive normalized events for CREATED, MODIFIED, DELETED, and preferably MOVED/RENAMED.

Minimum event fields:
- operation
- path (relative to configured sync folder)
- hash (SHA-256 when applicable)
- size
- timestamp

M1 must remain configurable and portable; no machine-specific absolute paths.

### M2 <-> M3: Agent/API Contract
M2 communicates with M3 over HTTP/HTTPS REST APIs.

M2 sends synchronization requests containing file event metadata and, for upload operations, file content.

M3 provides at minimum:
- GET /health
- POST /sync/upload
- POST /sync/delete
- GET /sync/changes
- GET /files
- GET /files/{id}/content
- GET /files/{id}/versions
- GET /logs
- GET /status

M3 returns explicit success/failure information. Authentication/authorization must be enforced according to the implemented security design.

### M3 -> M4: Backend/S3 Contract
M3 is the controlled application layer for S3 operations.

M4 stores actual file content. S3 Versioning must be enabled.

M3 may:
- upload/update objects
- retrieve objects
- process deletion according to the documented deletion strategy
- obtain/use S3 version information

RDS, not S3, remains the source for relational synchronization metadata.

### M3 <-> M5: Backend/RDS Contract
M5 stores metadata rather than full file contents.

Minimum logical entities:
- FILES
- FILE_VERSIONS
- SYNC_LOGS

M3 creates/updates these records after synchronization operations and reads them for status, history, and logs.

### M6 -> AWS Resources: Security Contract
M6 defines and verifies the AWS security boundary.

M6 completion requires both the local security implementation and real-AWS deployment verification. The implementation must use an EC2 IAM role/instance profile rather than hardcoded AWS access keys, follow least privilege, and keep RDS inaccessible from the public internet.

The EC2-to-S3 policy must be restricted to the actual project bucket and only the S3 actions required by the application. Infrastructure-management permissions such as bucket versioning configuration are not runtime permissions.

The application may use API-key authentication between the Sync Agent and EC2. This is an application-level security layer and is separate from AWS IAM.

M6 controls AWS resource permissions and network security; application-level roles are handled separately by the application.

### M7: Bidirectional Synchronization Contract
M7 coordinates both directions:
- LOCAL -> CLOUD
- CLOUD -> LOCAL

For cloud-to-local synchronization, M2 periodically asks M3 for changes since its last known synchronization state. M3 returns applicable cloud changes; M2 downloads and applies them locally.

Local synchronization state must track enough information to prevent repeated processing.

### M8: Versioning and Conflict Contract
M8 extends the framework with object versioning, recoverable history, and deterministic conflict detection and preservation.

Endpoints & Parameters:
- `POST /sync/upload`: Supports optional `base_hash` form field representing the last known synced SHA-256 hash.
- `GET /files/{file_id}/versions`: Returns `VersionsResponse` containing file ID, version count, and list of `VersionRecord` items (`id`, `file_id`, `version_number`, `hash`, `size`, `operation`, `source`, `storage_version_id`, `created_at`, `is_conflict`).
- `GET /files/{file_id}/content?version={n}`: Downloads specific historical version content from storage.
- `GET /status`: Reports `conflict_count` across all active files.

Normal modification flow:
1. Client computes SHA-256 hash and dispatches event with `base_hash`.
2. Backend identifies existing file by path; if content matches, returns `idempotent=True`.
3. New content stored in S3 via existing adapter; S3 `VersionId` captured.
4. RDS updates `files.current_hash`, `files.size`, and increments `files.current_version`.
5. `file_versions` record added with `version_number`, `operation='MODIFIED'`, `storage_version_id`.
6. Success logged to `sync_logs` and published to `sync_changes`.

Conflict handling (Zero Silent Overwrite):
1. **Detection:** Deterministic 3-way check: `local_hash != cloud_hash AND base_hash != cloud_hash AND base_hash != local_hash`.
2. **Preservation:** Canonical file remains intact with status updated to `'conflict'`.
3. **Conflict Copy:** Conflicting local payload saved to S3 and registered in RDS at `{stem}.conflict-{local_hash[:12]}{ext}`.
4. **Versioning:** Sibling file record created with version record (`operation='CONFLICT'`, `is_conflict=True`).
5. **Logging:** Both original path and conflict copy path logged to `sync_logs` with `operation='CONFLICT'`.
6. **Agent Poller:** Cloud poller checks for local divergence against `SyncState` before applying cloud changes, creating local conflict copies if needed.

### M9: Monitoring, Logging and Alerting Contract
M9 operates around the backend/AWS layer without changing the M1–M8 sync protocol.

Structured application logs (JSON) and RDS `sync_logs` record file create/modify/delete, sync success/failure, conflicts, authentication failures, and unexpected errors. Secrets are never logged.

CloudWatch (`CloudAWSProject/Sync`) records `SyncOperations`, `SyncSuccess`, `SyncFailure`, `ConflictEvents`, `ApplicationErrors`, and `AuthFailures`. Metrics use the EC2 instance role.

SNS publishes only for defined conditions: repeated sync failures (threshold), unhandled critical application errors, and repeated production authentication failures. Successful syncs do not send SNS messages.

CloudTrail remains AWS API audit activity at the account level. It is not a substitute for `SYNC_LOGS`.

CloudWatch and SNS failures must not fail synchronization. `GET /health` and `GET /status` keep their existing fields; status `notes` may include monitoring flags.


### M10 <-> M3: Dashboard/API Contract
M10 communicates with M3 through the REST API. M10 must not connect directly to RDS.

The dashboard should display, where implemented:
- system health
- file count/status
- recent synchronization activity
- version history
- synchronization logs
- conflicts

## Core Dependency Chain

M1 -> M2 -> M3 -> M4 + M5

M6 supplies AWS permissions and security controls around the deployed cloud resources.
M7 and M8 extend the synchronization/versioning behavior across M2/M3/M4/M5.
M9 monitors and alerts around the system.
M10 reads project state through M3.

## Implementation Rule

Before implementing a module, inspect the existing interfaces in this document and the current repository. Do not redesign another module's interface implicitly. If an interface must change, update this document first and ensure dependent modules remain compatible.
