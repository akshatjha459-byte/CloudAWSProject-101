# Module 6 — AWS IAM / Security

## Purpose

Module 6 implements the least-privilege security controls, IAM role/policy templates, and API authentication layer for the hybrid cloud file synchronization system.

## Key Features

1. **Least-Privilege IAM Policies (`infrastructure/iam_policies/`):**
   - `ec2_s3_policy.json`: Restricts S3 actions (`PutObject`, `GetObject`, `DeleteObject`, `ListBucket`, `GetBucketVersioning`, `PutBucketVersioning`) strictly to the application bucket and prefix.
   - `trust_policy_ec2.json`: Trust relationship allowing the EC2 service principal (`ec2.amazonaws.com`) to assume the EC2 IAM Role.

2. **API Authentication (`X-API-Key`):**
   - Protects backend REST endpoints (`/sync/upload`, `/sync/delete`, `/sync/changes`, `/files`, `/logs`, `/status`) when `API_KEY` environment variable is set.
   - `/health` remains accessible for load balancer and health check probes.
   - `HttpEventSender` automatically attaches `X-API-Key` header to agent requests.

3. **AWS Security Group Architecture:**
   - **EC2 Security Group (`CloudAWSProject-EC2-SG`):** Inbound HTTP (port 8000/80/443) and SSH (port 22). Outbound all.
   - **RDS Security Group (`CloudAWSProject-RDS-SG`):** Inbound PostgreSQL (port 5432) restricted strictly to `CloudAWSProject-EC2-SG`. No public internet exposure.

## Setup & Verification

Run the test suite:
```bash
python -m pytest modules/module-06/tests/test_m6.py -v
```
