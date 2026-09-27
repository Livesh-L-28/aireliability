"""Performance and latency benchmarks for Phase 29 — Observability & Tracing."""

import asyncio
import time

from aireliability.control_plane.controller import ControlPlane
from aireliability.core.models import TestCase
from aireliability.observability.aggregation import TelemetryAggregator
from aireliability.observability.anomaly import StatisticalAnomalyDetector
from aireliability.observability.context import (
    create_trace_context,
    get_current_context,
    observability_context,
)
from aireliability.observability.events import EventRecorder
from aireliability.observability.health import OperationalHealthManager
from aireliability.observability.incidents import IncidentManager
from aireliability.observability.manager import ObservabilityManager
from aireliability.observability.metrics import MetricsEngine
from aireliability.observability.slo import SLOManager
from aireliability.observability.traces import Tracer


def benchmark_context_creation(iterations: int = 10_000) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        create_trace_context(tenant_id="bench-t", execution_id="exec-1")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_context_propagation(iterations: int = 10_000) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        with observability_context(tenant_id="tenant_p"):
            get_current_context()
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_event_creation(iterations: int = 10_000) -> float:
    recorder = EventRecorder()
    start = time.perf_counter()
    for _ in range(iterations):
        recorder.record_event("job.submitted", tenant_id="tenant_ev")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_span_lifecycle(iterations: int = 5_000) -> float:
    tracer = Tracer()
    start = time.perf_counter()
    for _ in range(iterations):
        with tracer.span("bench.op"):
            pass
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_metric_increment(iterations: int = 20_000) -> float:
    metrics = MetricsEngine()
    counter = metrics.counter("bench_counter")
    start = time.perf_counter()
    for _ in range(iterations):
        counter.increment(tenant_id="bench_tenant")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_histogram_update(iterations: int = 10_000) -> float:
    metrics = MetricsEngine()
    hist = metrics.histogram("bench_hist")
    start = time.perf_counter()
    for _ in range(iterations):
        hist.observe(0.042, tenant_id="bench_tenant")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_telemetry_aggregation(iterations: int = 1_000) -> float:
    metrics = MetricsEngine()
    events = EventRecorder()
    tracer = Tracer()
    for _ in range(100):
        events.record_event("job.completed", tenant_id="t1", duration_ms=25.0)
    agg = TelemetryAggregator(metrics, events, tracer)

    start = time.perf_counter()
    for _ in range(iterations):
        agg.aggregate(window_seconds=60.0)
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_health_snapshot(iterations: int = 2_000) -> float:
    mgr = OperationalHealthManager()
    start = time.perf_counter()
    for _ in range(iterations):
        mgr.evaluate_health()
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_slo_evaluation(iterations: int = 1_000) -> float:
    metrics = MetricsEngine()
    events = EventRecorder()
    tracer = Tracer()
    for _ in range(50):
        events.record_event("job.completed", tenant_id="t1")
    agg = TelemetryAggregator(metrics, events, tracer)
    slo_mgr = SLOManager(agg)
    slo = slo_mgr.register_slo("success_slo", "success_rate", target=0.99)

    start = time.perf_counter()
    for _ in range(iterations):
        slo.evaluate(agg)
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_anomaly_detection(iterations: int = 5_000) -> float:
    det = StatisticalAnomalyDetector()
    for _ in range(20):
        det.record_observation("m1", 10.0)

    start = time.perf_counter()
    for _ in range(iterations):
        det.detect("m1", 10.5)
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_incident_detection(iterations: int = 5_000) -> float:
    mgr = IncidentManager()
    start = time.perf_counter()
    for _ in range(iterations):
        mgr.create_incident("High Error Rate", "Errors spiked", tenant_id="t1")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_full_observability_pipeline(iterations: int = 1_000) -> float:
    obs = ObservabilityManager()
    start = time.perf_counter()
    for _ in range(iterations):
        obs.events.record_event("job.submitted", tenant_id="t1")
        obs.metrics.counter("aireliability_jobs_submitted_total").increment(
            tenant_id="t1"
        )
        obs.snapshot(tenant_id="t1")
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000


def benchmark_control_plane_overhead(
    iterations: int = 500,
) -> tuple[float, float, float]:
    from aireliability.tenancy.models import RateLimitPolicy, ResourceQuota

    async def setup_cp(cp: ControlPlane):
        await cp.governance.register_tenant(
            "default",
            quota=ResourceQuota(max_queued_jobs=100_000, max_concurrent_jobs=100_000),
        )
        unlimited_policy = RateLimitPolicy(rate=100_000.0, burst_capacity=100_000.0)
        cp.governance.rate_limiter.default_policy = unlimited_policy
        cp.governance.rate_limiter.set_policy(
            "default:default:default", unlimited_policy
        )

    async def run_jobs(cp: ControlPlane):
        await setup_cp(cp)
        for i in range(iterations):
            tc = TestCase(id=f"tc-b-{i}", name=f"tc-b-{i}", input={"val": "x"})
            await cp.submit_job(tc)

    # Baseline with no observability integration
    cp_baseline = ControlPlane(observability_manager=None)
    cp_baseline.observability = None  # type: ignore

    t0 = time.perf_counter()
    asyncio.run(run_jobs(cp_baseline))
    baseline_time = (time.perf_counter() - t0) / iterations * 1_000_000

    # Enabled
    cp_enabled = ControlPlane()
    t1 = time.perf_counter()
    asyncio.run(run_jobs(cp_enabled))
    enabled_time = (time.perf_counter() - t1) / iterations * 1_000_000

    overhead_pct = (
        ((enabled_time - baseline_time) / baseline_time) * 100.0
        if baseline_time > 0
        else 0.0
    )
    return baseline_time, enabled_time, overhead_pct


def run_all_benchmarks():
    print("=" * 70)
    print("PHASE 29 — PRODUCTION OBSERVABILITY & TRACING BENCHMARKS")
    print("=" * 70)

    us_ctx_creation = benchmark_context_creation()
    print(f"Context Creation:            {us_ctx_creation:8.2f} µs/op")

    us_ctx_prop = benchmark_context_propagation()
    print(f"Context Propagation:         {us_ctx_prop:8.2f} µs/op")

    us_event_creation = benchmark_event_creation()
    print(f"Event Creation:              {us_event_creation:8.2f} µs/op")

    us_span_lifecycle = benchmark_span_lifecycle()
    print(f"Span Lifecycle (Start+End):  {us_span_lifecycle:8.2f} µs/op")

    us_metric_inc = benchmark_metric_increment()
    print(f"Metric Increment:            {us_metric_inc:8.2f} µs/op")

    us_hist_update = benchmark_histogram_update()
    print(f"Histogram Update:            {us_hist_update:8.2f} µs/op")

    us_aggregation = benchmark_telemetry_aggregation()
    print(f"Telemetry Aggregation:       {us_aggregation:8.2f} µs/op")

    us_health = benchmark_health_snapshot()
    print(f"Health Snapshot:             {us_health:8.2f} µs/op")

    us_slo = benchmark_slo_evaluation()
    print(f"SLO Evaluation:              {us_slo:8.2f} µs/op")

    us_anomaly = benchmark_anomaly_detection()
    print(f"Anomaly Detection:           {us_anomaly:8.2f} µs/op")

    us_incident = benchmark_incident_detection()
    print(f"Incident Creation:           {us_incident:8.2f} µs/op")

    us_full_pipeline = benchmark_full_observability_pipeline()
    print(f"Full Observability Pipeline: {us_full_pipeline:8.2f} µs/op")

    print("-" * 70)
    b_time, e_time, ov_pct = benchmark_control_plane_overhead()
    print(f"ControlPlane Baseline Submit: {b_time:8.2f} µs/job")
    print(f"ControlPlane With Obs Submit: {e_time:8.2f} µs/job")
    print(f"ControlPlane Overhead:        {ov_pct:8.2f} %")
    print("=" * 70)


if __name__ == "__main__":
    run_all_benchmarks()
