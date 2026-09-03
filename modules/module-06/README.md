# Module 6: AWS IAM, Security & Deployment Verification

Module 6 establishes the AWS security boundary and deployment verification gate. It is fully complete only after the local security implementation and the real AWS environment have both been verified.

## Scope

M6 owns:
- EC2 IAM role / instance profile and least-privilege AWS permissions.
- Application authentication between the Synchronization Agent and EC2.
- EC2/RDS network isolation and security-group requirements.
- Deployment configuration required to run the existing backend on EC2.
- Verification that EC2 can securely reach S3 and RDS and that the Agent can securely reach EC2.

M6 does **not** own bidirectional synchronization. **M7 remains Bidirectional Synchronization.** M6 also does not redesign M4 S3 storage, M5 RDS schema/repository, M8 conflict handling, M9 monitoring/alerting, or M10 dashboard behavior.

## Security Model

1. **Agent -> EC2:** FastAPI protected endpoints use the application-level `X-API-Key` mechanism. `/health` remains public. In production, protected endpoints require the configured key; missing or incorrect keys return HTTP 401.
2. **EC2 -> AWS:** EC2 uses an IAM instance role / instance profile. No long-lived AWS access keys are stored in the application. boto3 uses the EC2 role's temporary credentials.
3. **Least privilege:** The runtime policy is restricted to the actual project S3 bucket and only the S3 actions required by the application. Infrastructure-management permissions such as `s3:PutBucketVersioning` are not runtime permissions.
4. **Network isolation:** RDS PostgreSQL is not publicly accessible. Inbound TCP 5432 must be allowed only from the EC2 security group, not `0.0.0.0/0`.

## Code Verification — Completed

- [x] API-key authentication for protected API endpoints.
- [x] Public `/health` endpoint.
- [x] Production authentication behavior.
- [x] Agent sends `X-API-Key` without hardcoding it.
- [x] Least-privilege S3 policy template using `YOUR-BUCKET-NAME`.
- [x] EC2 trust policy.
- [x] `.env.example` uses placeholders; real secrets are excluded from Git.
- [x] 113/113 tests passed in the M6 regression suite.

## AWS Deployment — Pending

The project uses the user's real AWS account and available credits. M6 AWS deployment must be completed before M7 starts.

### S3
- Create the project bucket.
- Enable S3 Versioning.
- Record the exact bucket name.

### IAM
- Create a customer-managed policy from `infrastructure/iam_policies/ec2_s3_policy.json`.
- Replace `YOUR-BUCKET-NAME` with the actual bucket name before creating the policy.
- Create an IAM role trusted by EC2.
- Attach the S3 policy to the role.
- Attach the role/instance profile to EC2.
- Do not put AWS access keys in the repository or deployed application.

### Security Groups
Create separate EC2 and RDS security groups.

**EC2:**
- Allow only the backend port needed for the demonstration (for example TCP 8000).
- Restrict SSH TCP 22 to the administrator's IP where possible.
- Do not expose unrelated ports.

**RDS:**
- Allow TCP 5432 only from the EC2 security group.
- Do not allow `0.0.0.0/0` for PostgreSQL.
- Set RDS Public access to **No**.

### RDS PostgreSQL
- Create PostgreSQL RDS in the same VPC as EC2.
- Attach the RDS security group.
- Keep endpoint, username, database name and password out of Git.

### EC2 Backend
- Launch a supported Linux EC2 instance.
- Attach the EC2 security group and IAM role.
- Clone the repository.
- Configure a real `.env` on the instance, never commit it.

Example configuration:

```env
APP_ENV=production
API_KEY=<set-a-secret-api-key>
AWS_REGION=<actual-region>
S3_BUCKET=<actual-bucket-name>
STORAGE_ADAPTER=s3
METADATA_ADAPTER=rds
RDS_HOST=<actual-rds-endpoint>
RDS_PORT=5432
RDS_DATABASE=<actual-database>
RDS_USERNAME=<actual-user>
RDS_PASSWORD=<actual-password>
```

Start the existing FastAPI application, for example:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Local Agent

Configure the demonstration laptop with the EC2 endpoint and application key:

```env
BACKEND_URL=http://<ec2-endpoint>:8000
API_KEY=<same-api-key-used-by-backend>
```

The demonstration laptop does **not** need AWS credentials or direct RDS access.

## AWS Verification Checklist

M6 is **FULLY COMPLETE** only after these real-AWS checks pass:

- [ ] EC2 has the intended IAM role/instance profile attached.
- [ ] EC2 accesses the project S3 bucket using the IAM role and no hardcoded AWS keys.
- [ ] S3 Versioning is enabled.
- [ ] EC2 connects to RDS PostgreSQL.
- [ ] RDS is not publicly accessible.
- [ ] RDS inbound TCP 5432 accepts traffic only from the EC2 security group.
- [ ] Agent reaches the EC2 backend.
- [ ] Missing `X-API-Key` returns HTTP 401 on a protected endpoint.
- [ ] Incorrect `X-API-Key` returns HTTP 401.
- [ ] Correct `X-API-Key` succeeds.
- [ ] A real local file completes Agent -> EC2 -> S3/RDS using the existing M1-M5 contracts.

Record actual results. Do not mark an AWS check complete based only on documentation or local tests.

## Current Status

**Code/security implementation:** VERIFIED.

**AWS deployment:** PENDING.

**Next safe step:** Complete the AWS deployment and verification checklist above. Do **not** start M7 until this gate is complete.

## Future Module Boundaries

- **M7:** Bidirectional Synchronization — cloud-to-local and local-to-cloud synchronization behavior.
- **M8:** Versioning & Conflict Handling — conflict detection/resolution using the existing state and version model.
- **M9:** Monitoring, Logging & Alerting — CloudWatch, CloudTrail, SNS and operational visibility.
- **M10:** Frontend Dashboard — dashboard through the M3 REST API; no direct RDS access.

Future modules must consume the existing contracts rather than moving M6 security responsibilities or redefining the module sequence.
