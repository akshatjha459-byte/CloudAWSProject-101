# HYBRID CLOUD FILE SYNCHRONIZATION AND SECURE DATA MIGRATION FRAMEWORK USING AMAZON WEB SERVICES

## PROJECT MASTER ARCHITECTURE AND IMPLEMENTATION PLAN

**Version:** 2.0  
**Project Duration:** 5 Days  
**Development Strategy:** ChatGPT = Architecture / Project Log / Technical Guidance  
Antigravity = Implementation / Coding Agent  
**Cloud Platform:** Amazon Web Services (project AWS account)  
**Repository:** GitHub

---

## 1. PROJECT PURPOSE

This project implements a functional hybrid-cloud file synchronization system. A local directory represents an organization's on-premises file server, while AWS provides cloud storage, backend compute, metadata persistence, security and operational services.

```text
LOCAL ORGANIZATION FILES
          ↕
  SYNCHRONIZATION AGENT
          ↕
       EC2 / API
       ↙       ↘
      S3       RDS
```

AWS services:
- **Amazon S3** — actual cloud file content and object versioning.
- **Amazon RDS PostgreSQL** — file metadata, versions, sync logs and change state.
- **Amazon EC2** — FastAPI backend and cloud-side application logic.
- **AWS IAM** — AWS resource permissions and EC2 identity.
- **Security Groups** — network isolation.
- **CloudWatch** — monitoring and operational visibility.
- **CloudTrail** — AWS API audit trail.
- **Amazon SNS** — failure/security notifications.

The project must demonstrate actual synchronization through the application, not merely manual S3 uploads.

---

## 2. NON-NEGOTIABLE DESIGN PRINCIPLES

### S3 vs RDS

> **S3 stores FILE CONTENT.**
>
> **RDS stores INFORMATION ABOUT FILES.**
>
> **RDS is NOT the cloud copy of the files.**

### Backend ownership

The Synchronization Agent communicates with the FastAPI backend. The backend controls S3 and RDS operations. The agent does not contain the project's database logic.

### Security ownership

M6 owns AWS IAM, least-privilege permissions, application authentication, security-group requirements and real AWS deployment verification. Future modules must not move these responsibilities into M7-M10.

### Portability

The local agent must run on another laptop without source-code modification. No machine-specific paths, AWS credentials or database passwords may be committed.

### Deployment

The project does **not** use Docker or container-based deployment. AWS components run directly on AWS infrastructure; the local agent runs directly on the demonstration laptop.

---

## 3. CANONICAL MODULE SEQUENCE

The project has exactly 10 modules. This sequence is fixed unless `docs/module-contracts.md` is deliberately changed before implementation.

| Module | Responsibility | Completion Gate |
|---|---|---|
| **M1** | Local File System / Organization Server | Portable local directory and validation |
| **M2** | Synchronization Agent | Watcher, normalized events, hashing, sender |
| **M3** | FastAPI Backend / EC2 | REST API and service contracts |
| **M4** | Amazon S3 Storage | S3 adapter and versioning support |
| **M5** | Amazon RDS Database | PostgreSQL metadata/version/log persistence |
| **M6** | AWS IAM / Security | Security implementation **plus real AWS deployment/verification** |
| **M7** | Bidirectional Synchronization | Cloud-to-local and local-to-cloud behavior |
| **M8** | Versioning & Conflict Handling | Conflict detection and safe resolution |
| **M9** | Monitoring, Logging & Alerting | CloudWatch, CloudTrail, SNS integration |
| **M10** | Frontend Dashboard | Dashboard through the M3 API |

**Important:** AWS deployment is part of the M6 completion gate. It is **not** a separate M7. M7 is and remains **Bidirectional Synchronization**.

---

## 4. SYSTEM ARCHITECTURE

```text
                         INTERNET
                            |
                    HTTP / HTTPS API
                            |
                  +---------v----------+
                  |       EC2          |
                  |    FastAPI API     |
                  +----+----------+----+
                       |          |
                 IAM role     DB credentials
                       |          |
                       v          v
                      S3         RDS
                  file content  metadata
                       |
                       +---- CloudWatch
                       +---- CloudTrail
                                   |
                                   v
                                  SNS

                            ^
                            |
                     HTTP / HTTPS
                     X-API-Key
                            |
                  +---------+----------+
                  | LOCAL / ON-PREM   |
                  | Synchronization   |
                  | Agent             |
                  |                   |
                  | organization/     |
                  |   files/          |
                  +-------------------+
```

For the academic demonstration, `organization/files/` on a laptop simulates the organization's local file server.

---

## 5. MODULE RESPONSIBILITIES

### M1 — Local File System / Organization Server

Owns only the portable local file source `organization/files/`. It does not own filesystem watching, hashing, synchronization or AWS logic.

### M2 — Synchronization Agent

Owns local directory monitoring, CREATED/MODIFIED/DELETED events, preferably MOVED/RENAMED events, SHA-256 hashing, local synchronization state, M3 communication and appropriate retry/error handling.

The agent must obtain configuration externally and never contain AWS credentials.

### M3 — FastAPI Backend / EC2

Owns the REST API and service layer between M2 and AWS resources.

Minimum API contract:

```text
GET  /health
POST /sync/upload
POST /sync/delete
GET  /sync/changes
GET  /files
GET  /files/{id}/versions
GET  /logs
GET  /status
```

M3 validates requests, authenticates the agent, coordinates S3/RDS operations and returns explicit success/failure information.

### M4 — Amazon S3

Owns actual file content. The project bucket must have S3 Versioning enabled. Runtime IAM access must be restricted to the project bucket and required S3 actions.

### M5 — Amazon RDS

Owns persistent relational metadata. Minimum logical entities are `FILES`, `FILE_VERSIONS` and `SYNC_LOGS`. A change-feed/state table may be used when required by M7. RDS must not store complete file contents.

### M6 — AWS IAM / Security

M6 owns the security boundary and deployment verification.

Requirements:
- EC2 uses an IAM role / instance profile rather than long-lived AWS access keys.
- Runtime permissions follow least privilege.
- S3 permissions are restricted to the project bucket.
- Infrastructure-management actions such as bucket versioning configuration are not runtime permissions unless genuinely required.
- RDS is not publicly accessible.
- RDS PostgreSQL port 5432 is reachable only from the EC2 security group.
- EC2 exposes only required ports.
- Agent-to-EC2 authentication uses the implemented application mechanism (`X-API-Key`).
- Real AWS resources and the end-to-end connection path are verified before M7 starts.

### M7 — Bidirectional Synchronization

M7 extends the existing system to support:

```text
LOCAL -> CLOUD
CLOUD -> LOCAL
```

The preferred student-project mechanism for cloud-to-local discovery is polling through M3:

```text
Agent -> M3: changes since last known state?
M3 -> Agent: applicable changes
Agent -> local filesystem: apply change
```

M7 must consume the existing M2/M3/M4/M5 contracts rather than redesigning M6.

### M8 — Versioning & Conflict Handling

M8 builds on S3 Versioning, RDS version records, hashes and synchronization state.

Minimum conflict behavior:
1. Detect conflicting hashes/versions.
2. Do not silently overwrite data.
3. Preserve existing versions where practical.
4. Record the conflict in RDS.
5. Create a conflict copy or clearly flag the conflict.
6. Expose the conflict through the existing API/dashboard path.

### M9 — Monitoring, Logging & Alerting

M9 owns CloudWatch monitoring/logging, CloudTrail AWS API auditing and SNS failure/security notification. Application synchronization logs and CloudTrail audit records remain separate concepts.

### M10 — Frontend Dashboard

M10 communicates with M3 only through the REST API. It should display system health, file status, recent synchronization activity, version history, logs and conflicts where implemented. It must not connect directly to RDS.

---

## 6. LOCAL-TO-CLOUD FLOW

```text
Local filesystem
      |
      v
M2 watcher detects event
      |
      v
SHA-256 + metadata
      |
      v
M3 REST API
      |
      +---------> M4 S3: file content
      |
      +---------> M5 RDS: metadata/version/log
      |
      v
Success response
```

For a modification, the agent computes a new hash and the backend creates the next application/S3 version as appropriate.

For deletion, the implementation follows the documented deletion strategy while preserving history where practical.

---

## 7. CLOUD-TO-LOCAL FLOW

M7 uses the existing `/sync/changes` contract to discover cloud-side changes.

```text
M4/M5 cloud state
      |
      v
M3 change feed
      |
      v
M2 Synchronization Agent
      |
      v
local filesystem
      |
      v
local sync state updated
```

The mechanism must avoid repeatedly applying the same cloud change.

---

## 8. HASHING AND STATE

Files use SHA-256 for content comparison and integrity checks. The agent maintains local state such as `.sync_state.json`, including information such as the last known hash, synchronization timestamp, cloud/application version and processed cloud change.

The state file must never contain AWS credentials.

---

## 9. SECURITY MODEL

### Agent -> EC2

Application-level authentication uses `X-API-Key` for protected API endpoints. `/health` remains public. Production configuration rejects missing/incorrect keys with HTTP 401.

### EC2 -> S3

EC2 uses its attached IAM role and temporary credentials through the AWS SDK credential chain.

### EC2 -> RDS

EC2 connects to RDS over the VPC using database authentication plus security-group restrictions.

### Internet -> RDS

Direct public access to RDS is prohibited. The RDS security group allows PostgreSQL traffic only from the EC2 security group.

### Secrets

Never commit AWS secret keys, database passwords, production API keys or real `.env` files. Use `.env.example` for placeholders and real environment configuration outside Git.

---

## 10. AWS DEPLOYMENT AND M6 COMPLETION GATE

The project uses a real AWS account rather than AWS Academy/Learner Lab infrastructure.

M6 remains **PARTIAL** until the following are actually deployed and verified:

1. S3 bucket created and Versioning enabled.
2. IAM policy created from the repository template with the real bucket name.
3. EC2-trusted IAM role created and attached to EC2.
4. EC2 security group configured.
5. PostgreSQL RDS created in the same VPC as EC2.
6. RDS security group restricts port 5432 to the EC2 security group.
7. RDS public access disabled.
8. EC2 backend configured with production environment variables.
9. EC2 can access S3 through its IAM role.
10. EC2 can connect to RDS.
11. Local Agent can authenticate to EC2.
12. Unauthorized API requests return 401.
13. Authorized requests succeed.
14. A real local file completes Agent -> EC2 -> S3/RDS.

Only after this checklist is verified should the project move to M7.

---

## 11. DEVELOPMENT / TESTING MODES

### Real Cloud Mode — Primary

```text
Local Agent
    |
    v
EC2 FastAPI
   /    \
 S3     RDS
```

This is the mode used for the final demonstration.

### Local Development Mode — Secondary

Existing local/in-memory adapters may be used for development and regression tests. Local mode is not proof that the AWS deployment works.

---

## 12. PORTABLE DEMONSTRATION

A second laptop should be able to:

1. Clone the repository.
2. Install the agent dependencies.
3. Configure the backend URL and API key.
4. Use `organization/files/` as the local source.
5. Start the synchronization agent.
6. Create/modify a file.
7. Observe synchronization through EC2.
8. Show the file in S3 and metadata in RDS.
9. Demonstrate versioning and, after M7, cloud-to-local synchronization.
10. Demonstrate a failure/authentication case.

The demonstration laptop does not need AWS credentials or direct RDS access.

---

## 13. FUTURE MODULE PLAN

```text
M6 AWS deployment + verification
        |
        v
M7 Bidirectional Synchronization
        |
        v
M8 Versioning & Conflict Handling
        |
        v
M9 Monitoring, Logging & Alerting
        |
        v
M10 Frontend Dashboard
        |
        v
Final end-to-end testing + portable demonstration
```

Do not implement future modules early merely to compensate for an incomplete earlier module.

---

## 14. DOCUMENTATION RULE

- `docs/Architecture.md` — canonical system architecture and module boundaries.
- `docs/module-contracts.md` — canonical interfaces/dependencies.
- `docs/PROGRESS.md` — factual implementation and verification state.
- `modules/module-XX/README.md` — module-specific implementation notes and verification.
- `daily_report.txt` — factual day-by-day project history.

Documentation must never claim AWS resources or end-to-end behavior has been verified when only local tests or documentation have been completed.

When implementation differs from the architecture, resolve the discrepancy deliberately before continuing to the next module.
