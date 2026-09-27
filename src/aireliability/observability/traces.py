"""Distributed tracing manager and Tracer implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from aireliability.observability.context import (
    ObservabilityContext,
    get_current_context,
    set_current_context,
)
from aireliability.observability.models import SpanKind, SpanRecord, TraceRecord
from aireliability.observability.sanitization import TelemetrySanitizer
from aireliability.observability.spans import Span


class Trace:
    """In-progress trace aggregating its spans."""

    def __init__(
        self,
        trace_id: str,
        tenant_id: str = "default",
        project_id: str = "default",
        namespace: str = "default",
        execution_id: str | None = None,
        job_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.namespace = namespace
        self.execution_id = execution_id
        self.job_id = job_id
        self.start_time: datetime = datetime.now(UTC)
        self.end_time: datetime | None = None
        self.status: str = "ok"
        self.root_span_id: str | None = None
        self.attributes: dict[str, Any] = attributes or {}
        self.spans: list[SpanRecord] = []

    def add_span_record(self, span: SpanRecord) -> None:
        """Add finished span record to trace."""
        self.spans.append(span)
        if self.root_span_id is None and span.parent_span_id is None:
            self.root_span_id = span.span_id
        if span.status == "error":
            self.status = "error"

    def finish(self) -> TraceRecord:
        """Mark trace finished and produce TraceRecord."""
        if self.end_time is None:
            self.end_time = datetime.now(UTC)
        return TraceRecord(
            trace_id=self.trace_id,
            root_span_id=self.root_span_id,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            namespace=self.namespace,
            execution_id=self.execution_id,
            job_id=self.job_id,
            start_time=self.start_time,
            end_time=self.end_time,
            status=self.status,
            attributes=self.attributes,
            spans=list(self.spans),
        )


class Tracer:
    """Provider-neutral distributed tracer."""

    def __init__(
        self,
        sanitizer: TelemetrySanitizer | None = None,
        max_traces: int = 5000,
    ) -> None:
        self.sanitizer = sanitizer or TelemetrySanitizer()
        self.max_traces = max_traces
        self._traces: dict[str, Trace] = {}
        self._finished_records: dict[str, TraceRecord] = {}

    def start_trace(
        self,
        name: str = "root",
        trace_id: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
        execution_id: str | None = None,
        job_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new root trace and return its root span."""
        tid = trace_id or str(uuid4())
        ctx = get_current_context()

        t_id = tenant_id or ctx.tenant_id
        p_id = project_id or ctx.project_id
        ns = namespace or ctx.namespace
        e_id = execution_id or ctx.execution_id
        j_id = job_id or ctx.job_id

        trace = Trace(
            trace_id=tid,
            tenant_id=t_id,
            project_id=p_id,
            namespace=ns,
            execution_id=e_id,
            job_id=j_id,
            attributes=self.sanitizer.sanitize(attributes or {}),
        )
        self._traces[tid] = trace

        # Set context
        new_ctx = ObservabilityContext(
            trace_id=tid,
            execution_id=e_id,
            job_id=j_id,
            tenant_id=t_id,
            project_id=p_id,
            namespace=ns,
            worker_id=ctx.worker_id,
            request_id=ctx.request_id,
        )
        set_current_context(new_ctx)

        root_span = self.start_span(
            name=name,
            trace_id=tid,
            parent_span_id=None,
            kind=SpanKind.SERVER,
            attributes=attributes,
        )
        trace.root_span_id = root_span.span_id
        return root_span

    def start_span(
        self,
        name: str,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span within current or specified trace."""
        ctx = get_current_context()
        tid = trace_id or ctx.trace_id
        pid = parent_span_id if parent_span_id is not None else ctx.span_id

        if tid not in self._traces:
            self._traces[tid] = Trace(
                trace_id=tid,
                tenant_id=ctx.tenant_id,
                project_id=ctx.project_id,
                namespace=ctx.namespace,
                execution_id=ctx.execution_id,
                job_id=ctx.job_id,
            )

        def _on_span_finish(record: SpanRecord) -> None:
            if tid in self._traces:
                self._traces[tid].add_span_record(record)

        return Span(
            name=name,
            trace_id=tid,
            parent_span_id=pid,
            kind=kind,
            attributes=attributes,
            sanitizer=self.sanitizer,
            on_finish=_on_span_finish,
        )

    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Convenience method for creating a span in current context."""
        return self.start_span(name=name, kind=kind, attributes=attributes)

    def finish_trace(self, trace_id: str) -> TraceRecord | None:
        """Finish a trace, archiving its record."""
        trace = self._traces.pop(trace_id, None)
        if not trace:
            return self._finished_records.get(trace_id)

        record = trace.finish()
        self._finished_records[trace_id] = record

        # Prune if exceeded max
        if len(self._finished_records) > self.max_traces:
            oldest_key = next(iter(self._finished_records))
            self._finished_records.pop(oldest_key, None)

        return record

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        """Fetch trace record by id."""
        if trace_id in self._finished_records:
            return self._finished_records[trace_id]
        if trace_id in self._traces:
            return self._traces[trace_id].finish()
        return None

    def list_traces(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[TraceRecord]:
        """List traces with optional tenant filtering."""
        all_traces = list(self._finished_records.values())
        if tenant_id:
            all_traces = [t for t in all_traces if t.tenant_id == tenant_id]
        return all_traces[-limit:]

    def clear(self) -> None:
        """Clear active and finished traces."""
        self._traces.clear()
        self._finished_records.clear()
