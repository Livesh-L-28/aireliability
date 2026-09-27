"""Optional OpenTelemetry integration for exporting TelemetryTraces to OTel SDK.

This module is lazy-loaded and requires the optional `opentelemetry` extra:
    pip install "aireliability[opentelemetry]"

If OpenTelemetry is not installed, importing this module raises a helpful
ImportError with installation instructions.
"""

from typing import Any

from aireliability.telemetry.models import (
    TelemetryStatus,
    TelemetryTrace,
)


def _check_opentelemetry_installed() -> tuple[Any, Any]:
    """Check if opentelemetry API is installed, raising ImportError if missing."""
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.trace import StatusCode

        return otel_trace, StatusCode
    except ImportError as exc:
        raise ImportError(
            "OpenTelemetry integration requires the 'opentelemetry' extra.\n"
            "Install with: pip install 'aireliability[opentelemetry]'"
        ) from exc


class OpenTelemetryExporter:
    """Translates internal TelemetryTraces into OpenTelemetry spans."""

    def __init__(self, tracer: Any | None = None) -> None:
        self.otel_trace, self.status_code_cls = _check_opentelemetry_installed()
        self.tracer = tracer or self.otel_trace.get_tracer("aireliability")

    def export_trace(self, telemetry_trace: TelemetryTrace) -> list[Any]:
        """Export internal TelemetryTrace to OpenTelemetry spans."""
        created_spans: list[Any] = []

        # Find root spans
        root_spans = telemetry_trace.child_spans(None)
        for root in root_spans:
            otel_span = self._create_otel_span(root, parent_context=None)
            created_spans.append(otel_span)
            self._export_children(telemetry_trace, root.span_id, parent_span=otel_span)

        return created_spans

    def _export_children(
        self,
        telemetry_trace: TelemetryTrace,
        parent_id: str,
        parent_span: Any,
    ) -> None:
        children = telemetry_trace.child_spans(parent_id)
        for child in children:
            child_otel = self._create_otel_span(child, parent_span=parent_span)
            self._export_children(
                telemetry_trace, child.span_id, parent_span=child_otel
            )

    def _create_otel_span(
        self,
        span_model: Any,
        parent_context: Any = None,
        parent_span: Any = None,
    ) -> Any:
        span_name = span_model.name
        otel_span = self.tracer.start_span(
            span_name,
            start_time=int(span_model.started_at.timestamp() * 1e9),
        )

        # Set attributes
        for k, v in span_model.attributes.items():
            if isinstance(v, (str, bool, int, float)):
                otel_span.set_attribute(k, v)
            elif v is not None:
                otel_span.set_attribute(k, str(v))

        # Add events
        for ev in span_model.events:
            otel_span.add_event(
                ev.name,
                attributes={
                    k: str(v) if not isinstance(v, (str, bool, int, float)) else v
                    for k, v in ev.attributes.items()
                },
                timestamp=int(ev.timestamp.timestamp() * 1e9),
            )

        # Set status
        if span_model.status == TelemetryStatus.OK:
            otel_span.set_status(self.status_code_cls.OK)
        elif span_model.status == TelemetryStatus.ERROR:
            otel_span.set_status(
                self.status_code_cls.ERROR, description=span_model.status_message
            )

        # End span
        end_ns = (
            int(span_model.completed_at.timestamp() * 1e9)
            if span_model.completed_at
            else None
        )
        otel_span.end(end_time=end_ns)
        return otel_span
