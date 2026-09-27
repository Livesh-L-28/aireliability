"""Unified observability manager coordinating all observability subsystems."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aireliability.observability.aggregation import TelemetryAggregator
from aireliability.observability.anomaly import StatisticalAnomalyDetector
from aireliability.observability.events import EventRecorder
from aireliability.observability.exporter import (
    CsvMetricExporter,
    JsonExporter,
    JsonlExporter,
    PrometheusExporter,
)
from aireliability.observability.health import OperationalHealthManager
from aireliability.observability.incidents import IncidentManager
from aireliability.observability.metrics import MetricsEngine
from aireliability.observability.models import HealthSnapshot, HealthStatus
from aireliability.observability.retention import RetentionPolicyManager
from aireliability.observability.sanitization import TelemetrySanitizer
from aireliability.observability.slo import SLOEvaluation, SLOManager
from aireliability.observability.traces import Tracer


class OperationalSnapshot(BaseModel):
    """Unified operational diagnostic snapshot."""

    system_status: HealthStatus
    active_jobs: int = 0
    queue_depth: float = 0.0
    throughput: float = 0.0
    success_rate: float = 1.0
    failure_rate: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    worker_utilization: float = 0.0
    provider_health: str = "HEALTHY"
    tenant_utilization: dict[str, Any] = Field(default_factory=dict)
    open_circuits: int = 0
    quarantined_workers: int = 0
    active_incidents: int = 0
    slo_status: list[SLOEvaluation] = Field(default_factory=list)
    error_budget: dict[str, float] = Field(default_factory=dict)
    subsystem_health: HealthSnapshot = Field(default_factory=lambda: HealthSnapshot())


class ObservabilityManager:
    """Central entry point for all observability services."""

    def __init__(
        self,
        sanitizer: TelemetrySanitizer | None = None,
        retention: RetentionPolicyManager | None = None,
        health_checker: Any | None = None,
        resilience_manager: Any | None = None,
        resource_governor: Any | None = None,
        security_gateway: Any | None = None,
        control_plane: Any | None = None,
        worker_manager: Any | None = None,
        storage_backend: Any | None = None,
    ) -> None:
        self.sanitizer = sanitizer or TelemetrySanitizer()
        self.retention = retention or RetentionPolicyManager()
        self.events = EventRecorder(sanitizer=self.sanitizer)
        self.tracer = Tracer(sanitizer=self.sanitizer)
        self.metrics = MetricsEngine()
        self.aggregator = TelemetryAggregator(self.metrics, self.events, self.tracer)
        self.health = OperationalHealthManager(
            health_checker=health_checker,
            resilience_manager=resilience_manager,
            resource_governor=resource_governor,
            security_gateway=security_gateway,
            control_plane=control_plane,
            worker_manager=worker_manager,
            storage_backend=storage_backend,
        )
        self.slo = SLOManager(self.aggregator)
        self.anomaly = StatisticalAnomalyDetector()
        self.incidents = IncidentManager()

        # Exporters
        self.json_exporter = JsonExporter()
        self.jsonl_exporter = JsonlExporter()
        self.csv_exporter = CsvMetricExporter()
        self.prometheus_exporter = PrometheusExporter(self.metrics)

        # Wire automated anomaly & incident detection subscriber
        self._wire_events_pipeline()

    def _wire_events_pipeline(self) -> None:
        """Process events for metrics updates and incident detection."""

        def _on_event(event: Any) -> None:
            # Metrics counters
            if event.event_type == "job.submitted":
                self.metrics.counter("aireliability_jobs_submitted_total").increment(
                    tenant_id=event.tenant_id
                )
            elif event.event_type == "job.completed":
                self.metrics.counter("aireliability_jobs_completed_total").increment(
                    tenant_id=event.tenant_id
                )
            elif event.event_type == "job.failed":
                self.metrics.counter("aireliability_jobs_failed_total").increment(
                    tenant_id=event.tenant_id
                )
            elif event.event_type.startswith("security.denied"):
                self.metrics.counter(
                    "aireliability_authorization_denials_total"
                ).increment(tenant_id=event.tenant_id)
            elif event.event_type == "security.authentication" and event.status != "ok":
                self.metrics.counter("aireliability_auth_failures_total").increment(
                    tenant_id=event.tenant_id
                )
            elif event.event_type == "tenant.rate_limited":
                self.metrics.counter(
                    "aireliability_tenant_rate_limits_total"
                ).increment(tenant_id=event.tenant_id)
            elif event.event_type == "tenant.quota_exceeded":
                self.metrics.counter(
                    "aireliability_tenant_quota_exceeded_total"
                ).increment(tenant_id=event.tenant_id)
            elif event.event_type == "resilience.retry":
                self.metrics.counter("aireliability_retries_total").increment()
            elif event.event_type == "resilience.load_shed":
                self.metrics.counter("aireliability_jobs_shed_total").increment()
            elif event.event_type == "job.reassigned":
                self.metrics.counter("aireliability_jobs_reassigned_total").increment()
            elif event.event_type == "provider.request_failed":
                self.metrics.counter("aireliability_provider_errors_total").increment()

            # Record latency into histogram if available
            if event.duration_ms is not None:
                self.metrics.histogram("aireliability_job_latency_seconds").observe(
                    event.duration_ms / 1000.0,
                    tenant_id=event.tenant_id,
                )

        self.events.subscribe(_on_event)

    def snapshot(self, tenant_id: str | None = None) -> OperationalSnapshot:
        """Produce unified operational diagnostic snapshot."""
        health_snap = self.health.evaluate_health()
        agg = self.aggregator.aggregate(window_seconds=300.0, tenant_id=tenant_id)
        slo_evals = self.slo.evaluate_all(tenant_id=tenant_id)

        error_budget: dict[str, float] = {}
        for s in slo_evals:
            error_budget[s.name] = s.remaining_error_budget

        active_inc = len(
            self.incidents.list_incidents(tenant_id=tenant_id, status=None)
        )

        lat = agg.get("latency", {})

        return OperationalSnapshot(
            system_status=health_snap.overall_status,
            active_jobs=int(agg.get("job_submissions", 0))
            - int(agg.get("job_completions", 0)),
            queue_depth=float(agg.get("queue_depth", 0.0)),
            throughput=float(agg.get("throughput_eps", 0.0)),
            success_rate=float(agg.get("success_rate", 1.0)),
            failure_rate=float(agg.get("error_ratio", 0.0)),
            p50_latency=float(lat.get("p50", 0.0)),
            p95_latency=float(lat.get("p95", 0.0)),
            p99_latency=float(lat.get("p99", 0.0)),
            worker_utilization=float(agg.get("worker_utilization", 0.0)),
            provider_health="HEALTHY"
            if agg.get("error_ratio", 0.0) < 0.2
            else "DEGRADED",
            tenant_utilization={
                "submissions": agg.get("job_submissions", 0),
                "completions": agg.get("job_completions", 0),
            },
            open_circuits=int(agg.get("circuit_breakers_open", 0)),
            quarantined_workers=int(
                health_snap.details.get("quarantined_workers_count", 0)
            ),
            active_incidents=active_inc,
            slo_status=slo_evals,
            error_budget=error_budget,
            subsystem_health=health_snap,
        )

    def prune_retention(self) -> dict[str, int]:
        """Prune records based on retention policies."""
        return self.retention.prune_all(
            events=self.events,
            tracer=self.tracer,
            metrics=self.metrics,
            incidents=self.incidents,
        )
