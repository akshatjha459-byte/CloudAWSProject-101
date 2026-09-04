"""
observability.py — Module 9: monitoring, structured logging, and alerting.

CloudWatch metrics and SNS alerts are auxiliary.  Every public method swallows
exceptions so monitoring never becomes a synchronization dependency.

RDS SYNC_LOGS remain the application audit trail (M5).  This module adds
process-level structured logs plus optional AWS operational signals.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger("backend.observability")

CLOUDWATCH_NAMESPACE = "CloudAWSProject/Sync"

METRIC_SYNC_OPERATIONS = "SyncOperations"
METRIC_SYNC_SUCCESS = "SyncSuccess"
METRIC_SYNC_FAILURE = "SyncFailure"
METRIC_CONFLICT_EVENTS = "ConflictEvents"
METRIC_APPLICATION_ERRORS = "ApplicationErrors"
METRIC_AUTH_FAILURES = "AuthFailures"

ALERT_REPEATED_SYNC_FAILURES = "repeated_sync_failures"
ALERT_CRITICAL_APPLICATION_ERROR = "critical_application_error"
ALERT_REPEATED_AUTH_FAILURES = "repeated_auth_failures"
ALERT_SECURITY_FAILURE = "security_failure"

_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "session_token",
    "authorization",
    "database_url",
    "db_url",
    "dsn",
    "token",
)

_URL_WITH_USERINFO = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s]*:[^\s]*@[^\s]+")

LogSink = Callable[[dict[str, Any]], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_value(value: Any) -> Any:
    """Remove secrets from structured log payloads."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_key(str(key)) else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        if _URL_WITH_USERINFO.search(value):
            return _URL_WITH_USERINFO.sub("[REDACTED_URL]", value)
        return _redact_configured_secrets(value)
    return value


def _configured_secrets() -> list[str]:
    secrets: list[str] = []
    try:
        from backend import config

        for candidate in (
            getattr(config, "API_KEY", ""),
            getattr(config, "RDS_PASSWORD", ""),
        ):
            if candidate and len(str(candidate)) >= 4:
                secrets.append(str(candidate))
    except Exception:
        pass
    return secrets


def _redact_configured_secrets(text: str) -> str:
    redacted = text
    for secret in _configured_secrets():
        if secret and secret in redacted:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    return sanitize_value(record)


class StructuredLogger:
    """JSON application logger with optional in-memory sinks for tests."""

    def __init__(self, sinks: Optional[list[LogSink]] = None) -> None:
        self._sinks = list(sinks or [])
        self.records: list[dict[str, Any]] = []

    def add_sink(self, sink: LogSink) -> None:
        self._sinks.append(sink)

    def emit(self, level: str, event: str, **fields: Any) -> None:
        try:
            payload = sanitize_record(
                {
                    "timestamp": utc_now_iso(),
                    "level": level.upper(),
                    "event": event,
                    **fields,
                }
            )
            self.records.append(payload)
            line = json.dumps(payload, default=str, separators=(",", ":"))
            log_level = getattr(logging, payload["level"], logging.INFO)
            logger.log(log_level, line)
            for sink in self._sinks:
                try:
                    sink(payload)
                except Exception:
                    pass
        except Exception:
            # Logging must never raise into the sync path.
            return


class CloudWatchMetrics:
    """Best-effort CloudWatch PutMetricData wrapper."""

    def __init__(
        self,
        *,
        namespace: str = CLOUDWATCH_NAMESPACE,
        region: str = "",
        client: Any = None,
        enabled: bool = True,
    ) -> None:
        self.namespace = namespace or CLOUDWATCH_NAMESPACE
        self.region = (region or "").strip()
        self._client = client
        self.enabled = bool(enabled)
        self.emitted: list[dict[str, Any]] = []

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.enabled or not self.region:
            return None
        try:
            import boto3

            self._client = boto3.client("cloudwatch", region_name=self.region)
            return self._client
        except Exception:
            return None

    def increment(
        self,
        metric_name: str,
        *,
        value: float = 1.0,
        dimensions: Optional[dict[str, str]] = None,
        unit: str = "Count",
    ) -> None:
        try:
            datum: dict[str, Any] = {
                "MetricName": metric_name,
                "Value": float(value),
                "Unit": unit,
            }
            if dimensions:
                datum["Dimensions"] = [
                    {"Name": str(name), "Value": str(val)}
                    for name, val in dimensions.items()
                    if name and val is not None
                ]
            self.emitted.append(datum)
            client = self._resolve_client()
            if client is None:
                return
            client.put_metric_data(Namespace=self.namespace, MetricData=[datum])
        except Exception:
            return


class SnsAlerter:
    """SNS publisher with deterministic anti-spam rules."""

    def __init__(
        self,
        *,
        topic_arn: str = "",
        region: str = "",
        client: Any = None,
        sync_failure_threshold: int = 3,
        auth_failure_threshold: int = 5,
        enabled: bool = True,
    ) -> None:
        self.topic_arn = (topic_arn or "").strip()
        self.region = (region or "").strip()
        self._client = client
        self.sync_failure_threshold = max(1, int(sync_failure_threshold))
        self.auth_failure_threshold = max(1, int(auth_failure_threshold))
        self.enabled = bool(enabled) and bool(self.topic_arn)
        self.published: list[dict[str, Any]] = []
        self._consecutive_sync_failures = 0
        self._sync_streak_alerted = False
        self._consecutive_auth_failures = 0
        self._auth_streak_alerted = False
        self._critical_alerted: set[str] = set()

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.enabled or not self.region:
            return None
        try:
            import boto3

            self._client = boto3.client("sns", region_name=self.region)
            return self._client
        except Exception:
            return None

    def record_sync_success(self) -> None:
        self._consecutive_sync_failures = 0
        self._sync_streak_alerted = False

    def record_sync_failure(self, *, operation: str, path: str, error: str) -> None:
        self._consecutive_sync_failures += 1
        if (
            self._consecutive_sync_failures >= self.sync_failure_threshold
            and not self._sync_streak_alerted
        ):
            self._publish(
                ALERT_REPEATED_SYNC_FAILURES,
                f"Repeated synchronization failures ({self._consecutive_sync_failures})",
                {
                    "operation": operation,
                    "path": path,
                    "error": error,
                    "consecutive_failures": self._consecutive_sync_failures,
                    "threshold": self.sync_failure_threshold,
                },
            )
            self._sync_streak_alerted = True

    def record_auth_failure(self) -> None:
        self._consecutive_auth_failures += 1
        if (
            self._consecutive_auth_failures >= self.auth_failure_threshold
            and not self._auth_streak_alerted
        ):
            self._publish(
                ALERT_REPEATED_AUTH_FAILURES,
                f"Repeated authentication failures ({self._consecutive_auth_failures})",
                {
                    "consecutive_failures": self._consecutive_auth_failures,
                    "threshold": self.auth_failure_threshold,
                },
            )
            self._auth_streak_alerted = True

    def record_auth_success(self) -> None:
        self._consecutive_auth_failures = 0
        self._auth_streak_alerted = False

    def record_critical_error(self, *, error: str, event: str = "application.error") -> None:
        key = event
        if key in self._critical_alerted:
            return
        self._publish(
            ALERT_CRITICAL_APPLICATION_ERROR,
            "Critical application failure",
            {"event": event, "error": error},
        )
        self._critical_alerted.add(key)

    def record_security_failure(self, *, detail: str) -> None:
        # Distinct from routine 401s: used for unexpected security faults.
        self._publish(
            ALERT_SECURITY_FAILURE,
            "Security failure",
            {"detail": detail},
        )

    def _publish(self, reason: str, subject: str, details: dict[str, Any]) -> None:
        try:
            message = sanitize_record(
                {
                    "reason": reason,
                    "subject": subject,
                    "timestamp": utc_now_iso(),
                    "details": details,
                }
            )
            self.published.append(message)
            if not self.enabled:
                return
            client = self._resolve_client()
            if client is None:
                return
            client.publish(
                TopicArn=self.topic_arn,
                Subject=subject[:100],
                Message=json.dumps(message, default=str),
            )
        except Exception:
            return


class Observability:
    """Facade used by the backend.  All methods are failure-isolated."""

    def __init__(
        self,
        *,
        structured: Optional[StructuredLogger] = None,
        metrics: Optional[CloudWatchMetrics] = None,
        alerts: Optional[SnsAlerter] = None,
    ) -> None:
        self.structured = structured or StructuredLogger()
        self.metrics = metrics or CloudWatchMetrics(enabled=False)
        self.alerts = alerts or SnsAlerter(enabled=False)

    @classmethod
    def from_env(cls) -> "Observability":
        from backend import config

        region = getattr(config, "AWS_REGION", "") or ""
        namespace = getattr(config, "CLOUDWATCH_NAMESPACE", CLOUDWATCH_NAMESPACE)
        topic = getattr(config, "SNS_ALERT_TOPIC_ARN", "") or ""
        production = getattr(config, "APP_ENV", "development") == "production"
        cw_enabled = bool(getattr(config, "CLOUDWATCH_METRICS_ENABLED", False)) and production
        sns_enabled = bool(getattr(config, "SNS_ALERTS_ENABLED", False)) and production
        return cls(
            structured=StructuredLogger(),
            metrics=CloudWatchMetrics(
                namespace=namespace,
                region=region,
                enabled=cw_enabled and bool(region),
            ),
            alerts=SnsAlerter(
                topic_arn=topic,
                region=region,
                enabled=sns_enabled and bool(topic),
                sync_failure_threshold=int(
                    getattr(config, "SNS_SYNC_FAILURE_THRESHOLD", 3) or 3
                ),
                auth_failure_threshold=int(
                    getattr(config, "SNS_AUTH_FAILURE_THRESHOLD", 5) or 5
                ),
            ),
        )

    def status_notes(self) -> dict[str, str]:
        return {
            "cloudwatch": "enabled" if self.metrics.enabled else "disabled",
            "sns": "enabled" if self.alerts.enabled else "disabled",
            "monitoring": "module-09",
        }

    def on_sync_success(
        self,
        *,
        operation: str,
        path: str,
        file_id: Optional[int] = None,
        conflict: bool = False,
        conflict_path: Optional[str] = None,
        idempotent: bool = False,
    ) -> None:
        try:
            event = "conflict.detected" if conflict else "sync.success"
            self.structured.emit(
                "INFO",
                event,
                operation=operation,
                path=path,
                file_id=file_id,
                success=True,
                conflict=conflict,
                conflict_path=conflict_path,
                idempotent=idempotent,
            )
            self.metrics.increment(
                METRIC_SYNC_OPERATIONS, dimensions={"Operation": operation}
            )
            self.metrics.increment(METRIC_SYNC_SUCCESS)
            if conflict:
                self.metrics.increment(METRIC_CONFLICT_EVENTS)
                self.structured.emit(
                    "WARNING",
                    "conflict.logged",
                    operation="CONFLICT",
                    path=path,
                    file_id=file_id,
                    success=True,
                    conflict_path=conflict_path,
                )
            self.alerts.record_sync_success()
        except Exception:
            return

    def on_sync_failure(
        self,
        *,
        operation: str,
        path: str,
        error: str,
        critical: bool = False,
    ) -> None:
        try:
            self.structured.emit(
                "ERROR",
                "sync.failure",
                operation=operation,
                path=path,
                success=False,
                error=error,
            )
            self.metrics.increment(
                METRIC_SYNC_OPERATIONS, dimensions={"Operation": operation or "UNKNOWN"}
            )
            self.metrics.increment(METRIC_SYNC_FAILURE)
            self.alerts.record_sync_failure(
                operation=operation, path=path, error=error
            )
            if critical:
                self.on_application_error(error=error, event="sync.unexpected_error")
        except Exception:
            return

    def on_application_error(self, *, error: str, event: str = "application.error") -> None:
        try:
            self.structured.emit(
                "ERROR",
                event,
                success=False,
                error=error,
            )
            self.metrics.increment(METRIC_APPLICATION_ERRORS)
            self.alerts.record_critical_error(error=error, event=event)
        except Exception:
            return

    def on_auth_failure(self) -> None:
        try:
            self.structured.emit(
                "WARNING",
                "auth.failure",
                success=False,
                operation="AUTH",
            )
            self.metrics.increment(METRIC_AUTH_FAILURES)
            self.alerts.record_auth_failure()
        except Exception:
            return

    def on_file_event(self, *, operation: str, path: str, file_id: Optional[int] = None) -> None:
        try:
            event_map = {
                "CREATED": "file.created",
                "MODIFIED": "file.modified",
                "DELETED": "file.deleted",
                "MOVED": "file.moved",
            }
            self.structured.emit(
                "INFO",
                event_map.get(operation, "file.event"),
                operation=operation,
                path=path,
                file_id=file_id,
                success=True,
            )
        except Exception:
            return
