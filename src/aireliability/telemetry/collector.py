"""Internal telemetry collectors for capturing and exporting trace spans.

Provides standard collectors:
- NoOpTelemetryCollector: Zero overhead when telemetry is disabled.
- InMemoryTelemetryCollector: Retains traces in memory for assertions, tests,
  and programmatic inspection.
- JsonTelemetryCollector: Streams or flushes structured JSON traces to disk or
  file-like streams.
"""

import json
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable

from aireliability.telemetry.models import TelemetryTrace
from aireliability.telemetry.sampler import AlwaysOnSampler, TelemetrySampler
from aireliability.telemetry.sanitizer import SanitizationPolicy


@runtime_checkable
class TelemetryCollector(Protocol):
    """Protocol for recording and flushing telemetry traces."""

    def record(self, trace: TelemetryTrace) -> None:
        """Record a completed telemetry trace."""
        ...

    def flush(self) -> None:
        """Flush any buffered telemetry traces."""
        ...

    def clear(self) -> None:
        """Clear any buffered traces."""
        ...


class NoOpTelemetryCollector:
    """Zero-overhead collector that discards all telemetry data."""

    def record(self, trace: TelemetryTrace) -> None:
        pass

    def flush(self) -> None:
        pass

    def clear(self) -> None:
        pass


class InMemoryTelemetryCollector:
    """Collector that stores captured telemetry traces in memory."""

    def __init__(
        self,
        *,
        sampler: TelemetrySampler | None = None,
        sanitizer: SanitizationPolicy | None = None,
    ) -> None:
        self.sampler = sampler or AlwaysOnSampler()
        self.sanitizer = sanitizer or SanitizationPolicy()
        self._traces: list[TelemetryTrace] = []

    def record(self, trace: TelemetryTrace) -> None:
        if not self.sampler.should_sample(trace.trace_id):
            return
        # Apply sanitization if configured
        if self.sanitizer is not None:
            sanitized_attrs = self.sanitizer.sanitize(trace.attributes)
            sanitized_spans = []
            for span in trace.spans:
                s_attrs = self.sanitizer.sanitize(span.attributes)
                s_events = [
                    ev.model_copy(
                        update={"attributes": self.sanitizer.sanitize(ev.attributes)}
                    )
                    for ev in span.events
                ]
                sanitized_spans.append(
                    span.model_copy(update={"attributes": s_attrs, "events": s_events})
                )
            trace = trace.model_copy(
                update={"attributes": sanitized_attrs, "spans": sanitized_spans}
            )
        self._traces.append(trace)

    def flush(self) -> None:
        pass

    def clear(self) -> None:
        self._traces.clear()

    @property
    def traces(self) -> list[TelemetryTrace]:
        """Return a copy of the recorded traces."""
        return list(self._traces)

    def get_last_trace(self) -> TelemetryTrace | None:
        """Return the most recently recorded trace, or None if empty."""
        return self._traces[-1] if self._traces else None


class JsonTelemetryCollector:
    """Collector that records sanitized telemetry traces as JSON."""

    def __init__(
        self,
        target: str | Path | TextIO,
        *,
        sampler: TelemetrySampler | None = None,
        sanitizer: SanitizationPolicy | None = None,
        indent: int = 2,
    ) -> None:
        self.target = target
        self.sampler = sampler or AlwaysOnSampler()
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.indent = indent
        self._traces: list[TelemetryTrace] = []

    def record(self, trace: TelemetryTrace) -> None:
        if not self.sampler.should_sample(trace.trace_id):
            return
        if self.sanitizer is not None:
            sanitized_attrs = self.sanitizer.sanitize(trace.attributes)
            sanitized_spans = []
            for span in trace.spans:
                s_attrs = self.sanitizer.sanitize(span.attributes)
                s_events = [
                    ev.model_copy(
                        update={"attributes": self.sanitizer.sanitize(ev.attributes)}
                    )
                    for ev in span.events
                ]
                sanitized_spans.append(
                    span.model_copy(update={"attributes": s_attrs, "events": s_events})
                )
            trace = trace.model_copy(
                update={"attributes": sanitized_attrs, "spans": sanitized_spans}
            )
        self._traces.append(trace)

    def flush(self) -> None:
        export_data = [t.to_export_dict() for t in self._traces]
        payload = json.dumps(export_data, indent=self.indent)
        if isinstance(self.target, (str, Path)):
            path = Path(self.target)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        elif hasattr(self.target, "write"):
            self.target.write(payload)

    def clear(self) -> None:
        self._traces.clear()

    @property
    def traces(self) -> list[TelemetryTrace]:
        return list(self._traces)
