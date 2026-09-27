# Phase 26 — Fault Tolerance, Resilience & Self-Healing

## 1. Overview

Phase 26 introduces production-grade, provider-neutral fault tolerance, resilience, and self-healing to the `aireliability` platform. It transforms distributed reliability execution from basic retry and stale-worker detection into a proactive reliability platform capable of:

- Classifying failures into structured taxonomies with credential sanitization.
- Isolating faulty providers and workers using three-state Circuit Breakers.
- Preventing retry stampedes via exponential backoff with full jitter.
- Enforcing bounded concurrency isolation per partition via Bulkheads.
- Tracking fine-grained worker health (`HEALTHY`, `DEGRADED`, `QUARANTINED`, `RECOVERING`).
- Protecting systems from cascading failure storms and queue overload via intelligent load shedding.
- Executing multi-component health checks across persistence, schedulers, and workers.
- Persisting structured failure records in SQLite and InMemory storage backends.
- Emitting comprehensive Prometheus metrics and structured telemetry events.

---

## 2. Failure Model & Classification

Failures in distributed AI systems stem from many distinct layers (rate limits, upstream 5xx, timeouts, network partitions, authentication expirations, memory limits). The `FailureClassifier` deterministically maps raw exceptions and errors into a structured `DetailedFailureRecord`.

### Categories (`ResilienceFailureCategory`)
- `worker_failure`: Worker crash or unhandled worker-side runtime failure.
- `worker_timeout`: Heartbeat or task deadline expiration on a worker.
- `job_timeout`: Individual job exceeded configured execution timeout.
- `provider_failure`: Upstream LLM provider 5xx error or service unavailability.
- `network_failure`: Connection reset, DNS failure, or socket error.
- `rate_limit_failure`: HTTP 429 or provider quota exhaustion.
- `authentication_failure`: HTTP 401/403 or invalid API keys (non-retryable).
- `persistence_failure`: Database lock, disk I/O, or SQLite OperationalError.
- `scheduler_failure`: Queue corruptions or internal dispatch exceptions.
- `cancellation`: User-initiated or cooperative job cancellation.
- `resource_exhaustion`: Out-of-memory or worker concurrency limits.
- `unknown_failure`: Unclassified fallback category.

Every `DetailedFailureRecord` enforces mandatory redaction through the package's `SanitizationPolicy`.

---

## 3. Circuit Breaker

The `CircuitBreaker` implements the standard three-state pattern:

```text
       CLOSED
         │
         │ failures >= failure_threshold
         ▼
        OPEN
         │
         │ cooldown >= recovery_timeout_seconds
         ▼
     HALF_OPEN
       │      │
       │      └── failure ───────► OPEN
       │
       └── successes >= success_threshold ──► CLOSED
```

### Key Parameters:
- `failure_threshold`: Consecutive failures before transitioning to `OPEN`.
- `recovery_timeout_seconds`: Cooldown time before entering `HALF_OPEN`.
- `half_open_probe_count`: Concurrency limit for probe requests in `HALF_OPEN`.
- `success_threshold`: Consecutive successful probe requests required to close the circuit.

---

## 4. Retries & Backoff with Jitter

The `ResilientRetryPolicy` calculates backoff delays non-blockingly across multiple strategies:

- `NONE`: No delay.
- `FIXED`: Uniform delay per retry attempt.
- `LINEAR`: Delay scales proportionally with retry attempt (`delay = base * attempt`).
- `EXPONENTIAL`: Exponential backoff (`delay = min(max_delay, base * factor^(attempt - 2))`).
- `EXPONENTIAL_JITTER`: Exponential backoff with uniform random spread:
  $$\text{delay} = \text{delay}_{\text{base}} \pm (\text{delay}_{\text{base}} \times \text{jitter\_factor})$$

Retries automatically filter out non-retryable failures (such as authentication or cancellation).

---

## 5. Bulkhead Isolation

The `Bulkhead` module provides independent concurrency limits for providers, job priority tiers, or worker pools. This guarantees that latency spikes or rate-limit throttling in one model provider cannot exhaust worker slots allocated to other workloads.

```python
from aireliability import Bulkhead

bulkhead = Bulkhead(default_limit=10)
bulkhead.set_limit("provider:anthropic", limit=5)

async with bulkhead.acquire("provider:anthropic"):
    # Guarded execution slot
    pass
```

---

## 6. Worker Health, Quarantine & Self-Healing

The `WorkerHealthManager` tracks per-worker lifecycle statistics and manages progressive degradation:

```text
HEALTHY
   │
   │ failures >= degradation_threshold
   ▼
DEGRADED
   │
   │ failures >= quarantine_threshold
   ▼
QUARANTINED
   │
   │ recover_worker()
   ▼
RECOVERING
   │
   ├── success >= recovery_success_threshold ──► HEALTHY
   └── failure ──────────────────────────────► QUARANTINED
```

### Self-Healing Guarantee:
- Quarantined workers are excluded from job dispatching via `worker_health_filter`.
- When eligible, a quarantined worker is transitioned to `RECOVERING`.
- Once a recovering worker executes probe jobs successfully, it is reinstated to `HEALTHY`.
- Historical metrics, total failures, and provenance are strictly preserved.

---

## 7. Failure Storm Protection & Load Shedding

The `LoadShedder` monitors a sliding time window for execution results. If the rolling failure rate exceeds `failure_rate_threshold` (e.g. 50%) or if the queue depth exceeds `max_queue_depth`:

1. High failure rate or queue saturation is detected.
2. Low and normal priority jobs are shed or deferred with structured rejection reasons.
3. High and critical priority jobs are preserved.

---

## 8. Health Checks

`HealthChecker` provides non-invasive diagnostic probes returning structured `HealthCheckResult` records:

- Storage health: Checks persistence backend responsiveness and queries execution records.
- Scheduler health: Checks event-loop status and internal queue health.
- Worker health: Verifies worker heartbeat freshness and failure profile.

---

## 9. Prometheus Metrics & Telemetry

When `prometheus-client` is installed, the following metrics are exposed:

- `aireliability_failures_total`: Total failure records partitioned by `failure_type` and `severity`.
- `aireliability_retry_attempts_total`: Retries partitioned by `strategy`.
- `aireliability_circuit_breaker_state`: Gauge indicating circuit state (0=closed, 1=open, 2=half-open).
- `aireliability_workers_quarantined`: Current gauge of quarantined workers.
- `aireliability_worker_recoveries_total`: Total worker self-healing recoveries.
- `aireliability_jobs_reassigned_total`: Total jobs reassigned to alternate healthy workers.
- `aireliability_jobs_shed_total`: Total jobs rejected or shed due to failure storms.
- `aireliability_recovery_duration_seconds`: Histogram of recovery operation durations.
- `aireliability_failure_rate`: Rolling failure rate in active monitoring window.

Structured telemetry events emitted:
- `reliability.failure_detected`
- `reliability.circuit_opened`
- `reliability.circuit_closed`
- `reliability.worker_quarantined`
- `reliability.worker_recovered`
- `reliability.job_reassigned`
- `reliability.load_shed`

---

## 10. CLI Usage

The `airel` command-line tool includes first-class operations for resilience management:

```bash
# View resilience subsystem status
airel resilience status

# List recent classified failure records
airel resilience failures [--execution-id <id>]

# Inspect worker health states
airel resilience workers

# Inspect circuit breaker states
airel resilience circuits

# Manually quarantine an unhealthy worker
airel resilience quarantine <worker_id>

# Unquarantine and initiate self-healing for a worker
airel resilience unquarantine <worker_id>

# Trigger an execution-wide recovery sweep
airel resilience recover
```
