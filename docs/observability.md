# Production Observability, Distributed Tracing & Intelligent Operations

Phase 29 establishes an integrated, zero-dependency production observability architecture for `aireliability`. It provides distributed tracing, multi-window metrics aggregation, operational health snapshots, Service Level Objective (SLO) error-budget tracking, statistical anomaly detection, and operational incident correlation without requiring external platforms like Prometheus, OpenTelemetry Collector, Jaeger, Datadog, Kafka, or Redis.

---

## 1. Architecture Overview

Phase 29 is structured under `aireliability.observability` and coordinates across all subsystems:

```text
SecurityGateway ───► ResourceGovernance ───► ControlPlane ───► Worker ───► Resilience
       │                      │                    │              │             │
       ▼                      ▼                    ▼              ▼             ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           Observability Subsystem                                 │
│                                                                                   │
│  Contextvars Propagation ──► Structured Events ──► Distributed Tracer (Spans)    │
│                                                                                   │
│  Metrics Engine (Histograms/Percentiles) ──► Telemetry Aggregator (Windows)       │
│                                                                                   │
│  Operational Health Engine ──► SLI/SLO & Error Budget ──► Anomaly & Incidents     │
│                                                                                   │
│  Exporters (Prometheus, JSONL, JSON, CSV) ──► Retention & Sanitization Policies  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Correlation Context (`context.py`)

Observability context automatically flows through synchronous and asynchronous operations using standard library `contextvars`:

```python
from aireliability.observability import observability_context, get_current_context

with observability_context(tenant_id="tenant_corp", trace_id="trace_xyz"):
    ctx = get_current_context()
    assert ctx.tenant_id == "tenant_corp"
    assert ctx.trace_id == "trace_xyz"
```

Available context dimensions:
- `trace_id`
- `span_id`
- `parent_span_id`
- `execution_id`
- `job_id`
- `tenant_id`
- `project_id`
- `namespace`
- `worker_id`
- `request_id`

---

## 3. Distributed Tracing (`traces.py` & `spans.py`)

Provider-neutral tracing without external OpenTelemetry runtime dependencies:

```python
from aireliability.observability import Tracer, SpanKind

tracer = Tracer()
root_span = tracer.start_trace(name="request.root", tenant_id="acme")

with root_span:
    with tracer.span("auth.verify", kind=SpanKind.SERVER) as s1:
        s1.set_attribute("principal", "user-123")
    with tracer.span("worker.execute", kind=SpanKind.WORKER) as s2:
        s2.add_event("starting_batch")

record = tracer.finish_trace(root_span.trace_id)
print(f"Recorded trace with {len(record.spans)} spans, status: {record.status}")
```

Supported span kinds: `CLIENT`, `SERVER`, `INTERNAL`, `WORKER`, `PROVIDER`, `SCHEDULER`, `PERSISTENCE`.

---

## 4. Structured Events (`events.py`)

Event recorder capturing standardized lifecycle events with automatic correlation:

```python
from aireliability.observability import EventRecorder

recorder = EventRecorder()
recorder.record_event(
    event_type="job.submitted",
    tenant_id="acme",
    attributes={"test_id": "test-1", "api_key": "secret-value"},
)
# Sensitive attributes are automatically sanitized to "[REDACTED]"
```

Supported event categories:
- `execution.*` (`started`, `completed`, `failed`)
- `job.*` (`submitted`, `queued`, `dispatched`, `completed`, `failed`, `cancelled`, `reassigned`)
- `worker.*` (`started`, `healthy`, `degraded`, `quarantined`, `recovered`)
- `provider.*` (`request_started`, `request_completed`, `request_failed`)
- `security.*` (`authentication`, `authorization`, `denied`, `replay_detected`)
- `resilience.*` (`failure`, `retry`, `circuit_opened`, `circuit_closed`, `load_shed`)
- `tenant.*` (`admitted`, `rejected`, `rate_limited`, `quota_exceeded`)
- `scheduler.*` (`queue_depth`, `dispatch`, `starvation`)
- `system.*` (`health_changed`, `incident_detected`, `incident_resolved`)

---

## 5. Metrics Engine & Prometheus Format (`metrics.py`)

In-process counter, gauge, histogram, and rate metrics with percentile computations:

```python
from aireliability.observability import MetricsEngine

metrics = MetricsEngine()
metrics.counter("aireliability_jobs_submitted_total").increment(tenant_id="tenant_1")
metrics.gauge("aireliability_queue_depth").set(3.0)
metrics.histogram("aireliability_job_latency_seconds").observe(
    0.045, tenant_id="tenant_1"
)

# Prometheus Exposition:
prom_output = metrics.render_prometheus()
```

Percentile calculations (`p50`, `p90`, `p95`, `p99`, `min`, `max`, `mean`, `count`) are computed efficiently using sliding time windows without external numerical libraries.

---

## 6. Operational Health Engine (`health.py`)

Synthesizes operational health across 7 core dimensions:
- `scheduler_status`
- `storage_status`
- `worker_status`
- `resilience_status`
- `security_status`
- `tenancy_status`
- `queue_status`

Overall status is deterministically computed into: `HEALTHY`, `DEGRADED`, `UNHEALTHY`, or `UNKNOWN`.

---

## 7. Service Level Objectives (SLOs) & Error Budgets (`slo.py`)

Tracks SLIs (availability, success rate, latency, worker success rate) and computes error budgets:

```python
from aireliability.observability import SLOManager

slo_mgr = SLOManager(aggregator)
slo = slo_mgr.register_slo(
    name="execution_success_rate",
    sli_name="success_rate",
    target=0.999,  # 99.9%
    window_seconds=300.0,
)

eval_res = slo_mgr.evaluate_slo(slo.slo_id)
print(
    f"Compliant: {eval_res.compliant}, Remaining Budget: {eval_res.budget_percentage}%"
)
```

Calculated metrics:
- `allowed_error_budget`
- `consumed_error_budget`
- `remaining_error_budget`
- `budget_percentage`
- `burn_rate`

---

## 8. Statistical Anomaly Detection (`anomaly.py`)

Lightweight, deterministic statistical evaluation using moving averages, standard deviation, z-score, and exponentially weighted moving averages (EWMA):

```python
from aireliability.observability import StatisticalAnomalyDetector

detector = StatisticalAnomalyDetector(z_threshold_warning=2.0, z_threshold_anomaly=3.0)
for val in [10.0, 10.1, 9.9, 10.2, 10.0]:
    detector.record_observation("latency", val)

report = detector.detect("latency", current_value=45.0)
print(f"Severity: {report.severity}, Z-Score: {report.details['z_score']}")
```

---

## 9. Incident Management (`incidents.py`)

Maintains the incident lifecycle (`DETECTED` -> `ACKNOWLEDGED` -> `MITIGATING` -> `RESOLVED`) correlated with trace IDs, execution IDs, workers, and events:

```python
from aireliability.observability import IncidentManager

incidents = IncidentManager()
inc = incidents.create_incident(
    title="Worker Quarantine Spike",
    description="Multiple workers quarantined by resilience manager",
    severity="CRITICAL",
    tenant_id="tenant_1",
)
incidents.acknowledge_incident(inc.incident_id)
incidents.resolve_incident(inc.incident_id)
```

---

## 10. CLI Reference

```bash
# General status and health
airel observability status
airel observability health

# Metrics and Prometheus text
airel observability metrics
airel observability metrics --tenant <tenant_id>

# Distributed tracing
airel observability traces
airel observability trace <trace-id>

# Structured events
airel observability events

# Operational incidents
airel observability incidents
airel observability incident <incident-id>

# SLOs & Error Budgets
airel observability slo

# Statistical anomalies
airel observability anomalies

# Subsystem inspections
airel observability workers
airel observability providers

# Telemetry data export
airel observability export metrics
airel observability export traces
airel observability export events
```
