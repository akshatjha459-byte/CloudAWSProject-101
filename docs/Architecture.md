# HYBRID CLOUD FILE SYNCHRONIZATION AND SECURE DATA MIGRATION FRAMEWORK USING AMAZON WEB SERVICES

## PROJECT MASTER ARCHITECTURE AND IMPLEMENTATION PLAN

**Version:** 1.0  
**Project Duration:** 5 Days  
**Primary Developer:** Akshat Jha  
**Development Strategy:** ChatGPT = Architecture / Project Log / Technical Guidance  
Antigravity = Implementation / Coding Agent  
**Cloud Platform:** AWS Academy  
**Repository:** GitHub

---

## 1. PROJECT PURPOSE

This project implements a functional hybrid-cloud file synchronization system.

The core problem being solved is:

Organizations may continue to use on-premises/local file servers while also wanting cloud storage, remote accessibility, backup, versioning, monitoring, and secure cloud integration.

The system therefore maintains a synchronized relationship between:

```text
ORGANIZATION LOCAL FILE SYSTEM
          ↕
    SYNCHRONIZATION AGENT
          ↕
        AWS CLOUD
```

The AWS environment will provide:

- **Amazon S3** → actual cloud file storage
- **Amazon RDS** → metadata, versions, synchronization logs
- **Amazon EC2** → backend/API and cloud-side compute
- **AWS IAM** → access control and permissions
- **CloudWatch** → monitoring and system health
- **CloudTrail** → AWS activity/audit logging
- **Amazon SNS** → failure/security notifications

The approved project proposal describes the system as an incremental, event-driven hybrid migration/synchronization framework rather than a one-time migration system.

The implementation must therefore demonstrate actual file synchronization and not merely demonstrate uploading files manually to S3.

---

## 2. CORE DESIGN PRINCIPLE

The most important conceptual distinction in this project is:

> **S3 stores FILE CONTENT.**
>
> **RDS stores INFORMATION ABOUT FILES.**
>
> **RDS is NOT the cloud copy of the organization's files.**

The architecture is therefore:

```text
LOCAL FILE SYSTEM
      |
      | file operations
      v
SYNCHRONIZATION AGENT
      |
      | HTTP/API
      v
EC2 BACKEND
   /       \
  /         \
 v           v
S3          RDS
files       metadata/history/logs
```

Monitoring and security operate around these components:

```text
IAM        → permissions
CloudWatch → health/metrics
CloudTrail → AWS audit trail
SNS        → alerts
```

---

## 3. HIGH-LEVEL ARCHITECTURE

The complete system should conceptually look like:

```text
                         INTERNET
                            |
                            |
                  +---------v----------+
                  |      AWS CLOUD     |
                  |                    |
                  |       EC2         |
                  |  +---------------+ |
                  |  | FastAPI       | |
                  |  | Backend       | |
                  |  +-------+-------+ |
                  |          |         |
                  |     +----+----+    |
                  |     |         |    |
                  |     v         v    |
                  |    S3        RDS   |
                  |  FILES     DATABASE |
                  |                    |
                  |  CloudWatch        |
                  |  CloudTrail        |
                  |  SNS               |
                  |  IAM               |
                  +---------^----------+
                            |
                            |
                       HTTP/HTTPS API
                            |
                  +---------+----------+
                  | ORGANIZATION /     |
                  | LOCAL MACHINE      |
                  |                    |
                  | organization/      |
                  |     files/         |
                  |                    |
                  |       ↕            |
                  | Synchronization    |
                  |      Agent         |
                  +--------------------+
```

For the project demonstration, the “organization server” will be represented by a directory on a laptop.

This is intentional.

A real enterprise deployment could place the synchronization agent on an actual on-premises file server. For this student implementation, the local filesystem of a laptop acts as the simulated on-premises server.

---

## 4. WHY THE LOCAL AGENT EXISTS

AWS cannot simply assume that it can access arbitrary files on an organization's private computer.

The synchronization agent is therefore the bridge between the local environment and AWS.

The agent is responsible for:

1. Monitoring a local directory.
2. Detecting file creation.
3. Detecting file modification.
4. Detecting file deletion.
5. Detecting file movement/rename where practical.
6. Calculating file hashes.
7. Sending synchronization events to the backend.
8. Downloading cloud-side changes.
9. Maintaining local synchronization state.
10. Handling temporary failures.
11. Reporting synchronization status.

The agent is therefore the primary component implementing the “hybrid synchronization” portion of the project.

---

## 5. LOCAL DIRECTORY STRUCTURE

The client/organization side should use a predictable directory:

```text
organization/
    files/
```

For example:

```text
organization/
    files/
        report.txt
        report.pdf
        employee.xlsx
```

The synchronization agent monitors:

```text
organization/files/
```

The location must be configurable.

The project must **NOT** hardcode a specific user's Windows username or absolute path.

Example configuration:

```text
SYNC_FOLDER=./organization/files
```

This makes the project portable.

Another person should be able to clone the GitHub repository and run the project on their laptop without modifying source code.

---

## 6. PORTABILITY REQUIREMENT

The project MUST be demonstrable on another laptop.

This is a major design requirement.

The cloud infrastructure must remain hosted in AWS.

The demonstration laptop only needs to run the local synchronization agent and, optionally, the frontend/dashboard.

The intended demonstration architecture is:

```text
OTHER LAPTOP
    |
    | clone GitHub repository
    v
install dependencies
    |
    v
configure cloud endpoint
    |
    v
run synchronization agent
    |
    v
AWS EC2 backend
    |
   S3/RDS
```

The project must therefore avoid:

- hardcoded local paths
- hardcoded localhost addresses
- hardcoded AWS credentials
- hardcoded database passwords
- machine-specific configuration
- dependencies on files that exist only on the developer's laptop
- Docker/container-specific deployment requirements

Configuration should be externalized.

A `.env.example` file should be committed.

A real `.env` file containing credentials must NOT be committed.

---

## 7. GITHUB REPOSITORY STRUCTURE

The final repository should approximately resemble:

```text
hybrid-cloud-file-sync/
|
+-- agent/
|   +-- agent.py
|   +-- watcher.py
|   +-- sync_client.py
|   +-- hashing.py
|   +-- config.py
|   +-- state.py
|   +-- requirements.txt
|
+-- backend/
|   +-- main.py
|   +-- routes/
|   +-- services/
|   +-- models/
|   +-- database.py
|   +-- config.py
|   +-- requirements.txt
|
+-- frontend/
|   +-- index.html
|   +-- app.js
|   +-- styles.css
|
+-- database/
|   +-- schema.sql
|
+-- organization/
|   +-- files/
|       +-- .gitkeep
|
+-- docs/
|
+-- .env.example
+-- .gitignore
+-- README.md
+-- Architecture.md
+-- daily_report.txt
```

The exact directory structure may change during implementation, but the separation between agent, backend, database, and frontend should remain conceptually clear.

**Deployment constraint:** The project will **not use Docker or container-based deployment**. Components will run directly using their required runtimes on the development/demo machine or AWS infrastructure.

---

## 8. AWS COMPONENTS

### 8.1 AMAZON S3

**Purpose:**

S3 is the cloud storage layer for synchronized file content.

**Responsibilities:**

- Store files.
- Provide scalable cloud storage.
- Maintain object versions using S3 Versioning.
- Serve as the cloud-side copy of organization files.

S3 must have versioning enabled.

The project should use a logical organization/prefix structure.

Example:

```text
bucket/
    organization/
        files/
            report.txt
            report.pdf
            employee.xlsx
```

S3 should not be treated as the metadata database.

The RDS database records metadata about objects stored in S3.

### 8.2 AMAZON RDS

**Purpose:**

RDS stores relational information about synchronization.

**Minimum conceptual entities:**

```text
FILES
FILE_VERSIONS
SYNC_LOGS
```

Possible additional entity:

```text
USERS / ROLES
```

depending on implementation requirements.

`FILES` stores the current logical representation of a synchronized file.

Example fields:

```text
id
filename
relative_path
current_version
current_hash
size
status
created_at
updated_at
deleted
```

`FILE_VERSIONS` stores historical information.

Example fields:

```text
id
file_id
version_number
hash
size
operation
source
s3_version_id
created_at
```

`SYNC_LOGS` stores synchronization activity.

Example fields:

```text
id
file_id
operation
source
destination
status
error_message
timestamp
```

The exact schema must be finalized before backend implementation.

### 8.3 AMAZON EC2

**Purpose:**

EC2 hosts the backend/API and cloud-side compute layer.

The EC2 server should run the project's backend application.

**Recommended backend technology:**

```text
Python
FastAPI
```

The backend acts as the controlled communication interface between the synchronization agent and AWS resources.

The agent should NOT directly contain all database logic.

The backend should provide APIs for:

- uploading/synchronizing files
- obtaining synchronization information
- obtaining cloud changes
- querying status
- querying synchronization logs
- querying version history
- health checking

The backend communicates with S3 and RDS.

### 8.4 AWS IAM

**Purpose:**

IAM controls AWS permissions.

The EC2 instance should use an IAM role rather than hardcoded AWS access keys wherever practical.

Permissions should follow least privilege.

The backend should receive only the permissions it requires.

Example conceptual permissions:

```text
EC2 backend
    -> S3 required bucket operations
    -> CloudWatch logging/metrics where required
```

The final policy should avoid unnecessary `AdministratorAccess`.

### 8.5 AMAZON CLOUDWATCH

**Purpose:**

CloudWatch provides system monitoring.

Potential metrics:

- synchronization count
- successful synchronizations
- failed synchronizations
- API errors
- backend health
- synchronization latency

Logs may include:

- synchronization events
- backend errors
- AWS operation errors

The project should demonstrate at least one meaningful monitoring mechanism.

### 8.6 AWS CLOUDTRAIL

**Purpose:**

CloudTrail provides auditing of AWS API activity.

The project should use CloudTrail to demonstrate that AWS-side operations can be audited.

CloudTrail is different from the application's synchronization log.

Application log:

```text
“report.txt synchronized successfully”
```

CloudTrail:

```text
“AWS API activity occurred”
```

Both provide traceability at different layers.

### 8.7 AMAZON SNS

**Purpose:**

SNS sends alerts/notifications.

The project should demonstrate at least one meaningful alert.

Example:

```text
Synchronization failure
        |
        v
CloudWatch/alarm or backend event
        |
        v
       SNS
        |
        v
   notification
```

If time is limited, a single working failure alert is sufficient for the demonstration.

---

## 9. SYNCHRONIZATION MODEL

The synchronization system must support the fundamental direction:

```text
LOCAL -> CLOUD
```

and should also support:

```text
CLOUD -> LOCAL
```

The ideal final architecture is bidirectional.

### 9.1 LOCAL -> CLOUD

Example:

User creates:

```text
organization/files/test.txt
```

The watcher detects:

```text
CREATED
```

The agent calculates:

- filename
- relative path
- file size
- SHA-256 hash
- timestamp

The agent sends the event to the backend.

Backend:

1. validates request
2. authenticates/authorizes request
3. uploads file to S3
4. obtains S3 version information if applicable
5. updates RDS
6. records sync log
7. returns success

Result:

- Local file exists.
- Cloud file exists.
- RDS records its metadata.
- Version history exists.

### 9.2 LOCAL MODIFICATION

User modifies:

```text
test.txt
```

Watcher detects:

```text
MODIFIED
```

Agent calculates a new hash.

If the hash is different from the known version, synchronize.

Backend uploads the new content.

RDS creates a new `FILE_VERSIONS` entry.

Example:

```text
test.txt
    version 1
    version 2
    version 3
```

This demonstrates version history.

### 9.3 LOCAL DELETE

User deletes:

```text
test.txt
```

Agent detects:

```text
DELETED
```

The backend records the deletion.

Depending on final implementation, deletion may:

- delete the S3 object
- OR mark the logical file as deleted while retaining historical versions

For demonstration and recovery purposes, retaining version history is preferred.

The final implementation decision must be documented in `daily_report.txt`.

### 9.4 CLOUD -> LOCAL

A cloud-side change occurs.

The agent needs a way to discover it.

The preferred student-project mechanism is:

> Agent periodically asks backend: “Are there cloud changes since my last synchronization?”

The backend checks the relevant database state/S3 state.

If a cloud-side change exists:

```text
backend informs agent
        |
        v
agent downloads file
        |
        v
local filesystem updated
        |
        v
local synchronization state updated
```

This polling interval can be small enough to appear near-real-time during the demonstration.

A future production architecture could use more sophisticated event-driven mechanisms, but the student implementation must remain simple enough to finish within five days.

---

## 10. FILE HASHING

The synchronization agent should calculate a SHA-256 hash for files.

**Purpose:**

Detect whether content actually changed.

Example:

```text
test.txt
    hash A
```

User opens and saves without changing content.

If hash remains:

```text
hash A
```

the agent should avoid unnecessary upload where practical.

If content changes:

```text
hash B
```

the agent recognizes a new content version.

The hash is also useful for:

- integrity checking
- duplicate detection
- conflict detection
- version metadata

---

## 11. FILE EVENTS

Minimum supported events:

```text
CREATED
MODIFIED
DELETED
```

Preferred additional event:

```text
MOVED / RENAMED
```

The implementation should normalize filesystem-specific events into a common internal representation.

Example event:

```json
{
  "operation": "MODIFIED",
  "path": "reports/test.txt",
  "hash": "...",
  "size": 1234,
  "timestamp": "..."
}
```

The exact API representation may change during implementation.

---

## 12. SYNCHRONIZATION STATE

The agent needs local state.

The purpose is to know:

- what has already synchronized
- the last known hash
- the last synchronization timestamp
- the last known cloud version
- potentially the last processed cloud change

A simple local state file may be used.

Example:

```text
.sync_state.json
```

This file must not contain AWS credentials.

Example conceptual state:

```json
{
  "report.txt": {
    "hash": "...",
    "version": 3,
    "last_synced": "..."
  }
}
```

The exact implementation should be chosen by the coding agent based on simplicity and reliability.

---

## 13. CONFLICT HANDLING

A conflict occurs when:

```text
local version changes

and

cloud version changes
```

before the system has synchronized one side.

The project must not silently overwrite data.

Minimum acceptable student implementation:

1. Detect conflicting versions using hashes/version numbers.
2. Record the conflict in RDS.
3. Preserve the existing cloud version.
4. Preserve the local version where practical.
5. Create a conflict copy or otherwise clearly flag the conflict.
6. Display the conflict in the dashboard/log.

Example:

```text
report.txt
report.txt.conflict-<timestamp>
```

The exact conflict-resolution strategy must be documented once implemented.

---

## 14. DATABASE LOGIC

RDS must provide persistent project state.

The database should not store full file contents.

Instead it stores metadata.

Example:

**FILES:**

```text
file_id
path
filename
current_hash
current_version
current_s3_key
status
timestamps
```

**FILE_VERSIONS:**

```text
version_id
file_id
version_number
hash
s3_version_id
operation
source
timestamp
```

**SYNC_LOGS:**

```text
log_id
file_id
operation
status
source
error
timestamp
```

The schema should be normalized enough to demonstrate proper relational database design without unnecessarily complicating the project.

---

## 15. API DESIGN

The backend should expose a small, well-defined REST API.

Potential endpoints:

```text
GET  /health
```

Returns backend health.

```text
POST /sync/upload
```

Receives a local file synchronization request.

```text
POST /sync/delete
```

Records/processes a deletion.

```text
GET /sync/changes
```

Returns cloud-side changes after a supplied timestamp/version.

```text
GET /files
```

Returns synchronized files.

```text
GET /files/{id}/versions
```

Returns version history.

```text
GET /logs
```

Returns synchronization logs.

```text
GET /status
```

Returns system synchronization status.

The exact endpoints may be changed if Antigravity determines a cleaner implementation.

The API contract must be agreed upon before the agent and backend are implemented together.

---

## 16. FRONTEND / DASHBOARD

A small dashboard should be included if time permits.

The dashboard should prioritize demonstration value rather than visual complexity.

Potential display:

```text
HYBRID CLOUD SYNC

System Status: HEALTHY

Total Files: 10
Synced: 10
Failed: 0
Conflicts: 0

RECENT ACTIVITY

test.txt
    Modified
    Version 2
    Synced

report.pdf
    Created
    Version 1
    Synced

salary.xlsx
    Modified
    Version 4
    Synced
```

The dashboard should obtain information from the backend rather than directly connecting to RDS.

---

## 17. SECURITY MODEL

The system should follow these principles:

1. Never commit AWS credentials.
2. Never commit database passwords.
3. Use environment variables/configuration.
4. Use IAM roles where possible.
5. Use least-privilege permissions.
6. Validate API requests.
7. Do not expose RDS publicly unless absolutely necessary.
8. Restrict security groups.
9. Do not expose unnecessary AWS services.
10. Log relevant failures and security events.

For a five-day student implementation, security must be practical and demonstrable rather than enterprise-grade.

---

## 18. PORTABLE DEMONSTRATION ARCHITECTURE

This is a critical requirement.

The final demonstration must be possible using another person's laptop.

The demonstration laptop will act as the “organization's on-premises server”.

The cloud remains hosted in the developer's AWS environment.

Demonstration sequence:

1. Clone GitHub repository.
2. Install Python/dependencies.
3. Configure the cloud backend URL.
4. Create/use `organization/files/`.
5. Start agent.
6. Create a file.
7. Show synchronization occurring.
8. Open AWS S3 and show the file.
9. Open dashboard and show synchronization record.
10. Modify the local file.
11. Show new version.
12. Demonstrate version history.
13. Demonstrate cloud-to-local synchronization if implemented.
14. Demonstrate failure/alert scenario.

The user should NOT need:

- AWS CLI
- access to the AWS account
- RDS credentials
- AWS secret keys

on the demonstration laptop.

The laptop only needs the client/agent.

The project therefore separates:

```text
CLOUD INFRASTRUCTURE
```

from:

```text
DEMONSTRATION CLIENT
```

This makes the project portable.

---

## 19. DEMONSTRATION MODES

The project should ideally have two modes.

### MODE A: REAL CLOUD MODE

```text
Local laptop
    |
    v
EC2 backend
    |
    +--> S3
    +--> RDS
```

This is the primary demonstration.

### MODE B: DEVELOPMENT/LOCAL MODE

If AWS is temporarily unavailable during development, the agent and backend should ideally still be runnable locally.

For example:

```text
Local Agent
    |
    v
Local FastAPI backend
    |
    v
Local development database/mock storage
```

MODE B is optional and must not replace MODE A.

Its purpose is debugging and development resilience.

---

## 20. ENVIRONMENT CONFIGURATION

The repository should contain:

```text
.env.example
```

Example conceptual configuration:

```text
BACKEND_URL=
AWS_REGION=
S3_BUCKET=
DATABASE_NAME=
DATABASE_HOST=
```

Sensitive values must NOT be committed.

The real environment should use:

```text
.env
```

or appropriate environment variables.

`.gitignore` must include:

```text
.env
__pycache__/
*.pyc
.sync_state.json
local configuration
virtual environments
```

---

## 21. DEVELOPMENT STRATEGY

The project will be developed in layers.

**DO NOT build the entire project simultaneously.**

Correct order:

```text
PHASE 1
Local file watcher
        ↓
PHASE 2
Local synchronization logic
        ↓
PHASE 3
FastAPI backend
        ↓
PHASE 4
S3 integration
        ↓
PHASE 5
RDS integration
        ↓
PHASE 6
Bidirectional synchronization
        ↓
PHASE 7
Versioning/conflict handling
        ↓
PHASE 8
Dashboard
        ↓
PHASE 9
CloudWatch/SNS/CloudTrail/IAM
        ↓
PHASE 10
Portable demonstration
        ↓
PHASE 11
Documentation and final testing
```

At every stage, the system should remain runnable.

---

## 22. ANTIGRAVITY DEVELOPMENT STRATEGY

Antigravity is the implementation agent.

It must receive focused tasks.

**Do NOT give it the entire project and ask it to build everything at once.**

Each task must specify:

- current architecture
- files involved
- expected behavior
- constraints
- interfaces/API contracts
- what must not be changed
- test requirements

Example:

> “Implement the local filesystem watcher only. Do not implement AWS integration. Detect CREATED, MODIFIED and DELETED events. Normalize them into our event structure. Add tests.”

After completion:

```text
review
    ↓
test
    ↓
commit
    ↓
update daily report
```

Then move to the next component.

**Global implementation constraint:** Antigravity must not introduce Docker/container-specific files or deployment requirements.

---

## 23. CHATGPT PROJECT LOG RESPONSIBILITY

ChatGPT is responsible for maintaining the project's conceptual continuity.

The project log must track:

- current architecture
- completed components
- AWS resources
- database schema
- API contracts
- implementation decisions
- known bugs
- unresolved questions
- next task
- demonstration readiness
- documentation status

Before beginning a new major component, the current architecture must be checked against the existing implementation.

If implementation differs from architecture, the architecture file must be updated rather than allowing documentation and implementation to diverge silently.

---

## 24. DAILY REPORT FILE

A separate file must be maintained:

```text
daily_report.txt
```

`Architecture.md` = WHAT THE SYSTEM IS AND HOW IT IS SUPPOSED TO WORK.

`daily_report.txt` = WHAT WAS ACTUALLY DONE EACH DAY.

Daily report format:

```text
================================================================
DAY X
DATE:
================================================================

OBJECTIVES
- ...

COMPLETED
- ...

AWS CHANGES
- ...

CODE CHANGES
- ...

DATABASE CHANGES
- ...

TESTS PERFORMED
- ...

RESULTS
- ...

PROBLEMS ENCOUNTERED
- ...

DECISIONS MADE
- ...

CURRENT SYSTEM STATE
- ...

NEXT TASKS
- ...

NOTES FOR FINAL DEMONSTRATION
- ...
```

The daily report must contain factual information about what was actually completed.

Do not claim a feature is complete until it has been tested.

---

## 25. FIVE-DAY IMPLEMENTATION SCHEDULE

### DAY 1

**OBJECTIVE:**

Build AWS foundation and establish the project repository.

**Tasks:**

1. Confirm AWS Academy access.
2. Launch AWS Academy/Learner Lab environment.
3. Determine available AWS region.
4. Create S3 bucket.
5. Enable S3 versioning.
6. Create initial EC2 instance.
7. Configure EC2 security group.
8. Create IAM role for EC2.
9. Begin RDS setup.
10. Initialize GitHub repository.
11. Create `Architecture.md`.
12. Create `daily_report.txt`.
13. Create project directory structure.
14. Create `.gitignore`.
15. Create `.env.example`.
16. Confirm EC2 can run a basic backend.
17. Confirm S3 access from EC2.
18. Confirm RDS connectivity if possible.

**DAY 1 MUST END WITH:**

- GitHub repository exists.
- AWS account/lab works.
- S3 exists.
- EC2 exists.
- IAM is configured.
- RDS is created or actively being configured.
- Basic project skeleton exists.

### DAY 2

**OBJECTIVE:**

Build the local synchronization agent and establish the backend communication layer.

**Tasks:**

1. Build local directory watcher.
2. Detect file creation.
3. Detect file modification.
4. Detect file deletion.
5. Calculate SHA-256 hashes.
6. Normalize file events.
7. Build basic FastAPI backend.
8. Create `/health`.
9. Create initial synchronization endpoint.
10. Test local agent against local backend.
11. Add configuration system.
12. Add local synchronization state.
13. Establish communication between agent and EC2.
14. Test upload request end-to-end.

**DAY 2 MUST END WITH:**

- A local file can be created/modified/deleted.
- The agent detects the operation.
- The agent communicates with the backend.
- The backend receives the event.
- The system has a stable foundation for S3 synchronization.

### DAY 3

**OBJECTIVE:**

Complete actual cloud synchronization and persistence.

**Tasks:**

1. Connect backend to S3.
2. Upload files to S3.
3. Connect backend to RDS.
4. Persist file metadata.
5. Persist synchronization logs.
6. Persist version information.
7. Handle modifications.
8. Handle deletions.
9. Implement cloud-to-local change detection.
10. Implement cloud-to-local download.
11. Test bidirectional synchronization.

**DAY 3 MUST END WITH:**

- Local → S3 works.
- S3/cloud → Local works.
- RDS records synchronization metadata.
- Version history exists.

### DAY 4

**OBJECTIVE:**

Add product/demo features and reliability.

**Tasks:**

1. Version history endpoint.
2. Conflict detection.
3. Conflict handling.
4. Synchronization status.
5. Dashboard.
6. CloudWatch logging/metrics.
7. SNS failure notification.
8. CloudTrail verification.
9. IAM permission review.
10. Improve error handling.

**DAY 4 MUST END WITH:**

- The system looks like a complete project.
- The core demo works.
- Monitoring works.
- At least one alert scenario works.

### DAY 5

**OBJECTIVE:**

Turn the implementation into a reliable academic demonstration.

**Tasks:**

1. Full end-to-end testing.
2. Test on second laptop.
3. Fix portability issues.
4. Clean repository.
5. Remove secrets.
6. Improve README.
7. Verify `Architecture.md`.
8. Complete `daily_report.txt`.
9. Prepare architecture diagram.
10. Prepare demo script.
11. Prepare failure demonstration.
12. Prepare version-history demonstration.
13. Prepare AWS-console screenshots.
14. Prepare explanations for every AWS service.
15. Perform final clean deployment/test.

**FINAL SYSTEM MUST BE DEMONSTRABLE WITHOUT MANUAL CODE MODIFICATION.**

---

## 26. MINIMUM VIABLE PROJECT

If time becomes critically limited, the following features have priority.

### TIER 1 - ABSOLUTELY REQUIRED

- [ ] Local file watcher
- [ ] Local → AWS synchronization
- [ ] S3 storage
- [ ] RDS metadata
- [ ] EC2 backend
- [ ] File versioning
- [ ] Synchronization logs
- [ ] GitHub repository

### TIER 2 - STRONGLY REQUIRED

- [ ] Cloud → Local synchronization
- [ ] IAM
- [ ] CloudWatch
- [ ] SNS
- [ ] Dashboard

### TIER 3 - IF TIME PERMITS

- [ ] Conflict resolution
- [ ] Advanced RBAC
- [ ] Lifecycle policies
- [ ] Sophisticated event-driven mechanisms
- [ ] Terraform/IaC
- [ ] Automated CI/CD

Do NOT sacrifice Tier 1 functionality to implement Tier 3 features.

A working simple synchronization system is more valuable than a partially implemented enterprise architecture.

---

## 27. LIFECYCLE / COST OPTIMIZATION

The approved proposal mentions automatic movement of infrequently accessed files to lower-cost storage tiers.

This is an advanced requirement.

If time permits, configure an S3 lifecycle rule demonstrating movement of objects to an appropriate lower-cost storage class.

The implementation must be documented accurately.

Do not claim that lifecycle optimization is implemented if it was only described conceptually.

---

## 28. ROLE-BASED ACCESS CONTROL

The approved proposal requires role-based permissions.

A practical student implementation may define conceptual roles such as:

```text
ADMIN
    Full management access.

USER
    File synchronization/access.

VIEWER
    Read-only access.
```

depending on implementation requirements.

The implementation should avoid unnecessary authentication complexity.

The minimum goal is to demonstrate that different operations can be restricted according to role.

AWS IAM should be used for AWS resource permissions.

Application-level roles should be used for application permissions.

These are related but different security layers.

---

## 29. ERROR HANDLING

The system must not crash permanently because AWS becomes temporarily unavailable.

Potential failures:

- S3 unavailable
- EC2 unavailable
- RDS unavailable
- network timeout
- permission denied
- invalid file
- duplicate event
- synchronization conflict

The agent should ideally:

1. detect failure
2. record failure
3. retry where appropriate
4. avoid losing the local file
5. synchronize later when connectivity returns

For a five-day implementation, a simple retry mechanism is acceptable.

---

## 30. IDEMPOTENCY

The backend should avoid creating duplicate versions when the same event is accidentally processed multiple times.

Useful mechanisms:

- file hash
- version number
- event ID
- timestamp
- source

The exact implementation can be simplified for the academic project.

---

## 31. TESTING PLAN

The following scenarios must be tested.

### TEST 1

Create file locally.

**EXPECTED:**

- File appears in S3.
- RDS records file.
- Sync log says SUCCESS.

### TEST 2

Modify file locally.

**EXPECTED:**

- New S3 version.
- New RDS version record.
- Sync log records modification.

### TEST 3

Delete file locally.

**EXPECTED:**

- Cloud state reflects deletion.
- Historical metadata remains if deletion strategy retains history.

### TEST 4

Cloud changes.

**EXPECTED:**

- Agent discovers change.
- Local file is updated.

### TEST 5

Network/backend failure.

**EXPECTED:**

- Synchronization fails gracefully.
- Failure is logged.
- Alert is generated where configured.

### TEST 6

Conflicting local/cloud modifications.

**EXPECTED:**

- Conflict is detected.
- Data is not silently destroyed.
- Conflict is recorded.

### TEST 7

Second laptop.

**EXPECTED:**

- Repository can be cloned.
- Configuration can be provided.
- Agent starts.
- Synchronization works.

---

## 32. FINAL DEMONSTRATION SCRIPT

The final demonstration should follow this order.

1. Explain the problem: organization has an on-premises file server but wants cloud synchronization and backup.
2. Show architecture diagram.
3. Show GitHub repository.
4. Show local `organization/files` directory.
5. Start synchronization agent.
6. Create `demo.txt`.
7. Show agent detecting creation.
8. Show file appearing in S3.
9. Show RDS metadata/log.
10. Modify `demo.txt`.
11. Show version increment.
12. Show version history.
13. Demonstrate cloud-to-local synchronization.
14. Trigger synchronization failure.
15. Show CloudWatch/log information.
16. Show SNS notification if configured.
17. Show CloudTrail audit information.
18. Explain IAM.
19. Demonstrate second-laptop portability.
20. Conclude by mapping each demonstrated feature back to the project objectives.

---

## 33. PROJECT OBJECTIVE -> IMPLEMENTATION MAPPING

### OBJECTIVE 1

Automatically synchronize files between on-premises server and cloud storage.

**IMPLEMENTATION:**

```text
Local filesystem
+
Synchronization agent
+
EC2 backend
+
S3
```

### OBJECTIVE 2

Maintain auditable history of file changes.

**IMPLEMENTATION:**

```text
S3 Versioning
+
RDS FILE_VERSIONS
+
RDS SYNC_LOGS
+
CloudTrail
```

### OBJECTIVE 3

Secure role-based access.

**IMPLEMENTATION:**

```text
AWS IAM
+
application-level roles
```

### OBJECTIVE 4

Proactive monitoring and alerting.

**IMPLEMENTATION:**

```text
CloudWatch
+
SNS
```

**INNOVATION:**

```text
Incremental/event-driven file-level synchronization
+
versioning
+
monitoring
+
auditability
+
lifecycle optimization where implemented
```

---

## 34. DOCUMENTATION RULE

Documentation must reflect the actual implementation.

Never write:

```text
“Implemented”
```

until the feature has been tested.

Use:

```text
“Planned”
```

for future work.

Use:

```text
“In progress”
```

for incomplete work.

Use:

```text
“Implemented and tested”
```

only after successful testing.

---

## 35. FINAL DEFINITION OF DONE

The project is considered complete when:

- [ ] GitHub repository is clean.
- [ ] Architecture is documented.
- [ ] Daily reports are complete.
- [ ] Local agent runs.
- [ ] Local file creation synchronizes to AWS.
- [ ] Local modification synchronizes.
- [ ] Local deletion synchronizes.
- [ ] Cloud-side change can reach local machine.
- [ ] S3 stores actual files.
- [ ] S3 versioning works.
- [ ] RDS stores metadata.
- [ ] RDS stores version history.
- [ ] RDS stores synchronization logs.
- [ ] EC2 hosts backend.
- [ ] IAM permissions work.
- [ ] CloudWatch monitoring works.
- [ ] SNS alert works or its implemented scope is clearly documented.
- [ ] CloudTrail auditing is demonstrable.
- [ ] Conflict behavior is documented.
- [ ] Error handling works.
- [ ] Project works on another laptop.
- [ ] No secrets are present in GitHub.
- [ ] README explains setup.
- [ ] Architecture diagram exists.
- [ ] Full demonstration has been rehearsed.
- [ ] Every claimed feature can be demonstrated or is clearly marked as conceptual/limited.

---

## 36. GUIDING PRINCIPLE FOR THE FIVE-DAY BUILD

The project must prioritize **FUNCTIONALITY over complexity**.

The core chain is:

```text
LOCAL FILE
    ↓
WATCHER
    ↓
SYNCHRONIZATION AGENT
    ↓
EC2 API
    ↓
S3
+
RDS
    ↓
MONITORING / LOGGING / ALERTING
```

Everything else exists to strengthen this core.

If a feature threatens the completion of the core synchronization pipeline, postpone the feature.

The first objective is:

> **“A file changes on a laptop and the cloud copy changes automatically.”**

Once this works reliably, add versioning.

Once versioning works, add monitoring.

Once monitoring works, add security and polish.

---

## NO-DOCKER PROJECT CONSTRAINT

This project intentionally does **not** use Docker.

- No Dockerfiles.
- No `docker-compose.yml`.
- No container-based local development requirement.
- No container-based EC2 deployment requirement.
- Components should run directly using their normal runtimes.

This constraint does not alter the AWS architecture or the synchronization design; it only removes containerization from the implementation/deployment approach.
