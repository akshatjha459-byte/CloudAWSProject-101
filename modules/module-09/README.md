# Module 09 — Monitoring, Logging & Alerting

## 1. Overview

Module 09 adds operational visibility around the existing M1–M8 synchronization system:

- structured application logs
- reuse of RDS `sync_logs`
- CloudWatch application metrics
- SNS alerts for repeated or critical failures

Synchronization behavior is unchanged. Monitoring is auxiliary: CloudWatch, SNS, or RDS log-write failures never fail a successful file operation.

This module does **not** implement a dashboard (M10) and does **not** replace CloudTrail. CloudTrail remains an AWS-account audit trail configured in the AWS console; it is separate from application `SYNC_LOGS`.

## 2. What M9 adds

| Area | Implementation |
|---|---|
| Structured logs | `backend/services/observability.py` JSON logs (`event`, `level`, `timestamp`, path, success/failure, conflict fields) |
| RDS logs | Existing `sync_logs` via `SyncService._safe_add_log` (`SUCCESS` and `FAILURE`) |
| CloudWatch | `PutMetricData` into namespace `CloudAWSProject/Sync` |
| SNS | Publish only for defined alert conditions |
| Status | Existing `GET /status` `notes` include `cloudwatch`, `sns`, and `monitoring` |
| IAM | `infrastructure/iam_policies/ec2_monitoring_policy.json` |

## 3. Logging architecture

Two complementary logs:

1. **RDS `sync_logs` (M5)** — durable application audit of CREATED / MODIFIED / DELETED / MOVED / CONFLICT / FAILURE. Exposed by `GET /logs`.
2. **Process structured logs (M9)** — JSON lines on the backend logger `backend.observability` for operators and CloudWatch Logs / journald if the instance is so configured.

Important events:

- file upload / creation / modification / deletion
- synchronization success and failure
- conflict detection / preservation
- authentication failures (`auth.failure`)
- unexpected application errors (`application.error`)

Secrets (`API_KEY`, `RDS_PASSWORD`, credential-like keys, URLs with userinfo) are redacted. Logging exceptions are swallowed.

## 4. CloudWatch metrics

Namespace: `CLOUDWATCH_NAMESPACE` (default `CloudAWSProject/Sync`).

| Metric | Meaning |
|---|---|
| `SyncOperations` | Each sync attempt (dimension `Operation`) |
| `SyncSuccess` | Successful sync including conflict preservation |
| `SyncFailure` | Validation or operational sync failure |
| `ConflictEvents` | M8 conflict detections |
| `ApplicationErrors` | Unhandled backend exceptions |
| `AuthFailures` | Production API-key rejections |

Metrics are emitted with the EC2 instance role. No access keys are stored in source.

Auto-enable: production (`APP_ENV=production`) with `CLOUDWATCH_METRICS_ENABLED=true` and `AWS_REGION` set. Local pytest injects mock clients and does not require live AWS.

## 5. SNS alert conditions

Topic: `SNS_ALERT_TOPIC_ARN`. Empty ARN disables publishing.

Alerts are **not** sent for normal successful syncs.

| Reason | When |
|---|---|
| `repeated_sync_failures` | Consecutive sync failures reach `SNS_SYNC_FAILURE_THRESHOLD` (default 3). One alert per failure streak; a success resets the streak. |
| `critical_application_error` | Unhandled backend exception (HTTP 500). One alert per event name per process. |
| `repeated_auth_failures` | Consecutive production 401s reach `SNS_AUTH_FAILURE_THRESHOLD` (default 5). One alert per streak. |

SNS publish failures are ignored by the sync path.

## 6. Failure isolation

- CloudWatch `PutMetricData` errors → ignored
- SNS `Publish` errors → ignored
- RDS `add_log` errors → structured `logging.failure` only; the file operation still commits
- Observability methods never raise into `SyncService` callers

## 7. AWS / IAM requirements

Attach `ec2_monitoring_policy.json` to `CloudAWSProject-EC2-Role` (in addition to the M6 S3 policy):

- `cloudwatch:PutMetricData` limited by `cloudwatch:namespace` = `CloudAWSProject/Sync`
- `sns:Publish` limited to the project alert topic ARN

Create an SNS topic and subscribe an email (or other endpoint) for the demonstration. Set `SNS_ALERT_TOPIC_ARN` on EC2. CloudTrail, if used for the academic demo, is enabled at account/region level in the AWS console — not by application code.

## 8. Configuration

See `.env.example` (Module 9 section). Production EC2 already uses the instance role for S3; the same role is used for CloudWatch and SNS after the monitoring policy is attached.

## 9. How to test

```bash
pytest modules/module-09/tests/test_m9.py -v
pytest modules/module-08/tests/test_m8.py -v
```

Unit tests mock CloudWatch and SNS. They do not require live AWS credentials.
