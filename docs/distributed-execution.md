# Distributed Reliability & Async Execution

`aireliability` provides an asynchronous, concurrent, and distributed reliability evaluation engine. It enables developers to evaluate suites of reliability tests and regression suites across parallel worker pools with configurable concurrency, per-test timeouts, automatic retries with provenance, and deterministic output ordering.

```text
                        Test Suite (TestCase 1...N)
                                    │
                                    ▼
                        AsyncReliabilityRunner
                     (Bounded Concurrency Semaphore)
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
   ReliabilityWorker 1       ReliabilityWorker 2       ReliabilityWorker N
   (Job: test_1, try 1)      (Job: test_2, try 1)      (Job: test_3, try 1)
          │                         │                         │
          ├──────── Timeout /       ├──────── Crash /         ├──────── Nominal
          │         Retry           │         Recovery        │         Completion
          ▼                         ▼                         ▼
   ReliabilityWorker 1       ReliabilityWorker 2       RunResult(passed=True)
   (Job: test_1, try 2)      (Job: test_2, try 2)             │
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                                    ▼
                             ResultAggregator
                   (Deterministic Sort & Deduplication)
                                    │
                                    ▼
                      DistributedExecutionSummary
                 (Results 1...N in original test order)
```

---

## 1. Architecture & Design Principles

1. **Zero External Infrastructure**: No mandatory requirement for Redis, Celery, Kafka, RabbitMQ, or PostgreSQL. The core concurrent engine runs entirely on standard Python `asyncio` primitives.
2. **Deterministic Result Ordering**: While tests execute concurrently across workers, outputs and reports are deterministically sorted by their original test sequence.
3. **Correlation Context**: Every distributed execution preserves explicit correlation identifiers:
   - `execution_id`
   - `job_id`
   - `worker_id`
   - `test_id`
   - `attempt`
4. **Transient Retry & Failure Recovery**: Failed jobs can be automatically retried with attempts tracked in `JobExecutionOutcome` without losing historical failure provenance.
5. **Non-Blocking Telemetry**: Telemetry traces can be queued into `AsyncTelemetryCollector` and flushed asynchronously in the background.

---

## 2. Core Abstractions & Data Models

### ReliabilityJob
Serializable specification of a test execution job:
```python
@dataclass(frozen=True)
class ReliabilityJob:
    job_id: str
    execution_id: str
    test_case: TestCase
    priority: int = 0
    attempt: int = 1
    max_retries: int = 0
    timeout_seconds: float | None = None
    status: JobStatus = JobStatus.PENDING
```

### ReliabilityWorker
State machine worker executing jobs with lifecycle states (`IDLE`, `STARTING`, `RUNNING`, `COMPLETED`, `FAILED`, `STOPPED`).

### JobExecutionOutcome
Immutable record of a job attempt containing:
- `worker_id`, `job_id`, `test_id`, `status`
- `run_result` (if execution produced a result)
- `error`, `error_type`, `retryable`
- `started_at`, `completed_at`, `duration_ms`

### DistributedExecutionSummary
Consolidated summary aggregating all outcomes:
- `total_jobs`, `completed_jobs`, `failed_jobs`, `timed_out_jobs`
- `passed_tests`, `failed_tests`, `total_retries`, `total_latency_ms`
- Deterministically sorted `results: list[RunResult]`

---

## 3. Usage Examples

### Running Tests Concurrently with `AsyncReliabilityRunner`

```python
import asyncio
from aireliability import (
    AsyncReliabilityRunner,
    OutputEquals,
    TestCase,
)


async def main():
    def agent(user_input: str) -> str:
        return f"Hello, {user_input}"

    runner = AsyncReliabilityRunner(
        agent=agent,
        evaluators=[OutputEquals("Hello, world")],
        max_concurrency=10,
        test_timeout_seconds=5.0,
        max_retries=2,
    )

    test_cases = [
        TestCase(id=f"tc_{i}", name=f"test_{i}", input="world") for i in range(50)
    ]

    summary = await runner.execute_many(test_cases)
    print(f"Total tests: {summary.total_jobs}")
    print(f"All passed: {summary.all_passed}")
    print(f"Total retries: {summary.total_retries}")


asyncio.run(main())
```

### Parallel Regression Suite Evaluation

`RegressionRunner` seamlessly supports concurrent regression suite execution:

```python
import asyncio
from aireliability import BaselineManager, RegressionRunner


async def run_regression():
    runner = RegressionRunner(agent=my_agent, baseline_manager=bm)
    suite_result = await runner.run_suite_async(
        regression_tests,
        max_concurrency=8,
        compare_baseline="main",
    )
    assert suite_result.all_passed
    assert not suite_result.comparison_summary.has_regressions


asyncio.run(run_regression())
```

---

## 4. Async Telemetry Buffering

To prevent telemetry recording from blocking high-throughput concurrent workers, use `AsyncTelemetryCollector`:

```python
from aireliability import (
    AsyncReliabilityRunner,
    AsyncTelemetryCollector,
    InMemoryTelemetryCollector,
)

sink = InMemoryTelemetryCollector()
async_telemetry = AsyncTelemetryCollector(sink_collector=sink, max_buffer_size=5000)

runner = AsyncReliabilityRunner(
    agent=my_agent,
    telemetry_collector=async_telemetry,
    max_concurrency=20,
)
```

Traces are queued in-memory and periodically flushed to the sink in the background.

---

## 5. Performance Benchmarks

Performance measured across 100 test case executions:

| Execution Engine | Concurrency | Total Time | Per-Test Latency | Throughput |
| :--- | :--- | :--- | :--- | :--- |
| **`ReliabilityRunner` (Sequential)** | 1 | 0.58 ms | 5.79 µs | ~172,000 tests/sec |
| **`AsyncReliabilityRunner` (Sequential)** | 1 | 8.52 ms | 85.18 µs | ~11,700 tests/sec |
| **`AsyncReliabilityRunner` (Concurrent)** | 10 | 6.91 ms | 69.08 µs | **14,475 tests/sec** |

The asynchronous worker pool scheduling introduces only ~60 µs of worker coordination overhead per test, allowing massive parallel throughput in I/O and network-bound agent environments.
