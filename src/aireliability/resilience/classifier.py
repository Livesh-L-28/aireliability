"""Structured failure classification and diagnostic mapping."""

from typing import Any

from aireliability.core.models import FailureSeverity
from aireliability.resilience.models import (
    DetailedFailureRecord,
    ResilienceFailureCategory,
)
from aireliability.telemetry.sanitizer import SanitizationPolicy


class FailureClassifier:
    """Classifies raw exceptions and errors into structured resilience categories."""

    def __init__(self, sanitizer: SanitizationPolicy | None = None) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()

    def classify_error(
        self,
        exc: BaseException | str | None,
        *,
        execution_id: str | None = None,
        job_id: str | None = None,
        worker_id: str | None = None,
        provider_id: str | None = None,
        attempt: int = 1,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DetailedFailureRecord:
        """Classify an exception into a DetailedFailureRecord with
        sanitized metadata.
        """
        if exc is None:
            err_msg = "Unknown error"
            err_type = "None"
        elif isinstance(exc, BaseException):
            err_msg = str(exc)
            err_type = type(exc).__name__
        else:
            err_msg = str(exc)
            err_type = "StringError"

        lowered = f"{err_type} {err_msg}".lower()

        # Categorize deterministically
        category = ResilienceFailureCategory.UNKNOWN_FAILURE
        severity = FailureSeverity.HIGH
        retryable = True

        if "cancel" in lowered:
            category = ResilienceFailureCategory.CANCELLATION
            severity = FailureSeverity.LOW
            retryable = False
        elif "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
            if "worker" in lowered:
                category = ResilienceFailureCategory.WORKER_TIMEOUT
            else:
                category = ResilienceFailureCategory.JOB_TIMEOUT
            severity = FailureSeverity.MEDIUM
            retryable = True
        elif any(
            k in lowered
            for k in ("rate limit", "ratelimit", "429", "too many requests")
        ):
            category = ResilienceFailureCategory.RATE_LIMIT_FAILURE
            severity = FailureSeverity.MEDIUM
            retryable = True
        elif any(
            k in lowered
            for k in (
                "auth",
                "unauthorized",
                "401",
                "403",
                "forbidden",
                "api key",
                "permission",
            )
        ):
            category = ResilienceFailureCategory.AUTHENTICATION_FAILURE
            severity = FailureSeverity.CRITICAL
            retryable = False
        elif any(
            k in lowered
            for k in (
                "connection",
                "network",
                "socket",
                "dns",
                "reset by peer",
                "refused",
            )
        ):
            category = ResilienceFailureCategory.NETWORK_FAILURE
            severity = FailureSeverity.MEDIUM
            retryable = True
        elif any(
            k in lowered
            for k in (
                "sqlite",
                "database",
                "disk",
                "storage",
                "operationalerror",
                "integrityerror",
            )
        ):
            category = ResilienceFailureCategory.PERSISTENCE_FAILURE
            severity = FailureSeverity.HIGH
            retryable = True
        elif any(
            k in lowered for k in ("oom", "memory", "exhausted", "capacity", "no space")
        ):
            category = ResilienceFailureCategory.RESOURCE_EXHAUSTION
            severity = FailureSeverity.HIGH
            retryable = False
        elif any(
            k in lowered
            for k in (
                "provider",
                "model error",
                "500",
                "502",
                "503",
                "service unavailable",
                "bad gateway",
            )
        ):
            category = ResilienceFailureCategory.PROVIDER_FAILURE
            severity = FailureSeverity.HIGH
            retryable = True
        elif "worker" in lowered:
            category = ResilienceFailureCategory.WORKER_FAILURE
            severity = FailureSeverity.HIGH
            retryable = True
        elif "scheduler" in lowered:
            category = ResilienceFailureCategory.SCHEDULER_FAILURE
            severity = FailureSeverity.HIGH
            retryable = False

        sanitized_meta = self.sanitizer.sanitize(metadata or {})

        return DetailedFailureRecord(
            execution_id=execution_id,
            job_id=job_id,
            worker_id=worker_id,
            provider_id=provider_id,
            failure_type=category,
            severity=severity,
            retryable=retryable,
            attempt=attempt,
            error=err_msg,
            error_type=err_type,
            trace_id=trace_id,
            metadata=sanitized_meta,
        )
