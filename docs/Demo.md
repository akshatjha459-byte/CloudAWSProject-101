# Review 2 Demonstration Guide

This document is the technical runbook for the Review 2 demonstration. It describes the deployed system as it actually exists and gives the operator sequence for reproducing the main cloud-backed workflow.

> **Scope:** Review 2 demonstrates the complete cloud-backed application on one demonstration laptop. The two-laptop distributed synchronization demonstration is intentionally reserved for the final review.

---

## 1. What Was Built

The project is a hybrid-cloud file synchronization system in which a local directory represents an organization's on-premises file server.

```text
Local organization/files/
        |
        v
Synchronization Agent (M2)
        |
        | HTTP + X-API-Key
        v
FastAPI backend on EC2 (M3)
        |
        +------------------+
        |                  |
        v                  v
S3 (file bytes)      RDS PostgreSQL (metadata)
        |                  |
        +--------+---------+
                 |
          Dashboard (M10)
```

The deployed AWS environment is in `ap-south-1` (Mumbai).

### AWS components

| Component | Role |
|---|---|
| EC2 `t3.micro` | Runs the FastAPI backend persistently through `cloudaws-backend.service`. |
| S3 | Stores file content and S3 object versions. |
| RDS PostgreSQL | Stores file metadata, versions, sync logs and change state; it does not store file bytes. |
| IAM | Gives EC2 temporary AWS credentials through its instance role and limits runtime permissions. |
| Security Groups | Control network access between the Internet, EC2 and private RDS. |
| CloudWatch | Receives application metrics from M9. |
| SNS | Sends configured failure/security alerts from M9. |
| CloudTrail | AWS-account audit trail; separate from application sync logs. |

### Application components

| Component | Role |
|---|---|
| M1 local filesystem | Portable `organization/files/` source directory. |
| M2 Sync Agent | Watches files, computes SHA-256 hashes, sends events and polls cloud changes. |
| M3 FastAPI | Authentication, validation and orchestration between the agent, S3 and RDS. |
| M4 S3 adapter | Maps application paths to S3 object keys and handles S3 version IDs. |
| M5 RDS adapter | Persists relational metadata and synchronization state. |
| M6 security | API-key authentication, IAM, security groups and real AWS deployment. |
| M7 bidirectional sync | Cloud-to-local polling plus local-to-cloud synchronization and loop prevention. |
| M8 versioning/conflicts | Historical versions, 3-way conflict detection and zero-silent-overwrite behavior. |
| M9 observability | Structured logs, RDS sync logs, CloudWatch metrics and SNS alerts. |
| M10 dashboard | Read-only web UI consuming the M3 REST API; no direct S3/RDS access. |

---

## 2. How The System Was Deployed

The practical deployment sequence was:

1. Created the S3 project bucket and enabled S3 Versioning, Block Public Access and default encryption.
2. Created the `CloudAWSProject-S3-Access` least-privilege policy and attached it to `CloudAWSProject-EC2-Role`.
3. Created an EC2-trusted IAM role and attached the role to the EC2 instance through its instance profile.
4. Created separate EC2 and RDS security groups.
5. Allowed the EC2 application port (TCP 8000) for demonstration access and configured SSH access for administration.
6. Created private PostgreSQL RDS with public access disabled; TCP 5432 is permitted from the EC2 security group.
7. Connected to EC2 and cloned the project repository at `/home/ec2-user/CloudAWSProject-101`.
8. Configured a real `.env` on EC2 containing production settings and secrets; this file is not committed to GitHub.
9. Configured the backend for `STORAGE_ADAPTER=s3` and `METADATA_ADAPTER=rds`.
10. Configured the Sync Agent on Windows with the EC2 backend URL and application API key.
11. Converted the backend into the persistent `cloudaws-backend.service` systemd service.
12. Added M9 monitoring configuration and attached the monitoring IAM policy for CloudWatch/SNS.
13. Added the M10 dashboard to the FastAPI application at `/dashboard/`.
14. Verified a real local file synchronization path: Agent -> EC2 -> S3/RDS.
15. Verified S3 versioning by modifying a file and retrieving historical versions through the API/dashboard.

The backend uses the EC2 IAM role for AWS SDK access rather than storing long-lived AWS access keys on the instance. AWS documents this EC2 role/instance-profile model as the standard way for applications on EC2 to obtain AWS permissions. citeturn0search0turn0search4

---

## 3. Important Security Model

### Agent -> EC2

Protected API endpoints require the `X-API-Key` header in production. `/health` remains public. Missing or incorrect keys return HTTP 401.

### EC2 -> S3

The backend uses the EC2 IAM role and the AWS SDK credential chain. The runtime policy is restricted to the project bucket.

For the current version-download feature, the S3 policy must include:

```text
s3:GetObject
s3:GetObjectVersion
s3:PutObject
s3:DeleteObject
s3:ListBucket
```

`GetObjectVersion` is required when a specific S3 version ID is requested; ordinary current-object reads use `GetObject`. citeturn0search5turn0search9

### EC2 -> RDS

RDS is private. PostgreSQL traffic on TCP 5432 is restricted to the EC2 security group.

### Secrets

Never paste the real API key, RDS password or private SSH key into this document or GitHub. The local `.env` and private demo notes remain outside the repository.

---

## 4. Pre-Demo Checklist

Run these checks before the review rather than discovering problems during the presentation.

### AWS

- [ ] EC2 instance is running.
- [ ] EC2 security group allows the required demo access.
- [ ] RDS status is available and public access is disabled.
- [ ] RDS security group still permits TCP 5432 from EC2.
- [ ] S3 bucket exists and Versioning is enabled.
- [ ] `CloudAWSProject-EC2-Role` is attached to EC2.
- [ ] `CloudAWSProject-S3-Access` includes `s3:GetObjectVersion`.
- [ ] M9 monitoring policy remains attached.

### EC2

SSH from Windows PowerShell:

```powershell
ssh -i "D:\sem5\AWS\project\Key-Pair\CloudAWSProject-EC2-Key.pem" ec2-user@13.126.239.36
```

Then verify the project and service:

```bash
cd /home/ec2-user/CloudAWSProject-101
sudo systemctl status cloudaws-backend.service --no-pager
curl http://127.0.0.1:8000/health
```

Expected health response:

```json
{"status":"ok","service":"hybrid-cloud-sync-backend"}
```

The service should show `active (running)`.

If the service was stopped or the EC2 instance was restarted, use:

```bash
sudo systemctl restart cloudaws-backend.service
sudo systemctl status cloudaws-backend.service --no-pager
```

### Windows Agent

From the project root, make sure the local environment contains the configured `SYNC_FOLDER`, EC2 `BACKEND_URL`, and matching API key. Do not print the API key in the terminal during the demonstration.

The M2 entry point is:

```powershell
python -m agent.agent
```

When `BACKEND_URL` is set, the agent uses `HttpEventSender` and also starts the M7 `CloudPoller`. fileciteturn56file0L2-L2

---

## 5. Review 2 Demo Procedure

### Step 1 — Start the cloud backend

Confirm the EC2 systemd service is active and `/health` returns HTTP 200.

Do not run Uvicorn manually if the systemd service is already active; the service is the persistent production process.

### Step 2 — Open the dashboard

Open:

```text
http://13.126.239.36:8000/dashboard/
```

Enter the production API key when prompted.

The dashboard should show the production **S3 / RDS** adapters. The dashboard itself talks only to the FastAPI API; it does not connect directly to S3 or RDS. fileciteturn62file0L2-L2

### Step 3 — Start the Sync Agent

On Windows, from the project root:

```powershell
python -m agent.agent
```

Leave this terminal running. It watches `organization/files/`.

### Step 4 — Create a demonstration file

Create a small text file inside:

```text
organization/files/
```

For example:

```text
review2-demo.txt
```

The watcher detects the CREATED event, computes the SHA-256 hash and sends the event to the EC2 backend.

### Step 5 — Show the cloud path

The backend receives the event and performs the cloud-side operation:

```text
Windows local file
      ↓
M2 watcher + SHA-256
      ↓
HTTP POST /sync/upload
      ↓
EC2 FastAPI
      ├──→ S3: file bytes
      └──→ RDS: metadata/version/log/change
```

Refresh the dashboard and show the file in the Files table.

### Step 6 — Show S3

In the AWS S3 console, open the project bucket and navigate to:

```text
organization/files/
```

The object represents the actual file content.

Do not manually upload the demo file to S3; the point of the demonstration is that the application performed the synchronization.

### Step 7 — Show RDS's role

Explain that RDS stores information *about* the file rather than the file itself.

Relevant logical data includes:

```text
files
file_versions
sync_logs
sync_changes
```

The metadata includes values such as the relative path, current version, SHA-256 hash, size, status and S3 storage/version information.

### Step 8 — Demonstrate versioning

Modify the same local file and save it.

The second upload should create the next application version and a new S3 object version while preserving the historical version.

In the dashboard:

1. Find the file.
2. Open its version history.
3. Show Version 1 and Version 2.
4. Use **Download** on an older version.
5. Confirm that the historical content is retrieved.

A specific S3 version requires `s3:GetObjectVersion`, which is why that permission is present in the deployed runtime policy. citeturn0search5

### Step 9 — Demonstrate monitoring/logging

Use the dashboard's sync-log table to show successful operations and the existing historical failure entries.

The project deliberately keeps failures visible rather than hiding them:

```text
Operation attempt
      ↓
Validation / processing
      ↓
SUCCESS or FAILURE
      ↓
RDS sync_logs
      ↓
Dashboard visibility
```

M9 additionally emits CloudWatch metrics and can publish configured SNS alerts for repeated sync failures, repeated authentication failures and critical application errors. Monitoring is auxiliary and does not become a synchronization dependency. fileciteturn53file0L2-L2

### Step 10 — Demonstrate authentication

If required by the reviewer, show that a protected endpoint rejects an invalid/missing API key with HTTP 401.

Do **not** intentionally generate five consecutive authentication failures during a live presentation unless you specifically want to trigger the configured SNS repeated-auth-failure threshold.

### Step 11 — Stop cleanly

Stop the Windows agent with:

```text
Ctrl+C
```

The EC2 backend remains running because it is managed by systemd rather than the SSH terminal.

---

## 6. Review 2 Recommended Story

The cleanest sequence is:

```text
1. AWS console: EC2 + S3 + RDS
2. EC2: systemd service + /health
3. Dashboard: authenticate and show S3/RDS adapters
4. Start Sync Agent
5. Create local file
6. Show file in dashboard
7. Show object in S3
8. Show metadata/version information in RDS
9. Modify file
10. Show Version 2
11. Download Version 1
12. Show sync logs / failure handling
13. Show CloudWatch/SNS evidence if time permits
```

This demonstrates the complete Review 2 cloud architecture without using the final-review two-laptop scenario.

---

## 7. Failure / Recovery Demonstrations

The project already contains intentional failure records from M9 validation testing. These can be used to explain that an invalid request is rejected and recorded without taking down the service.

For a live failure demonstration, safer options are:

- Show an existing `FAILURE` entry in the dashboard.
- Show HTTP 401 from an invalid API key.
- Show the backend service still `active (running)` after an application error.
- Show CloudWatch metrics for `SyncFailure` or `ApplicationErrors` if the metric is present.

Avoid destructive AWS-console experiments during the review. Do not delete the bucket, RDS instance, IAM role, or security groups merely to demonstrate failure handling.

---

## 8. Troubleshooting

### Dashboard does not load

Check:

```bash
sudo systemctl status cloudaws-backend.service --no-pager
curl http://127.0.0.1:8000/health
```

Also confirm EC2 security-group access to TCP 8000.

### Dashboard says unauthorized

Re-enter the production API key. The dashboard stores it only in browser session storage and sends it as `X-API-Key`. fileciteturn62file0L2-L2

### Download gives HTTP 500 / AccessDenied

Verify that the EC2 IAM policy contains:

```text
s3:GetObjectVersion
```

This permission is required for requests that retrieve a specific S3 object version. citeturn0search5turn0search9

### Backend stopped after disconnecting SSH

It should not: `cloudaws-backend.service` is a systemd service. Check:

```bash
sudo systemctl status cloudaws-backend.service --no-pager
```

Then restart if necessary:

```bash
sudo systemctl restart cloudaws-backend.service
```

### Agent is not sending events

Verify the agent `.env` has:

```env
SYNC_FOLDER=./organization/files
BACKEND_URL=http://13.126.239.36:8000
API_KEY=<configured-production-key>
```

Then restart the agent.

### EC2 cannot reach RDS

Check that:

- RDS is available.
- RDS public access is disabled.
- RDS security group allows TCP 5432 from the EC2 security group.
- EC2 and RDS are in the expected VPC/network configuration.

---

## 9. Final Review Boundaries

### Review 2

Focus on:

```text
Single laptop
   ↓
Sync Agent
   ↓
EC2 FastAPI
   ↓
S3 + RDS
   ↓
Dashboard
```

### Final Review

Reserve the stronger distributed demonstration for later:

```text
Laptop A
   ↓
Sync Agent A
   ↓
EC2 FastAPI
   ↓
S3 + RDS
   ↓
Sync Agent B
   ↓
Laptop B
```

The final-review scenario demonstrates that the architecture is not merely a web interface over AWS storage: independent synchronization clients can use the same cloud backend and converge through the M7 change-feed/polling mechanism.

---

## 10. Verification Snapshot

The repository's current progress record states that all ten modules are complete and that the following have been verified: production S3/RDS adapters, persistent EC2 systemd service, public dashboard access, real local Agent -> EC2 -> S3/RDS synchronization, S3 versioning, API-key authentication and M9 monitoring/alerting integration. fileciteturn67file0L2-L2

Latest recorded full regression after M10:

```text
161 passed, 2 skipped, 1 warning
```

M10 focused suite:

```text
7 passed
```

---

## 11. Important Don'ts

- Do not upload files manually to S3 and call that synchronization.
- Do not connect the dashboard directly to RDS or S3.
- Do not put AWS credentials in the repository.
- Do not put the real API key or RDS password in this document.
- Do not expose RDS publicly.
- Do not remove the IAM least-privilege model just to make a demo work.
- Do not run a second Uvicorn process on port 8000 while the systemd service is active.
- Do not use the two-laptop demonstration for Review 2; keep it for the final review.
