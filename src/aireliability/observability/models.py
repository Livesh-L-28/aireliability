"""Observability data models for Phase 29."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """Health status states."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class SpanKind(StrEnum):
    """Distributed tracing span kinds."""

    CLIENT = "CLIENT"
    SERVER = "SERVER"
    INTERNAL = "INTERNAL"
    WORKER = "WORKER"
    PROVIDER = "PROVIDER"
    SCHEDULER = "SCHEDULER"
    PERSISTENCE = "PERSISTENCE"


class IncidentStatus(StrEnum):
    """Incident lifecycle status."""

    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    MITIGATING = "MITIGATING"
    RESOLVED = "RESOLVED"


class AnomalySeverity(StrEnum):
    """Anomaly detection severity."""

    NORMAL = "NORMAL"
    WARNING = "WARNING"
    ANOMALY = "ANOMALY"


class TelemetryEvent(BaseModel):
    """Structured telemetry event."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    severity: str = "INFO"
    source: str = "system"
    tenant_id: str = "default"
    project_id: str = "default"
    namespace: str = "default"
    execution_id: str | None = None
    job_id: str | None = None
    worker_id: str | None = None
    provider_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    duration_ms: float | None = None
    status: str = "ok"
    attributes: dict[str, Any] = Field(default_factory=dict)


class MetricSample(BaseModel):
    """Single metric sample point."""

    metric_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    value: float
    tenant_id: str = "default"
    project_id: str = "default"
    namespace: str = "default"
    worker_id: str | None = None
    provider_id: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class SpanRecord(BaseModel):
    """Record of an individual span execution."""

    span_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str
    parent_span_id: str | None = None
    name: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    duration_ms: float | None = None
    status: str = "ok"
    kind: SpanKind = SpanKind.INTERNAL
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


class TraceRecord(BaseModel):
    """Distributed trace aggregate record."""

    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    root_span_id: str | None = None
    tenant_id: str = "default"
    project_id: str = "default"
    namespace: str = "default"
    execution_id: str | None = None
    job_id: str | None = None
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    status: str = "ok"
    attributes: dict[str, Any] = Field(default_factory=dict)
    spans: list[SpanRecord] = Field(default_factory=list)


class HealthSnapshot(BaseModel):
    """Operational health snapshot across all subsystems."""

    overall_status: HealthStatus = HealthStatus.HEALTHY
    scheduler_status: HealthStatus = HealthStatus.HEALTHY
    storage_status: HealthStatus = HealthStatus.HEALTHY
    worker_status: HealthStatus = HealthStatus.HEALTHY
    resilience_status: HealthStatus = HealthStatus.HEALTHY
    security_status: HealthStatus = HealthStatus.HEALTHY
    tenancy_status: HealthStatus = HealthStatus.HEALTHY
    queue_status: HealthStatus = HealthStatus.HEALTHY
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)
