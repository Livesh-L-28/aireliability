"""Structured event recording and subscription."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from aireliability.observability.context import get_current_context
from aireliability.observability.models import TelemetryEvent
from aireliability.observability.sanitization import TelemetrySanitizer


class EventRecorder:
    """In-memory event recorder and dispatcher."""

    def __init__(
        self,
        sanitizer: TelemetrySanitizer | None = None,
        max_events: int = 10000,
    ) -> None:
        self.sanitizer = sanitizer or TelemetrySanitizer()
        self.max_events = max_events
        self._events: list[TelemetryEvent] = []
        self._subscribers: list[Callable[[TelemetryEvent], None]] = []

    def subscribe(self, subscriber: Callable[[TelemetryEvent], None]) -> None:
        """Register a callback for all new events."""
        self._subscribers.append(subscriber)

    def record_event(
        self,
        event_type: str,
        severity: str = "INFO",
        source: str = "system",
        duration_ms: float | None = None,
        status: str = "ok",
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
        execution_id: str | None = None,
        job_id: str | None = None,
        worker_id: str | None = None,
        provider_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        """Record a structured event, automatically attaching current context."""
        ctx = get_current_context()

        # Sanitize attributes
        sanitized_attrs = self.sanitizer.sanitize(attributes or {})

        event = TelemetryEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            severity=severity,
            source=source,
            tenant_id=tenant_id or ctx.tenant_id,
            project_id=project_id or ctx.project_id,
            namespace=namespace or ctx.namespace,
            execution_id=execution_id or ctx.execution_id,
            job_id=job_id or ctx.job_id,
            worker_id=worker_id or ctx.worker_id,
            provider_id=provider_id,
            trace_id=trace_id or ctx.trace_id,
            span_id=span_id or ctx.span_id,
            parent_span_id=parent_span_id or ctx.parent_span_id,
            duration_ms=duration_ms,
            status=status,
            attributes=sanitized_attrs,
        )

        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events.pop(0)

        import contextlib

        for subscriber in self._subscribers:
            with contextlib.suppress(Exception):
                subscriber(event)

        return event

    def get_events(
        self,
        tenant_id: str | None = None,
        event_type: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[TelemetryEvent]:
        """Query stored events with optional tenant and event filters."""
        results = []
        for ev in reversed(self._events):
            if tenant_id and ev.tenant_id != tenant_id:
                continue
            if event_type and not ev.event_type.startswith(event_type):
                continue
            if trace_id and ev.trace_id != trace_id:
                continue
            results.append(ev)
            if len(results) >= limit:
                break
        return list(reversed(results))

    def clear(self) -> None:
        """Clear all stored events."""
        self._events.clear()
