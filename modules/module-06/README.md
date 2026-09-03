# Module 6: AWS IAM, Security & Deployment

This module secures the CloudAWSProject-101 architecture and prepares it for real-world deployment on an Amazon EC2 instance using your AWS account. 

## Architectural Security Model

1. **Authentication (Agent ↔ EC2 Backend):**
   The FastAPI backend uses an application-level API key (`X-API-Key` header). The local Sync Agent must be configured with this key to push updates. This prevents unauthorized users from modifying your organization files.

2. **IAM Least Privilege (EC2 ↔ AWS Services):**
   The EC2 backend uses an **IAM Instance Role**, not hardcoded access keys. The AWS SDK (boto3) automatically retrieves short-lived temporary credentials from the EC2 instance metadata service. The policy grants strictly the permissions required for the application to function (e.g., `s3:PutObject`, `s3:GetObject`), and excludes infrastructure-management permissions like `s3:PutBucketVersioning`.

3. **Network Isolation (Internet ↔ EC2 ↔ RDS):**
   The RDS PostgreSQL database must **not** be publicly accessible. It must reside in a security group that only accepts inbound PostgreSQL traffic (port 5432) from the EC2 backend's security group.

## Implementation Status

### A. Code Verified Locally (Completed)
- [x] API Key enforcement middleware (`backend/routes/api.py`).
- [x] `APP_ENV` configuration to strictly enforce authentication in `production` and allow bypass in `development`.
- [x] Agent HTTP sender updated to transmit the `X-API-Key` header.
- [x] IAM Least-Privilege Policy template (`ec2_s3_policy.json`).
- [x] IAM Trust Policy (`trust_policy_ec2.json`).
- [x] Environment variable placeholders properly configured in `.env.example`.
- [x] Git ignores updated to prevent leaking `.env` and secrets.
- [x] Local test suite passes (113/113 tests).

### B. AWS Console Configuration Required (Pending User Action)
Since this project uses a real AWS account, you must perform the following infrastructure steps in the AWS Console.

1. **S3 Bucket Creation:**
   - Create an S3 bucket (e.g., `my-cloudaws-bucket`).
   - Enable S3 Bucket Versioning.

2. **IAM Configuration:**
   - Go to IAM -> Policies -> Create Policy.
   - Paste the contents of `infrastructure/iam_policies/ec2_s3_policy.json` (Replace `YOUR-BUCKET-NAME` with your actual bucket name).
   - Go to IAM -> Roles -> Create Role (Trusted entity: EC2).
   - Attach the newly created S3 policy to the role.

3. **Security Groups:**
   - Create an **EC2 Security Group**: Allow inbound HTTP (TCP 80 or 8000) from the internet, and SSH (TCP 22) from your IP.
   - Create an **RDS Security Group**: Allow inbound PostgreSQL (TCP 5432) **ONLY** from the EC2 Security Group. Do not allow `0.0.0.0/0`.

4. **RDS Database:**
   - Launch a PostgreSQL RDS instance in the same VPC as your EC2.
   - Attach the **RDS Security Group**.
   - Ensure "Public access" is set to **No**.

5. **EC2 Deployment:**
   - Launch an EC2 instance (Amazon Linux 2023 or Ubuntu).
   - Under "Advanced details", attach the **IAM Role** created in Step 2.
   - Attach the **EC2 Security Group**.
   - SSH into the instance, install Python 3, and clone this repository.
   - Set up the environment variables (e.g., in a `.env` file on the instance, **never** commit this).
     ```env
     APP_ENV=production
     API_KEY=your-secure-random-string
     AWS_REGION=us-east-1
     S3_BUCKET=my-cloudaws-bucket
     STORAGE_ADAPTER=s3
     METADATA_ADAPTER=rds
     RDS_HOST=your-rds-endpoint.amazonaws.com
     RDS_PORT=5432
     RDS_DATABASE=your_db_name
     RDS_USERNAME=your_db_user
     RDS_PASSWORD=your_db_password
     ```
   - Start the FastAPI application (e.g., using `uvicorn backend.main:app --host 0.0.0.0 --port 8000`).

6. **Local Agent Configuration:**
   - On your local machine, configure `.env`:
     ```env
     BACKEND_URL=http://<your-ec2-public-ip>:8000
     API_KEY=your-secure-random-string
     ```
   - Start the sync agent: `python -m agent.agent`

### C. AWS Configuration Actually Verified (Pending)
The following must be explicitly verified by you once the AWS environment is running:

- [ ] EC2 successfully authenticates with S3 via the IAM Instance Role (no access keys hardcoded).
- [ ] EC2 successfully connects to the RDS instance.
- [ ] Direct internet access to the RDS instance is blocked.
- [ ] Local Sync Agent successfully connects to EC2 and pushes files.
- [ ] Unauthorized requests (missing or wrong `X-API-Key`) to the EC2 backend return HTTP 401.
- [ ] Authorized requests to the EC2 backend succeed.
