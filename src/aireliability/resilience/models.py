"""Fault tolerance and resilience models for AI Reliability Engine (Phase 26).

Defines failure categories, structured failure records, circuit breaker states,
worker health statuses, backoff options, and bulkhead configurations.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.core.models import FailureSeverity


def _generate_resilience_id(prefix: str = "") -> str:
    """Generate a unique hex identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class ResilienceFailureCategory(StrEnum):
    """Broad categories for operational, infrastructure, and execution failures."""

    WORKER_FAILURE = "worker_failure"
    WORKER_TIMEOUT = "worker_timeout"
    JOB_TIMEOUT = "job_timeout"
    PROVIDER_FAILURE = "provider_failure"
    NETWORK_FAILURE = "network_failure"
    RATE_LIMIT_FAILURE = "rate_limit_failure"
    AUTHENTICATION_FAILURE = "authentication_failure"
    PERSISTENCE_FAILURE = "persistence_failure"
    SCHEDULER_FAILURE = "scheduler_failure"
    CANCELLATION = "cancellation"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    UNKNOWN_FAILURE = "unknown_failure"


class CircuitState(StrEnum):
    """Lifecycle states for circuit breakers."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class WorkerHealthStatus(StrEnum):
    """Health classification for distributed reliability workers."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    QUARANTINED = "quarantined"
    RECOVERING = "recovering"


class DetailedFailureRecord(BaseModel):
    """Structured and sanitized record of an operational or execution failure."""

    model_config = ConfigDict(frozen=True)

    failure_id: str = Field(default_factory=lambda: _generate_resilience_id("fail"))
    execution_id: str | None = None
    job_id: str | None = None
    worker_id: str | None = None
    provider_id: str | None = None
    failure_type: ResilienceFailureCategory = ResilienceFailureCategory.UNKNOWN_FAILURE
    severity: FailureSeverity = FailureSeverity.HIGH
    retryable: bool = True
    timestamp: datetime = Field(default_factory=_utc_now)
    attempt: int = 1
    error: str | None = None
    error_type: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthCheckResult(BaseModel):
    """Structured health check report for a system or component."""

    model_config = ConfigDict(frozen=True)

    component: str
    status: str  # "healthy", "degraded", "unhealthy"
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"
