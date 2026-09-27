"""Telemetry data models for AI Reliability Engine.

Provides framework-neutral, immutable schemas for traces, spans, events,
and execution status. Designed for deterministic testability and vendor-agnostic
exporting (JSON, OpenTelemetry, Prometheus).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _generate_telemetry_id(prefix: str = "") -> str:
    """Generate a unique hex identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class TelemetryStatus(StrEnum):
    """Standardized execution and span outcome status."""

    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class SpanKind(StrEnum):
    """Semantic category of an execution span."""

    INTERNAL = "internal"
    AGENT = "agent"
    MODEL = "model"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    EVALUATION = "evaluation"
    ANALYSIS = "analysis"
    REGRESSION = "regression"


class TelemetryEvent(BaseModel):
    """A point-in-time structured event within a telemetry span."""

    model_config = ConfigDict(frozen=True)

    name: str
    timestamp: datetime = Field(default_factory=_utc_now)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TelemetrySpan(BaseModel):
    """A timed operation within a telemetry trace representing a unit of work."""

    model_config = ConfigDict(frozen=True)

    span_id: str = Field(default_factory=lambda: _generate_telemetry_id("span"))
    trace_id: str
    parent_span_id: str | None = None
    name: str
    kind: SpanKind = SpanKind.INTERNAL
    status: TelemetryStatus = TelemetryStatus.UNSET
    status_message: str | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    duration_ms: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[TelemetryEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_timestamps_and_duration(self) -> "TelemetrySpan":
        if self.completed_at is not None:
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot be earlier than started_at")
            if self.duration_ms is None:
                calc_ms = (self.completed_at - self.started_at).total_seconds() * 1000.0
                object.__setattr__(self, "duration_ms", max(0.0, calc_ms))
        return self


class TelemetryTrace(BaseModel):
    """Root telemetry trace aggregating an entire execution and its hierarchy
    of spans.
    """

    model_config = ConfigDict(frozen=True)

    trace_id: str = Field(default_factory=lambda: _generate_telemetry_id("trace"))
    execution_id: str | None = None
    test_id: str | None = None
    name: str = "reliability_execution"
    status: TelemetryStatus = TelemetryStatus.UNSET
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    duration_ms: float | None = None
    spans: list[TelemetrySpan] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_trace_duration(self) -> "TelemetryTrace":
        if self.completed_at is not None:
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot be earlier than started_at")
            if self.duration_ms is None:
                calc_ms = (self.completed_at - self.started_at).total_seconds() * 1000.0
                object.__setattr__(self, "duration_ms", max(0.0, calc_ms))
        return self

    def find_span(self, span_id: str) -> TelemetrySpan | None:
        """Find a span by its identifier."""
        for span in self.spans:
            if span.span_id == span_id:
                return span
        return None

    def child_spans(self, parent_span_id: str | None) -> list[TelemetrySpan]:
        """Return direct child spans of a parent span ID (or roots if None)."""
        return [s for s in self.spans if s.parent_span_id == parent_span_id]

    def to_export_dict(self) -> dict[str, Any]:
        """Convert trace to a deterministic, JSON-serializable dictionary."""
        return {
            "trace_id": self.trace_id,
            "execution_id": self.execution_id,
            "test_id": self.test_id,
            "name": self.name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "duration_ms": round(self.duration_ms, 3)
            if self.duration_ms is not None
            else None,
            "attributes": self.attributes,
            "spans": [
                {
                    "span_id": span.span_id,
                    "trace_id": span.trace_id,
                    "parent_span_id": span.parent_span_id,
                    "name": span.name,
                    "kind": span.kind.value,
                    "status": span.status.value,
                    "status_message": span.status_message,
                    "started_at": span.started_at.isoformat(),
                    "completed_at": span.completed_at.isoformat()
                    if span.completed_at
                    else None,
                    "duration_ms": round(span.duration_ms, 3)
                    if span.duration_ms is not None
                    else None,
                    "attributes": span.attributes,
                    "events": [
                        {
                            "name": ev.name,
                            "timestamp": ev.timestamp.isoformat(),
                            "attributes": ev.attributes,
                        }
                        for ev in span.events
                    ],
                }
                for span in self.spans
            ],
        }
