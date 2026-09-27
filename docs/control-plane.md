# Production Control Plane & Intelligent Job Scheduling (Phase 25)

## Overview

The `aireliability` Control Plane provides a lightweight, provider-neutral, dependency-light orchestration and scheduling tier designed to coordinate job queues, scheduling policies, worker capacity, retry backoffs, cooperative cancellations, and distributed execution state.

Building upon Phase 24's persistent storage, worker heartbeat protocols, and failure recovery primitives, Phase 25 adds intelligent scheduling and decoupled job management without making external messaging systems (Redis, Kafka, RabbitMQ) or distributed orchestrators (Celery, Kubernetes) mandatory.

```text
                    Control Plane
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
      Queue          Scheduler       Worker Manager
 (FIFO/Priority)    (Dispatcher)   (Capacity/Heartbeat)
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                 Distributed Workers
                         │
                         ▼
                 Persistence Layer
              (SQLite / InMemory / Postgres)
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
         Telemetry   Evaluation    Recovery
```

---

## Key Features

1. **Provider-Neutral Job Queue Protocol (`JobQueue`)**:
   - Zero-dependency `InMemoryJobQueue` with thread-safe and async-safe concurrency (`asyncio.Lock`).
   - Supports queueing, dequeuing, peeking, removing, filtering, and priority sorting.
   - Preserves complete correlation IDs (`execution_id`, `job_id`, `test_id`).

2. **Scheduling Policies**:
   - **FIFO (`FIFOPolicy`)**: Oldest queued jobs execute first, with deterministic job ID tie-breaking.
   - **Priority (`PriorityPolicy`)**: Strict priority sorting (`CRITICAL` > `HIGH` > `NORMAL` > `LOW`), followed by queued timestamp and deterministic ID.
   - **Fair Scheduling (`FairSchedulingPolicy`)**: Prevents low-priority job starvation by applying priority age boosts when a job waits longer than `aging_threshold_seconds`.
   - **Retry-Aware Scheduling (`RetryAwareSchedulingPolicy`)**: Balances newly submitted jobs against retried jobs by applying configurable attempt-based ranking penalties (`retry_penalty_weight`).

3. **Delayed Jobs**:
   - Jobs can specify a future `scheduled_at` timestamp.
   - Dequeuing and peeking operations inspect `job.is_eligible_at(now)` and skip delayed jobs until their timer has expired.

4. **Worker Capacity & Load Balancing (`WorkerManager`)**:
   - Workers declare concurrent execution capacity limits (`capacity`).
   - Tracks active running jobs and available slots per worker (`available_slots`).
   - Rejects job assignments if a worker's capacity is exhausted (`WorkerCapacityExceededError`).
   - Deterministic least-loaded selection (`select_best_worker`) prioritizes workers with the most free capacity slots.
   - Integrates with Phase 24 heartbeat timestamps and filters out stale workers.

5. **Configurable Retry Policies (`RetryPolicy`)**:
   - **None (`BackoffStrategy.NONE`)**: Immediate re-execution up to `max_retries`.
   - **Fixed (`BackoffStrategy.FIXED`)**: Constant delay (`initial_delay_seconds`) between retry attempts.
   - **Exponential (`BackoffStrategy.EXPONENTIAL`)**: Exponential backoff (`initial_delay_seconds * (backoff_factor ** (attempt - 2))`) capped at `max_delay_seconds`.

6. **Cooperative Job Cancellation (`CancellationCoordinator`)**:
   - Cooperative cancellation tokens (`asyncio.Event`) signal running tasks.
   - Rejects cancellation requests for already `COMPLETED` jobs (`CancellationError`).
   - Updates queue and storage state to `CANCELLED`.

7. **ControlPlane Controller (`ControlPlane`)**:
   - High-level orchestrator coordinating queues, workers, schedulers, and storages.
   - API: `submit_job()`, `cancel_job()`, `get_job()`, `list_jobs()`, `start()`, `stop()`, `execute_execution()`, `recover_stale_workers()`.

8. **Security & Sanitization**:
   - Integrates with Phase 22 `SanitizationPolicy`.
   - Redacts sensitive credential keywords (`api_key`, `token`, `secret`, `password`, `authorization`, `private_key`, `bearer`, `credentials`) in metadata and tags.

9. **CLI Extensions**:
   - `airel jobs list`: List all persisted or queued jobs.
   - `airel jobs submit <test_id>`: Submit a new job to the control plane.
   - `airel jobs show <job_id>`: Display detailed metadata for a job.
   - `airel jobs cancel <job_id>`: Cancel a queued, scheduled, or running job.
   - `airel jobs retry <job_id>`: Requeue a failed job attempt.
   - `airel jobs queue`: View pending and queued jobs.
   - `airel scheduler status`: Query scheduler runtime state.

---

## Python API Usage

### Submitting and Scheduling Jobs

```python
import asyncio
from aireliability import (
    ControlPlane,
    ControlPlaneConfig,
    JobPriority,
    RetryPolicy,
    BackoffStrategy,
    TestCase,
)


async def main():
    def sample_agent(inputs):
        return {"response": f"Processed: {inputs['query']}"}

    # Configure control plane with Fair Scheduling and Exponential Retries
    config = ControlPlaneConfig(
        max_concurrency=4,
        scheduling_policy="fair",
        default_retry_policy=RetryPolicy(
            max_retries=2,
            strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay_seconds=0.5,
        ),
    )

    cp = ControlPlane(agent=sample_agent, config=config)

    # Submit test case with CRITICAL priority
    tc = TestCase(id="tc_auth", name="Authentication Check", input={"query": "login"})
    job = await cp.submit_job(
        tc,
        priority=JobPriority.CRITICAL,
    )
    print(f"Submitted job: {job.job_id} [State: {job.queue_state}]")

    # Run execution to completion
    summary = await cp.execute_execution([tc])
    print(f"Passed: {summary.passed_tests}/{summary.total_jobs}")

    await cp.stop()


asyncio.run(main())
```

### Worker Capacity Management

```python
from aireliability import WorkerManager


async def manage_workers():
    mgr = WorkerManager(default_capacity=4)
    await mgr.register_worker("worker_a", capacity=2)
    await mgr.register_worker("worker_b", capacity=4)

    # Select least-loaded worker (worker_b has 4 slots vs 2)
    best = await mgr.select_best_worker()
    assert best.worker_id == "worker_b"

    # Acquire slot
    await mgr.acquire_capacity("worker_b")
    assert (await mgr.get_worker("worker_b")).available_slots == 3
```

---

## Performance Benchmarks

Measured on local hardware without external network dependencies (`benchmarks/run_phase25_benchmarks.py`):

| Operation | Implementation | Latency |
| :--- | :--- | :--- |
| `enqueue` | `InMemoryJobQueue` (1,000 ops) | **2.43 µs/op** |
| `peek` | `InMemoryJobQueue` (Priority Sort) | **246.00 µs/op** |
| `dequeue` | `InMemoryJobQueue` (Priority Sort) | **162.47 µs/op** |
| `select_best_worker` | `WorkerManager` (50 workers) | **27.87 µs/op** |
| `acquire_capacity + release` | `WorkerManager` | **3.62 µs/op** |

### Worker Scaling Throughput (100 Jobs/Run)

| Active Workers | Total Duration | Throughput |
| :--- | :--- | :--- |
| **1 Worker** | 2555.49 ms | 39.1 tests/sec |
| **5 Workers** | 515.21 ms | 194.1 tests/sec |
| **10 Workers** | 258.80 ms | 386.4 tests/sec |
| **25 Workers** | 105.48 ms | 948.0 tests/sec |
| **50 Workers** | 62.03 ms | **1612.2 tests/sec** |

---

## Limitations

- `InMemoryJobQueue` is scoped to the current Python process. For persistence across process crashes, jobs are simultaneously registered with `DistributedPersistenceBackend` (`SQLiteDistributedStorage`).
- Cooperative cancellation requires non-blocking or asyncio-cooperative agent functions. Unyielding synchronous C extensions cannot be cancelled mid-execution.
