# AWS Explainer — Module 9

This document records the real AWS setup, deployment fixes, and verification performed for Module 9 (Monitoring, Logging & Alerting) on 2026-09-04. It is a practical future-reference document. Runtime secrets such as the API key, RDS password, and full SNS topic ARN are intentionally omitted.

## 1. M9 objective

M9 adds operational visibility without changing the M1-M8 synchronization contracts:

- structured application logging;
- durable RDS `sync_logs` audit entries remain in place;
- CloudWatch application metrics;
- SNS alerts for repeated/critical failures;
- least-privilege IAM permissions for CloudWatch/SNS.

CloudTrail remains an AWS-account audit service and is not reimplemented by the application.

## 2. Important deployment issue discovered

The EC2 repository was initially behind GitHub after M9 had been committed.

EC2 state before the fix:

```text
e3e9a0b  (EC2 HEAD / old deployment)
```

GitHub `origin/main` after `git fetch`:

```text
160ae43  feat(m9): Implement Module 9 - Monitoring, Logging & Alerting
```

`git fetch` only updated the remote-tracking reference; it did not update the EC2 working tree. This explained why the live EC2 backend initially had no `observability.py` and no M9 hooks even though GitHub contained M9.

Fix:

```bash
git fetch origin
git pull origin main
```

After the pull, EC2 was confirmed at:

```text
160ae43 (HEAD -> main, origin/main, origin/HEAD)
```

and the following were present:

```text
backend/services/observability.py
```

with `Observability` hooks in `backend/services/sync_service.py`.

## 3. EC2 production environment for M9

The existing EC2 runtime `.env` was extended with:

```text
APP_ENV=production
AWS_REGION=ap-south-1
CLOUDWATCH_NAMESPACE=CloudAWSProject/Sync
CLOUDWATCH_METRICS_ENABLED=true
SNS_ALERT_TOPIC_ARN=<actual project SNS topic ARN>
SNS_ALERTS_ENABLED=true
SNS_SYNC_FAILURE_THRESHOLD=3
SNS_AUTH_FAILURE_THRESHOLD=5
```

The actual API key, RDS password, and SNS ARN are not recorded here.

## 4. systemd environment fix

The FastAPI service already ran through:

```text
cloudaws-backend.service
```

To ensure the production `.env` was loaded by the systemd-managed process, the service definition was updated with:

```ini
EnvironmentFile=/home/ec2-user/CloudAWSProject-101/.env
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart cloudaws-backend.service
```

The service was verified `active (running)` and the live process environment contained the expected `APP_ENV`, `AWS_REGION`, `CLOUDWATCH_*`, and `SNS_*` settings.

This systemd change is an EC2 runtime configuration and is not a repository secret.

## 5. M9 application implementation

`backend/services/observability.py` provides:

### StructuredLogger

- JSON records with timestamp, level and event;
- file/synchronization success and failure events;
- conflict events;
- authentication failures;
- application errors;
- configured-secret and credential-like value redaction;
- logging failures are swallowed so observability cannot break synchronization.

The logger uses Python's `backend.observability` logger. A direct EC2 test with `logging.basicConfig(level=logging.INFO)` successfully produced a structured JSON log record, proving the logger implementation works.

The normal systemd journal showed Uvicorn access/startup logs but did not display the structured record during the upload test. No application behavior was changed solely for this because the M9 implementation intentionally keeps logging auxiliary/non-blocking.

### CloudWatchMetrics

Uses the AWS SDK and the EC2 IAM role to call:

```text
cloudwatch:PutMetricData
```

Default namespace:

```text
CloudAWSProject/Sync
```

Metrics implemented:

```text
SyncOperations
SyncSuccess
SyncFailure
ConflictEvents
ApplicationErrors
AuthFailures
```

The implementation does not use hardcoded AWS access keys.

### SnsAlerter

Uses the EC2 IAM role to call:

```text
sns:Publish
```

Alert conditions:

- repeated sync failures: default threshold 3;
- repeated authentication failures: default threshold 5;
- critical/unhandled application errors;
- security failure events.

Anti-spam behavior ensures one alert per failure streak/event condition. A successful synchronization resets the sync-failure streak.

CloudWatch/SNS failures are swallowed and cannot fail the synchronization path.

## 6. IAM setup performed in AWS

Existing EC2 role:

```text
CloudAWSProject-EC2-Role
```

Existing M6 policy remained attached:

```text
CloudAWSProject-S3-Access
```

A new customer-managed policy was created and attached:

```text
CloudAWSProject-Monitoring
```

Effective permissions:

```text
cloudwatch:PutMetricData
sns:Publish
```

CloudWatch permission is constrained to the project namespace:

```text
CloudAWSProject/Sync
```

SNS publish is constrained to the project alert topic.

The policy deliberately does not grant broad CloudWatch read permissions, `sns:CreateTopic`, `sns:Subscribe`, or unrestricted `logs:*` access.

## 7. SNS topic and subscription setup

AWS Console:

```text
SNS → Topics → Create topic → Standard
```

Topic created:

```text
CloudAWSProject-Alerts
```

An email subscription was created for the topic. The confirmation email initially landed in spam and was confirmed.

The EC2 role was then tested directly with:

```bash
aws sns publish \
  --topic-arn "<project SNS topic ARN>" \
  --subject "M9 Test Alert" \
  --message "CloudAWSProject M9 SNS connectivity test."
```

AWS returned a MessageId, proving the EC2 instance role could publish to the configured topic.

## 8. CloudWatch verification

The application was tested with the actual `CloudWatchMetrics.increment()` API:

```bash
python -c "from backend.services.observability import CloudWatchMetrics; m=CloudWatchMetrics(namespace='CloudAWSProject/Sync', region='ap-south-1', enabled=True); m.increment('M9TestMetric'); print(m.emitted)"
```

The call produced:

```text
[{'MetricName': 'M9TestMetric', 'Value': 1.0, 'Unit': 'Count'}]
```

AWS Console verification then showed the custom namespace:

```text
CloudAWSProject/Sync
```

and metrics including:

```text
M9Metric
M9TestMetric
SyncSuccess
```

Therefore CloudWatch custom-metric publishing is verified end-to-end.

### About CloudWatch alarms

No CloudWatch alarm objects were created for these metrics. This is expected for the current M9 design: application alerting is implemented directly through SNS threshold logic rather than CloudWatch Alarm resources.

## 9. Live M9 synchronization verification

After pulling M9 onto EC2 and restarting the systemd service, a fresh upload was performed:

```text
m9-test-2.txt
```

The backend returned a successful synchronization response containing:

```text
success: true
message: synchronized
status: synced
is_conflict: false
conflict: false
```

This verified that the M9 instrumentation did not break the existing M1-M8 synchronization path.

## 10. SNS failure-alert verification

Three controlled upload requests were sent using a valid `CREATED` operation but without file content:

```text
file content is required for CREATED and MODIFIED
```

Each request reached `SyncService.upload()`, where the exception was passed to `_observe_failure()` and therefore to the M9 failure counter.

The configured threshold was 3 consecutive sync failures.

The third failure triggered the configured SNS alert:

```text
Repeated Sync Failures
```

The alert email was received successfully.

This verifies the complete application path:

```text
Sync failure
    ↓
SyncService._observe_failure()
    ↓
Observability.on_sync_failure()
    ↓
SnsAlerter.record_sync_failure()
    ↓
SNS Publish
    ↓
Email subscription
```

The controlled failures occur before S3/RDS file mutation because the upload had no file content, so no test file was created by those three failure requests.

## 11. M9 test status

Focused M9 suite:

```text
14 passed
1 warning
```

The tests cover:

- `/health` and `/status` preservation;
- expected structured events;
- synchronization failures;
- conflict logging;
- secret redaction;
- CloudWatch metric emission;
- CloudWatch failure isolation;
- SNS repeated/critical alerting;
- anti-spam behavior;
- SNS failure isolation;
- M8 conflict behavior preservation;
- RDS logging failure isolation;
- least-privilege monitoring IAM policy.

Full project regression after M9 implementation:

```text
154 passed, 2 skipped, 1 warning
```

The skipped tests are the optional live S3/RDS integration tests that are not required for the local regression suite.

## 12. CloudTrail status

CloudTrail remains separate from application logging and is intended to provide the AWS-account API audit trail.

M9 code does not create or manage CloudTrail resources.

At the time of this document, CloudTrail was **not independently re-verified as an M9 AWS-console step**, so future verification should check AWS Console → CloudTrail → Event history/trails before the final demonstration if CloudTrail evidence is required by the rubric.

## 13. Important future rebuild notes

1. Recreate the SNS topic and confirm the email subscription.
2. Attach the M9 monitoring policy to `CloudAWSProject-EC2-Role`.
3. Replace the SNS ARN in the runtime `.env` with the new topic ARN.
4. Keep CloudWatch namespace as `CloudAWSProject/Sync` unless intentionally changed in configuration.
5. Use the EC2 instance role; never put AWS access keys in the repository.
6. Ensure `cloudaws-backend.service` loads the runtime `.env` with `EnvironmentFile=`.
7. After deployment, verify `git rev-parse HEAD` and `git rev-parse origin/main` match before testing the live service.
8. Verify the CloudWatch custom namespace and at least `SyncSuccess`.
9. Trigger one controlled repeated-failure scenario and confirm the SNS email before the final demo.
10. Do not create CloudWatch alarms unless the project requirements specifically call for them; current M9 application alerting is SNS-based.

## 14. M9 AWS completion state

```text
M9 application code             COMPLETE
M9 code deployed to EC2         COMPLETE
M9 systemd runtime config       COMPLETE
IAM CloudWatch/SNS permissions  COMPLETE
SNS topic + email subscription  COMPLETE
CloudWatch custom metrics       VERIFIED
SNS repeated-failure alert     VERIFIED
Live successful sync            VERIFIED
CloudTrail console verification PENDING
```

M10 can now proceed after the remaining CloudTrail verification is handled if it is required for the final project demonstration.
