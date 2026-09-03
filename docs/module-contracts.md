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
M8 uses hashes and version information to detect content changes and conflicts.

Normal modification:
1. detect changed hash
2. upload new content
3. create a new S3 version
4. create a FILE_VERSIONS record
5. create a SYNC_LOG record

Conflict:
1. detect conflicting local/cloud versions
2. do not silently overwrite data
3. preserve existing versions where practical
4. record the conflict in RDS
5. create a conflict copy or clearly flag the conflict
6. expose the conflict through status/log/dashboard interfaces

### M9: Monitoring, Logging and Alerting Contract
M9 operates around the backend/AWS layer.

CloudWatch handles meaningful application/system monitoring and logs.
CloudTrail provides AWS API audit activity.
SNS provides failure/security notifications.

Application synchronization logs in RDS and CloudTrail audit records are separate concepts and must not be conflated.

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
