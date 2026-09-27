"""Span representation and lifecycle management."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from aireliability.observability.context import (
    ObservabilityContext,
    get_current_context,
    reset_current_context,
    set_current_context,
)
from aireliability.observability.models import SpanKind, SpanRecord
from aireliability.observability.sanitization import TelemetrySanitizer


class Span:
    """Active span for tracing execution blocks."""

    def __init__(
        self,
        name: str,
        trace_id: str,
        parent_span_id: str | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
        sanitizer: TelemetrySanitizer | None = None,
        on_finish: Any | None = None,
    ) -> None:
        self.span_id: str = str(uuid4())
        self.name: str = name
        self.trace_id: str = trace_id
        self.parent_span_id: str | None = parent_span_id
        self.kind: SpanKind = kind
        self.start_time: datetime = datetime.now(UTC)
        self.end_time: datetime | None = None
        self.duration_ms: float | None = None
        self.status: str = "ok"
        self._sanitizer = sanitizer or TelemetrySanitizer()
        self.attributes: dict[str, Any] = self._sanitizer.sanitize(attributes or {})
        self.events: list[dict[str, Any]] = []
        self._on_finish = on_finish
        self._token: Any | None = None

    def set_attribute(self, key: str, value: Any) -> Span:
        """Add or update a span attribute."""
        self.attributes[key] = self._sanitizer.sanitize(value)
        return self

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> Span:
        """Attach an event log to this span."""
        self.events.append(
            {
                "name": name,
                "timestamp": datetime.now(UTC).isoformat(),
                "attributes": self._sanitizer.sanitize(attributes or {}),
            }
        )
        return self

    def record_exception(self, exc: BaseException) -> Span:
        """Record an exception into the span."""
        self.status = "error"
        self.add_event(
            "exception",
            {
                "exception.type": type(exc).__name__,
                "exception.message": str(exc),
            },
        )
        self.set_attribute("error", True)
        self.set_attribute("error.message", str(exc))
        return self

    def finish(self, status: str | None = None) -> SpanRecord:
        """Finish span and measure duration."""
        if self.end_time is None:
            self.end_time = datetime.now(UTC)
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000.0

        if status:
            self.status = status

        record = self.to_record()
        if self._token is not None:
            reset_current_context(self._token)
            self._token = None

        if self._on_finish:
            self._on_finish(record)

        return record

    def to_record(self) -> SpanRecord:
        """Convert to immutable SpanRecord."""
        return SpanRecord(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            name=self.name,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=self.duration_ms,
            status=self.status,
            kind=self.kind,
            attributes=self.attributes,
            events=self.events,
        )

    def __enter__(self) -> Span:
        ctx = get_current_context()
        new_ctx = ObservabilityContext(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            execution_id=ctx.execution_id,
            job_id=ctx.job_id,
            tenant_id=ctx.tenant_id,
            project_id=ctx.project_id,
            namespace=ctx.namespace,
            worker_id=ctx.worker_id,
            request_id=ctx.request_id,
            baggage=dict(ctx.baggage),
        )
        self._token = set_current_context(new_ctx)
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        if exc_val is not None:
            self.record_exception(exc_val)
        self.finish()

    async def __aenter__(self) -> Span:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)
