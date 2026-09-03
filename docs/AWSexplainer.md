# AWSexplainer — CloudAWSProject-101

This document is a personal reference for rebuilding and understanding the AWS environment used by CloudAWSProject-101. It records what was configured in the AWS Console, why it was configured, what was verified, and the important deployment commands used afterward.

> **Important:** Runtime passwords and API keys are intentionally NOT recorded here. When rebuilding the project after the current AWS credits/free period ends, create new credentials/secrets and place them in the appropriate `.env` files rather than copying old secrets.

---

## 1. Project Goal

The project is a hybrid-cloud file synchronization system:

```text
Windows local files
        |
        v
Synchronization Agent
        |
        | HTTP + API key
        v
EC2 / FastAPI Backend
      /       \
     v         v
   S3         RDS PostgreSQL
(file data)  (metadata/version state)
```

AWS responsibilities:

- **EC2:** FastAPI backend and compute.
- **S3:** actual cloud file contents and object versioning.
- **RDS PostgreSQL:** metadata, file versions, synchronization logs/change state.
- **IAM:** EC2 permissions to AWS resources.
- **Security Groups:** network access control.
- **CloudWatch / CloudTrail / SNS:** planned M9 monitoring, auditing and alerting.

RDS stores metadata, **not the actual file contents**.

---

## 2. AWS Account / Region

The project uses a normal AWS account, not an AWS Academy/Learner Lab environment.

**Region:** Asia Pacific (Mumbai) — `ap-south-1`

This region was selected consistently for the AWS resources so EC2, S3 and RDS remain in the same AWS region.

The AWS account was using the available introductory/free credits. Because those credits are time-limited, this document is intended to preserve the setup knowledge for rebuilding the project later.

---

# 3. S3 Setup

## 3.1 Create the bucket

AWS Console path:

**S3 → Create bucket**

Bucket created:

```text
cloudawsproject-101-482917-680476617705-ap-south-1-an
```

Region:

```text
ap-south-1
```

The bucket is used to store the synchronized file bytes.

The application uses the prefix:

```text
organization/files
```

So a local file such as:

```text
organization/files/m6-test.txt
```

is stored using the S3 key:

```text
organization/files/m6-test.txt
```

## 3.2 Enable S3 Versioning

Inside the bucket:

**Properties → Bucket Versioning → Enable**

Why:

The project needs historical versions rather than silently replacing cloud data. Version IDs are also recorded in RDS metadata.

## 3.3 Block public access

Inside the bucket:

**Permissions → Block public access → Block all public access**

All four block-public-access settings were enabled.

Why:

The project's files should not be publicly accessible through S3.

## 3.4 Default encryption

Inside the bucket:

**Properties → Default encryption**

Encryption was enabled using **SSE-S3**.

Why:

Objects stored in the bucket receive server-side encryption without requiring application-side encryption logic.

## 3.5 What was verified

The EC2 instance was later tested using its IAM role. This command:

```bash
aws s3 ls
```

returned `AccessDenied` because the role was intentionally not given `s3:ListAllMyBuckets`.

Access directly to the project bucket succeeded:

```bash
aws s3 ls s3://cloudawsproject-101-482917-680476617705-ap-south-1-an
```

This demonstrated that the IAM policy was scoped to the required bucket rather than giving unrestricted S3 access.

---

# 4. IAM Setup

IAM was used so EC2 can access S3 without storing long-lived AWS access keys in the project.

## 4.1 Create the S3 access policy

AWS Console path:

**IAM → Policies → Create policy**

Policy name:

```text
CloudAWSProject-S3-Access
```

The policy grants the EC2 workload only the S3 actions required by the project and scopes them to the actual project bucket.

The important design principle is:

> Give the EC2 application access to its bucket, not to every bucket in the AWS account.

## 4.2 Create the EC2 role

AWS Console path:

**IAM → Roles → Create role**

Trusted entity:

**AWS service → EC2**

Role name:

```text
CloudAWSProject-EC2-Role
```

Attach:

```text
CloudAWSProject-S3-Access
```

This produces an EC2 instance role/instance profile that AWS can expose to the application through the instance metadata credentials mechanism.

## 4.3 Attach the role to EC2

After the EC2 instance was launched:

**EC2 → Instances → select instance → Actions → Security → Modify IAM role**

Select:

```text
CloudAWSProject-EC2-Role
```

No AWS access key or secret access key was placed in the application configuration.

---

# 5. RDS PostgreSQL Setup

## 5.1 Create the RDS security group

AWS Console path:

**EC2 → Security Groups → Create security group**

Name:

```text
CloudAWSProject-RDS-SG
```

Inbound rule:

```text
Type: PostgreSQL
Port: 5432
Source: CloudAWSProject-EC2-SG
```

This means PostgreSQL is reachable from the EC2 security group rather than from the public Internet.

## 5.2 Create the RDS database

AWS Console path:

**RDS → Databases → Create database**

Configuration used:

```text
Engine: PostgreSQL
Version: PostgreSQL 18.3-R2
db instance class: db.t4g.micro
Storage: 20 GiB gp2
Database: postgres
Username: cloudadmin
Public access: No
Security group: CloudAWSProject-RDS-SG
Port: 5432
```

Endpoint:

```text
cloudawsproject-101-db.c3gy4qeog199.ap-south-1.rds.amazonaws.com
```

The database remains private. The EC2 backend connects to it through the VPC/security-group path.

The database password was configured during creation and later supplied to the backend through the EC2 runtime `.env`. It is deliberately omitted from this document.

## 5.3 RDS schema

The backend setup created/verified these tables:

```text
files
file_versions
sync_logs
sync_changes
```

Conceptually:

- `files` — current file identity and state.
- `file_versions` — version history and hashes.
- `sync_logs` — synchronization activity.
- `sync_changes` — cloud/local change-feed state used by later synchronization work.

---

# 6. EC2 Security Group

## 6.1 Create the EC2 security group

AWS Console path:

**EC2 → Security Groups → Create security group**

Name:

```text
CloudAWSProject-EC2-SG
```

The important inbound ports are:

```text
TCP 22   SSH
TCP 8000 FastAPI
```

The FastAPI port is publicly reachable for project/demo access.

## 6.2 SSH rule lesson

Initially SSH port 22 was restricted to the public IP of the college Wi-Fi:

```text
136.233.9.123/32
```

When switching to a mobile network, SSH timed out because the mobile network had a different public IP.

Changing the SSH source to:

```text
0.0.0.0/0
```

restored SSH access.

The same rule also allowed AWS Console **EC2 Instance Connect** to work.

### Security recommendation

`0.0.0.0/0` on SSH is convenient but broad. For normal administration, use **My IP** or another appropriately restricted source whenever possible. For the project presentation, remember that changing networks can change the public IP.

---

# 7. Launch EC2

AWS Console path:

**EC2 → Instances → Launch instance**

Instance configuration:

```text
OS: Amazon Linux 2023
Architecture: x86_64
Instance type: t3.micro
Public IP: Enabled
Security group: CloudAWSProject-EC2-SG
Key pair: CloudAWSProject-EC2-Key
```

The instance used the default VPC/subnet and default storage setup; no additional file system was required.

Instance public IPv4 used during deployment:

```text
13.126.239.36
```

The instance passed the AWS status checks and was running.

---

# 8. EC2 Key Pair / Windows SSH

Key pair name:

```text
CloudAWSProject-EC2-Key
```

Windows PEM file:

```text
D:\sem5\AWS\project\Key-Pair\CloudAWSProject-EC2-Key.pem
```

Windows SSH command:

```powershell
ssh -i "D:\sem5\AWS\project\Key-Pair\CloudAWSProject-EC2-Key.pem" ec2-user@13.126.239.36
```

The PEM permissions were tightened using:

```powershell
icacls "D:\sem5\AWS\project\Key-Pair\CloudAWSProject-EC2-Key.pem" /inheritance:r
icacls "D:\sem5\AWS\project\Key-Pair\CloudAWSProject-EC2-Key.pem" /grant:r "$($env:USERNAME):(R)"
icacls "D:\sem5\AWS\project\Key-Pair\CloudAWSProject-EC2-Key.pem" /remove "Authenticated Users"
icacls "D:\sem5\AWS\project\Key-Pair\CloudAWSProject-EC2-Key.pem" /remove "Users"
```

After this, Windows OpenSSH accepted the key.

---

# 9. EC2 Software Setup

## 9.1 Install Git

On EC2:

```bash
sudo dnf install git -y
git --version
```

The repository was cloned into:

```text
~/CloudAWSProject-101
```

## 9.2 Install Python 3.11

Amazon Linux initially exposed Python 3.9, which was incompatible with parts of the project's current dependency/code expectations.

Installed:

```bash
sudo dnf install python3.11 python3.11-pip python3.11-devel -y
```

Then the project's virtual environment was recreated:

```bash
cd ~/CloudAWSProject-101
rm -rf backend/venv
python3.11 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt
```

Python verification:

```bash
python --version
which python
```

Expected executable:

```text
/home/ec2-user/CloudAWSProject-101/backend/venv/bin/python
```

---

# 10. EC2 Runtime Configuration

A `.env` file was created in the project root on EC2.

The important non-secret configuration was:

```text
APP_ENV=production
SYNC_FOLDER=./organization/files
BACKEND_URL=http://13.126.239.36:8000
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
STORAGE_ADAPTER=s3
AWS_REGION=ap-south-1
S3_BUCKET=cloudawsproject-101-482917-680476617705-ap-south-1-an
S3_PREFIX=organization/files
METADATA_ADAPTER=rds
RDS_HOST=cloudawsproject-101-db.c3gy4qeog199.ap-south-1.rds.amazonaws.com
RDS_PORT=5432
RDS_DATABASE=postgres
RDS_USERNAME=cloudadmin
RDS_SSLMODE=require
```

The database password and API key were also configured there, but are intentionally omitted from this reference.

`APP_ENV=production` is important because the backend uses it to enforce API-key authentication.

---

# 11. Network Verification

## 11.1 EC2 → S3

The IAM role was tested from EC2.

This was intentionally denied:

```bash
aws s3 ls
```

because `s3:ListAllMyBuckets` was not granted.

This succeeded:

```bash
aws s3 ls s3://cloudawsproject-101-482917-680476617705-ap-south-1-an
```

Therefore the EC2 IAM role could access the project bucket without broad S3 permissions.

## 11.2 EC2 → RDS

Installed the connectivity tool:

```bash
sudo dnf install nmap-ncat -y
```

Then:

```bash
nc -zv cloudawsproject-101-db.c3gy4qeog199.ap-south-1.rds.amazonaws.com 5432
```

Result confirmed TCP connection to PostgreSQL.

## 11.3 Internet → FastAPI

FastAPI was bound to:

```text
0.0.0.0:8000
```

The AWS security group allowed TCP 8000.

Swagger was verified from Windows at:

```text
http://13.126.239.36:8000/docs
```

---

# 12. RDS Schema Setup

From the project root on EC2:

```bash
cd ~/CloudAWSProject-101
source backend/venv/bin/activate
python -m backend.rds_setup
```

Using `python -m backend.rds_setup` was important because running the file directly from the wrong working directory caused Python package import resolution problems.

Successful result:

```text
Metadata schema created/verified...
Tables: files, file_versions, sync_logs, sync_changes
```

---

# 13. Start FastAPI — Original Method

The original manual startup was:

```bash
cd ~/CloudAWSProject-101
source backend/venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The command must be run from the **project root**, because the application imports the `backend` package.

Problem with this method:

- closing SSH kills Uvicorn;
- rebooting EC2 requires manually starting Uvicorn;
- the backend is not automatically restarted after a crash.

---

# 14. Final FastAPI Setup — systemd

To make the backend persistent, a Linux `systemd` service was created.

Service file:

```text
/etc/systemd/system/cloudaws-backend.service
```

Contents:

```ini
[Unit]
Description=CloudAWSProject FastAPI Backend
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/CloudAWSProject-101
Environment="PATH=/home/ec2-user/CloudAWSProject-101/backend/venv/bin"
ExecStart=/home/ec2-user/CloudAWSProject-101/backend/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Commands used:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cloudaws-backend
sudo systemctl start cloudaws-backend
```

Verification:

```bash
sudo systemctl status cloudaws-backend
```

Expected:

```text
Active: active (running)
```

The service was verified to remain available after closing the SSH session:

```powershell
curl.exe http://13.126.239.36:8000/health
```

Successful response:

```json
{"status":"ok","service":"hybrid-cloud-sync-backend"}
```

This is important: **SSH is now only an administration channel. The FastAPI backend does not depend on an open SSH terminal.**

---

# 15. Application Authentication

The backend uses application-level API-key authentication separately from AWS IAM.

This distinction matters:

- **IAM role:** controls EC2's permission to AWS services such as S3.
- **API key:** controls whether a client is allowed to call protected FastAPI endpoints.
- **Security groups:** control network-level access.

With production mode enabled:

```text
Missing/wrong API key → HTTP 401
Correct API key → HTTP 200
```

`/health` remains public for basic service health checking.

The API key is intentionally not stored in this document.

---

# 16. End-to-End Verification

A real local file was used for the M6 verification.

Local file:

```text
organization/files/m6-test.txt
```

The Windows Sync Agent watched the folder and sent events to the EC2 backend.

Flow:

```text
m6-test.txt
   ↓
Windows Sync Agent
   ↓ HTTP + X-API-Key
EC2 FastAPI
   ↓             ↓
  S3            RDS
```

The agent generated CREATED and MODIFIED events and received HTTP 200 responses.

The modified file reached **version 2**.

RDS recorded:

- file identity;
- current version;
- SHA-256 hash;
- size;
- synced status;
- S3 storage key;
- S3 version ID.

This verified the real AWS path rather than only local mock/adaptor behavior.

---

# 17. EC2 Instance Connect

AWS Console path:

**EC2 → Instances → select instance → Connect → EC2 Instance Connect → Connect**

The Amazon Linux instance has the package:

```text
ec2-instance-connect-1.1-19.amzn2023.noarch
```

Initially, browser EC2 Instance Connect failed because SSH port 22 was restricted to the old college Wi-Fi IP.

After changing the EC2 security group SSH rule to:

```text
TCP 22 → 0.0.0.0/0
```

both of these worked from the mobile network:

- normal Windows SSH;
- AWS Console EC2 Instance Connect.

Therefore the Instance Connect package itself was not the root problem.

---

# 18. Final AWS Resource Summary

| Resource | Name / Value |
|---|---|
| Region | `ap-south-1` — Mumbai |
| S3 bucket | `cloudawsproject-101-482917-680476617705-ap-south-1-an` |
| S3 prefix | `organization/files` |
| IAM policy | `CloudAWSProject-S3-Access` |
| IAM role | `CloudAWSProject-EC2-Role` |
| EC2 security group | `CloudAWSProject-EC2-SG` |
| RDS security group | `CloudAWSProject-RDS-SG` |
| RDS engine | PostgreSQL 18.3-R2 |
| RDS class | `db.t4g.micro` |
| RDS endpoint | `cloudawsproject-101-db.c3gy4qeog199.ap-south-1.rds.amazonaws.com` |
| RDS port | `5432` |
| RDS public access | No |
| EC2 OS | Amazon Linux 2023 |
| EC2 type | `t3.micro` |
| EC2 public IP used | `13.126.239.36` |
| EC2 key pair | `CloudAWSProject-EC2-Key` |
| FastAPI port | `8000` |
| systemd service | `cloudaws-backend.service` |

> **Note:** Public IP addresses can change if an EC2 instance is stopped and restarted unless an Elastic IP is used. The project did not use an Elastic IP in this setup.

---

# 19. What Must Be Recreated If AWS Resources Expire

If the current AWS environment disappears after the free/credit period, the general rebuild order is:

1. Create/select AWS account and choose `ap-south-1`.
2. Create S3 bucket.
3. Enable S3 Versioning.
4. Enable S3 Block Public Access.
5. Enable SSE-S3 default encryption.
6. Create `CloudAWSProject-S3-Access` least-privilege policy.
7. Create `CloudAWSProject-EC2-Role` with EC2 trust.
8. Create `CloudAWSProject-EC2-SG`.
9. Create `CloudAWSProject-RDS-SG` with PostgreSQL 5432 restricted to EC2 SG.
10. Create RDS PostgreSQL with Public access disabled.
11. Launch Amazon Linux 2023 EC2.
12. Attach the EC2 IAM role.
13. Attach the EC2 security group.
14. Configure SSH access and generate/download a new key pair.
15. Clone the GitHub repository.
16. Install Python 3.11 and dependencies.
17. Configure new runtime secrets in `.env`.
18. Run the RDS schema setup.
19. Verify EC2 → S3 and EC2 → RDS.
20. Start FastAPI through `systemd`.
21. Verify the public API.
22. Configure the Windows Sync Agent with the new backend URL and a new API key.
23. Run an end-to-end synchronization test.
24. Recreate/verify remaining M7-M10 infrastructure only when those modules require it.

Do **not** reuse old passwords/API keys simply because they appear elsewhere in old notes. Generate/configure fresh runtime secrets.

---

# 20. Useful Troubleshooting Lessons

### SSH times out

First check:

1. EC2 is Running.
2. EC2 status checks pass.
3. Public IPv4 is current.
4. Security group has TCP 22 allowed from your current network/IP.
5. The instance is reachable on TCP 22.

A changing Wi-Fi/mobile public IP can invalidate a `My IP`/`x.x.x.x/32` SSH rule.

### FastAPI disappears after SSH closes

If started manually with Uvicorn, this is expected. Use the `systemd` service:

```bash
sudo systemctl status cloudaws-backend
```

### Python package import errors

Run backend commands from:

```text
/home/ec2-user/CloudAWSProject-101
```

For module scripts, prefer:

```bash
python -m backend.rds_setup
```

rather than executing the file directly.

### S3 `ListAllMyBuckets` is denied

That is **not necessarily a problem**. It was intentionally denied by the least-privilege policy. Test the actual project bucket directly instead.

### API returns 401

Check:

- `APP_ENV=production` is set;
- the client sends the correct `X-API-Key`;
- the backend `.env` contains the matching runtime key.

---

# 21. Final State at M6 Completion

M6 is complete when all of the following are true:

- AWS resources exist in `ap-south-1`.
- S3 Versioning is enabled.
- S3 is not public.
- EC2 uses an IAM role rather than hardcoded AWS keys.
- RDS is private.
- RDS accepts PostgreSQL traffic from the EC2 security group.
- FastAPI runs on EC2.
- FastAPI uses production API-key authentication.
- The Windows Agent can communicate with EC2.
- A real local file reaches S3 and RDS.
- S3 versioning is exercised.
- Browser EC2 Instance Connect works.
- FastAPI runs persistently through `systemd` and survives SSH disconnection.

At this point, the project can proceed to:

```text
M7 — Bidirectional Synchronization
```

---

## 22. Why This Document Exists

`docs/PROGRESS.md` answers **"What have we completed?"**

`docs/Architecture.md` answers **"How is the system designed?"**

`docs/module-contracts.md` answers **"What are the module interfaces and boundaries?"**

This file answers:

> **"How the hell did I actually set up AWS from scratch, and how do I rebuild it when these credits die?"**

Keep this document as the practical AWS setup reference. Update it if resource names, architecture, AWS services, or deployment procedures materially change.
