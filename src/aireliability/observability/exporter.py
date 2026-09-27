"""Telemetry exporters: JSONL, JSON, CSV, and Prometheus text."""

from __future__ import annotations

import csv
import io
import json
from abc import ABC, abstractmethod

from aireliability.observability.metrics import MetricsEngine
from aireliability.observability.models import (
    MetricSample,
    TelemetryEvent,
    TraceRecord,
)


class TelemetryExporter(ABC):
    """Abstract base class for telemetry exporters."""

    @abstractmethod
    def export_events(self, events: list[TelemetryEvent]) -> str:
        """Export events to formatted string."""

    @abstractmethod
    def export_traces(self, traces: list[TraceRecord]) -> str:
        """Export traces to formatted string."""


class JsonlExporter(TelemetryExporter):
    """Exports events, traces, and metrics as JSON Lines."""

    def export_events(self, events: list[TelemetryEvent]) -> str:
        return "\n".join(ev.model_dump_json() for ev in events)

    def export_traces(self, traces: list[TraceRecord]) -> str:
        return "\n".join(tr.model_dump_json() for tr in traces)

    def export_metrics(self, samples: list[MetricSample]) -> str:
        return "\n".join(s.model_dump_json() for s in samples)


class JsonExporter(TelemetryExporter):
    """Exports events, traces, and metrics as standard JSON arrays."""

    def export_events(self, events: list[TelemetryEvent]) -> str:
        return json.dumps([ev.model_dump(mode="json") for ev in events], indent=2)

    def export_traces(self, traces: list[TraceRecord]) -> str:
        return json.dumps([tr.model_dump(mode="json") for tr in traces], indent=2)

    def export_metrics(self, samples: list[MetricSample]) -> str:
        return json.dumps([s.model_dump(mode="json") for s in samples], indent=2)


class CsvMetricExporter:
    """Exports metric samples as CSV."""

    def export(self, samples: list[MetricSample]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "metric_name",
                "timestamp",
                "value",
                "tenant_id",
                "project_id",
                "namespace",
                "worker_id",
                "provider_id",
                "labels",
            ]
        )
        for s in samples:
            writer.writerow(
                [
                    s.metric_name,
                    s.timestamp.isoformat(),
                    s.value,
                    s.tenant_id,
                    s.project_id,
                    s.namespace,
                    s.worker_id or "",
                    s.provider_id or "",
                    json.dumps(s.labels),
                ]
            )
        return output.getvalue()


class PrometheusExporter:
    """Exports metrics in Prometheus text exposition format."""

    def __init__(self, metrics: MetricsEngine) -> None:
        self.metrics = metrics

    def export(self) -> str:
        return self.metrics.render_prometheus()
