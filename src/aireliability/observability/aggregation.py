"""Telemetry aggregation engine for multi-window rates, latencies, and ratios."""

from __future__ import annotations

import time
from typing import Any

from aireliability.observability.events import EventRecorder
from aireliability.observability.metrics import MetricsEngine, calculate_percentiles
from aireliability.observability.traces import Tracer


class TelemetryAggregator:
    """Aggregates metrics, traces, and events across configurable time windows."""

    def __init__(
        self,
        metrics: MetricsEngine,
        events: EventRecorder,
        tracer: Tracer,
    ) -> None:
        self.metrics = metrics
        self.events = events
        self.tracer = tracer

    def aggregate(
        self,
        window_seconds: float = 300.0,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate telemetry statistics for a specific time window."""
        now = time.time()
        cutoff_dt = now - window_seconds

        # Filter events
        matching_events = [
            ev
            for ev in self.events._events
            if (ev.timestamp.timestamp() >= cutoff_dt)
            and (tenant_id is None or ev.tenant_id == tenant_id)
        ]

        total_events = len(matching_events)
        job_submissions = sum(
            1 for ev in matching_events if ev.event_type == "job.submitted"
        )
        job_completions = sum(
            1 for ev in matching_events if ev.event_type == "job.completed"
        )
        job_failures = sum(1 for ev in matching_events if ev.event_type == "job.failed")
        auth_failures = sum(
            1
            for ev in matching_events
            if ev.event_type.startswith("security.denied")
            or ev.event_type == "security.authentication"
            and ev.status != "ok"
        )

        completed_or_failed = job_completions + job_failures
        success_rate = (
            (job_completions / completed_or_failed) if completed_or_failed > 0 else 1.0
        )
        error_ratio = (
            (job_failures / completed_or_failed) if completed_or_failed > 0 else 0.0
        )
        throughput_eps = (
            (job_completions / window_seconds) if window_seconds > 0 else 0.0
        )

        # Durations from events and spans
        durations: list[float] = [
            ev.duration_ms / 1000.0
            for ev in matching_events
            if ev.duration_ms is not None
        ]

        # Add trace durations
        for tr in self.tracer._finished_records.values():
            if tenant_id and tr.tenant_id != tenant_id:
                continue
            if tr.start_time.timestamp() >= cutoff_dt:
                for sp in tr.spans:
                    if sp.duration_ms is not None:
                        durations.append(sp.duration_ms / 1000.0)

        latency_percentiles = calculate_percentiles(durations)

        queue_depth = self.metrics.gauge("aireliability_queue_depth").get()
        worker_util = self.metrics.gauge("aireliability_worker_utilization").get()
        open_circuits = self.metrics.gauge("aireliability_circuit_breakers_open").get()

        return {
            "window_seconds": window_seconds,
            "tenant_id": tenant_id or "all",
            "total_events": total_events,
            "job_submissions": job_submissions,
            "job_completions": job_completions,
            "job_failures": job_failures,
            "auth_failures": auth_failures,
            "success_rate": success_rate,
            "error_ratio": error_ratio,
            "throughput_eps": throughput_eps,
            "queue_depth": queue_depth,
            "worker_utilization": worker_util,
            "circuit_breakers_open": open_circuits,
            "latency": latency_percentiles,
        }
