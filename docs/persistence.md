# Phase 24 — Production Persistence & Distributed Infrastructure

Phase 24 establishes a robust, transactional persistence and multi-process/multi-node execution layer for `aireliability`.

This architecture enables reliability test runs, worker states, job definitions, attempt histories, and execution summaries to survive process termination, power loss, and worker crashes.

---

## 1. Architectural Overview

```text
                        AsyncReliabilityRunner
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
    ReliabilityWorker       ReliabilityWorker       ReliabilityWorker
    (Worker Heartbeats)     (Worker Heartbeats)     (Worker Heartbeats)
          │                       │                       │
          ▼                       ▼                       ▼
    ReliabilityJob          ReliabilityJob          ReliabilityJob
    (Atomic Claims)         (Atomic Claims)         (Atomic Claims)
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │
                                  ▼
                    DistributedPersistenceBackend
                   (SQLite / InMemory / Postgres)
                                  │
        ┌───────────────┬─────────┴─────────┬───────────────┐
        ▼               ▼                   ▼               ▼
   executions        workers              jobs           outcomes
   (Run Status)    (Heartbeats)        (State Mach.)    (Idempotent)
```

---

## 2. Core Storage Protocol

`DistributedPersistenceBackend` is the unified storage contract:

```python
from aireliability import DistributedPersistenceBackend, SQLiteDistributedStorage

# Initialize persistent SQLite storage
storage = SQLiteDistributedStorage("path/to/reliability.db")
```

### Storage Operations:
- **Jobs**: `save_job()`, `get_job()`, `update_job()`, `list_jobs()`, `get_pending_jobs()`, `get_running_jobs()`, `get_failed_jobs()`
- **Outcomes**: `save_outcome()`, `get_outcome()`, `list_outcomes()`
- **Executions**: `save_execution()`, `get_execution()`, `list_executions()`, `delete_execution()`
- **Workers**: `save_worker()`, `get_worker()`, `list_workers()`, `detect_stale_workers()`
- **Coordination & Recovery**: `claim_job()`, `recover_execution()`

---

## 3. Persistent Data Models

### `ExecutionRecord`
Stores run-level orchestration metadata and aggregated counters:
- `execution_id`: Hex unique execution identifier.
- `status`: Lifecycle status (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `RESUMED`).
- `created_at`, `started_at`, `completed_at`: Timezone-aware UTC timestamps.
- `total_jobs`, `completed_jobs`, `failed_jobs`, `timed_out_jobs`, `cancelled_jobs`, `retry_count`: Progress counters.
- `metadata`: Sanitized user attributes.

### `PersistentWorkerRecord`
Tracks worker processes and liveness:
- `worker_id`: Worker process identity.
- `execution_id`: Attached execution context.
- `state`: Explicit state (`IDLE`, `STARTING`, `RUNNING`, `COMPLETED`, `FAILED`, `STOPPED`).
- `current_job_id`: Active claimed job.
- `last_heartbeat`: Timestamp updated periodically to prevent stale worker failover.
- `completed_jobs`, `failed_jobs`: Worker throughput statistics.

### `PersistentJobRecord`
Represents an individual unit of reliability testing:
- `job_id`, `execution_id`, `test_id`: Identification and trace correlation.
- `status`: Deterministic job lifecycle state (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, `RETRYING`).
- `attempt`, `max_retries`: Attempt number and retry limits.
- `assigned_worker_id`: Worker that successfully claimed this job attempt.

### `PersistentOutcomeRecord`
Immutable record of an execution attempt:
- `outcome_id`: `out_{job_id}_{attempt}`.
- `duration_ms`: Wall-clock latency.
- `run_result`: Full evaluation and trace snapshot.
- `retryable`: Flag indicating whether the error is eligible for automated retry.

---

## 4. Job & Worker State Machines

Deterministic transition validations enforce lifecycle guarantees:

```text
Job States:
PENDING ──► RUNNING ──► COMPLETED (Terminal)
              │
              ├──► FAILED ────┐
              ├──► TIMED_OUT ─┼──► RETRYING ──► RUNNING
              └──► CANCELLED (Terminal)
```

Illegal transitions (e.g. attempting to move directly from `PENDING` to `COMPLETED`, or transitioning from terminal `COMPLETED` to `RUNNING`) raise `InvalidStateTransitionError`.

```python
from aireliability import JobStatus, validate_job_transition

validate_job_transition(JobStatus.PENDING, JobStatus.RUNNING)  # OK
validate_job_transition(
    JobStatus.COMPLETED, JobStatus.RUNNING
)  # Raises InvalidStateTransitionError
```

---

## 5. SQLite Persistence Backend

`SQLiteDistributedStorage` provides a zero-setup local persistent database with:
- ACID transactional integrity using write-ahead logging (`PRAGMA journal_mode=WAL;`).
- Concurrent multi-process reads and exclusive atomic writes.
- Schema versioning with migration tables (`distributed_schema_migrations`).
- Automatic indexes on `execution_id`, `status`, `test_id`, `worker_id`, and `created_at`.
- Full asynchronous support via `AsyncDistributedPersistenceBackend` (`asave_job`, `aget_job`, `aclaim_job`).

```python
from aireliability import AsyncReliabilityRunner, SQLiteDistributedStorage, TestCase

storage = SQLiteDistributedStorage(".aireliability/runs.db")
runner = AsyncReliabilityRunner(
    agent=my_agent,
    storage=storage,
    max_concurrency=10,
)
```

---

## 6. Atomic Job Claiming & Idempotency

### Atomic Claiming
Workers prevent duplicate execution of the same job attempt using transactional conditional updates:

```sql
UPDATE distributed_jobs
SET status = 'running', assigned_worker_id = ?
WHERE job_id = ? AND status = 'pending'
```

If multiple workers attempt to claim the same job simultaneously, exactly one succeeds (`rowcount == 1`).

### Idempotency
Outcomes are keyed by `(job_id, attempt)`. If network partitions or duplicate retry emissions submit older results, earlier attempts never overwrite newer attempt states.

---

## 7. Stale Worker Detection & Execution Recovery

When a worker process crashes or loses network connectivity, its heartbeat ceases:

```python
# Detect workers that have not reported heartbeats in 30 seconds
stale_workers = storage.detect_stale_workers(timeout_seconds=30.0)

# Recover jobs and requeue them for healthy workers
recovery_summary = storage.recover_execution(execution_id, stale_timeout_seconds=30.0)
print(f"Requeued jobs: {recovery_summary.requeued_jobs}")
```

1. Stale workers are marked `FAILED`.
2. Running jobs assigned to stale workers are requeued to `PENDING` with incremented `attempt`.
3. Recovery provenance is preserved in job metadata (`recovered_from_worker`, `recovery_timestamp`).
4. Completed jobs are never re-executed.

---

## 8. Resuming Interrupted Executions

If an entire execution run is interrupted (e.g. process SIGKILL, CI cancellation), `resume_execution` restarts only incomplete jobs:

```python
runner = AsyncReliabilityRunner(agent=my_agent, storage=storage)
summary = await runner.resume_execution(execution_id="exec_12345")
```

The runner:
1. Recovers any stale jobs.
2. Identifies all tests not yet marked `COMPLETED`.
3. Executes remaining tests concurrently up to `max_concurrency`.
4. Rebuilds the final deterministic execution report from persisted storage using `ResultAggregator.from_storage()`.

---

## 9. CLI Persistence Commands

The `airel` CLI exposes complete management commands:

```bash
# List all executions
airel executions list

# Inspect detailed status and jobs of a specific execution
airel executions show <execution_id>

# Resume an interrupted execution
airel executions resume <execution_id>

# Force recovery of stale workers and requeue jobs
airel executions recover <execution_id>

# List all registered workers
airel workers list

# Detect workers that have timed out
airel workers stale --timeout 30.0
```

---

## 10. Optional Integrations

### PostgreSQL (`aireliability[postgres]`)
Optional enterprise database backend in `aireliability.integrations.postgres.PostgresDistributedStorage`.
- Requires: `pip install 'aireliability[postgres]'`

### Redis (`aireliability[redis]`)
Optional distributed queue coordinator in `aireliability.integrations.redis.RedisDistributedCoordinator`.
- Requires: `pip install 'aireliability[redis]'`

---

## 11. Performance Benchmarks

Measured on macOS arm64 across 500 test records:

| Operation | InMemory Storage | SQLite Storage |
|:---|:---|:---|
| `save_job` | 0.40 µs | 12.16 µs |
| `claim_job` | 2.76 µs | 7.56 µs |
| `save_outcome` | 1.77 µs | 20.30 µs |
| `query` | 0.026 ms | 11.052 ms |
| `aggregation` | 0.153 ms | 7.780 ms |
| `recovery` | 0.047 ms | 4.277 ms |

### Concurrency Scaling (100 Tests)
- **1 Worker**: 31.91 ms (3,133 tests/sec)
- **5 Workers**: 28.95 ms (3,454 tests/sec)
- **10 Workers**: 28.44 ms (3,515 tests/sec)
- **25 Workers**: 27.52 ms (3,633 tests/sec)
