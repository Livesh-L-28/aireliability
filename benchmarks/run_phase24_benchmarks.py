"""Phase 24 — Storage and Persistence Benchmarks.

Measures:
1. InMemory Storage vs SQLite Storage vs Async SQLite Persistence
2. Latency for save_job, claim_job, save_outcome, query, aggregation, recovery
3. Parallel execution scaling across 1, 5, 10, 25 workers
"""

import asyncio
import time
from datetime import UTC, datetime

from aireliability import (
    AsyncReliabilityRunner,
    InMemoryDistributedStorage,
    JobExecutionOutcome,
    JobStatus,
    PersistentWorkerRecord,
    ReliabilityJob,
    ResultAggregator,
    SQLiteDistributedStorage,
    TestCase,
    WorkerState,
)
from aireliability.core.models import ExecutionTrace, RunResult


def benchmark_storage_operations():
    """Measure single-operation latency across backends (1000 iterations)."""
    iterations = 500

    results = {}

    for backend_name, storage in [
        ("InMemory", InMemoryDistributedStorage()),
        ("SQLite (:memory:)", SQLiteDistributedStorage(":memory:")),
    ]:
        # 1. save_job
        jobs = [
            ReliabilityJob(
                job_id=f"bench_job_{i}",
                execution_id="bench_exec_1",
                test_case=TestCase(id=f"tc_{i}", name=f"tc_{i}", input=f"input_{i}"),
            )
            for i in range(iterations)
        ]
        t0 = time.perf_counter()
        for j in jobs:
            storage.save_job(j)
        save_job_time = (time.perf_counter() - t0) * 1000.0 / iterations

        # 2. claim_job
        t0 = time.perf_counter()
        for i in range(iterations):
            storage.claim_job(f"bench_job_{i}", f"worker_{i % 5}")
        claim_job_time = (time.perf_counter() - t0) * 1000.0 / iterations

        # 3. save_outcome
        outcomes = [
            JobExecutionOutcome(
                job_id=f"bench_job_{i}",
                execution_id="bench_exec_1",
                test_id=f"tc_{i}",
                worker_id=f"worker_{i % 5}",
                status=JobStatus.COMPLETED,
                run_result=RunResult(
                    test=jobs[i].test_case,
                    trace=ExecutionTrace(
                        test_id=f"tc_{i}", input=f"input_{i}", output=f"out_{i}"
                    ),
                    passed=True,
                ),
            )
            for i in range(iterations)
        ]
        t0 = time.perf_counter()
        for out in outcomes:
            storage.save_outcome(out)
        save_outcome_time = (time.perf_counter() - t0) * 1000.0 / iterations

        # 4. query
        t0 = time.perf_counter()
        for _ in range(50):
            storage.list_jobs(execution_id="bench_exec_1")
            storage.list_outcomes(execution_id="bench_exec_1")
        query_time = (time.perf_counter() - t0) * 1000.0 / 50

        # 5. aggregation from storage
        t0 = time.perf_counter()
        for _ in range(50):
            agg = ResultAggregator.from_storage(storage, "bench_exec_1")
            agg.aggregate()
        agg_time = (time.perf_counter() - t0) * 1000.0 / 50

        # 6. recovery
        # Register a stale worker
        stale_worker = PersistentWorkerRecord(
            worker_id="worker_stale_bench",
            execution_id="bench_exec_1",
            state=WorkerState.RUNNING,
            last_heartbeat=datetime.fromtimestamp(0, tz=UTC),
        )
        storage.save_worker(stale_worker)
        stale_job = ReliabilityJob(
            job_id="stale_job_bench",
            execution_id="bench_exec_1",
            test_case=TestCase(id="tc_stale", name="stale", input="in"),
            status=JobStatus.RUNNING,
            assigned_worker_id="worker_stale_bench",
        )
        storage.save_job(stale_job)

        t0 = time.perf_counter()
        for _ in range(50):
            storage.recover_execution("bench_exec_1", stale_timeout_seconds=30.0)
        recovery_time = (time.perf_counter() - t0) * 1000.0 / 50

        results[backend_name] = {
            "save_job_us": save_job_time * 1000.0,
            "claim_job_us": claim_job_time * 1000.0,
            "save_outcome_us": save_outcome_time * 1000.0,
            "query_ms": query_time,
            "agg_ms": agg_time,
            "recovery_ms": recovery_time,
        }

    return results


def benchmark_worker_scaling():
    """Measure parallel execution throughput across worker counts (1, 5, 10, 25)."""
    scaling_results = {}
    test_count = 100

    def mock_agent(x: int) -> int:
        return x * 2

    test_cases = [
        TestCase(id=f"tc_{i}", name=f"test_{i}", input=i) for i in range(test_count)
    ]

    for concurrency in [1, 5, 10, 25]:
        storage = SQLiteDistributedStorage(":memory:")
        runner = AsyncReliabilityRunner(
            agent=mock_agent,
            storage=storage,
            max_concurrency=concurrency,
        )
        t0 = time.perf_counter()
        summary = asyncio.run(runner.execute_many(test_cases))
        total_time_ms = (time.perf_counter() - t0) * 1000.0
        throughput = test_count / (total_time_ms / 1000.0)

        scaling_results[concurrency] = {
            "total_time_ms": round(total_time_ms, 2),
            "throughput_tests_per_sec": round(throughput, 1),
            "all_passed": summary.all_passed,
        }

    return scaling_results


if __name__ == "__main__":
    print("Running Phase 24 Storage Benchmarks...")
    storage_res = benchmark_storage_operations()
    print("Storage Operation Latencies:")
    for backend, metrics in storage_res.items():
        print(f"[{backend}]")
        print(f"  save_job:      {metrics['save_job_us']:.2f} µs")
        print(f"  claim_job:     {metrics['claim_job_us']:.2f} µs")
        print(f"  save_outcome:  {metrics['save_outcome_us']:.2f} µs")
        print(f"  query:         {metrics['query_ms']:.3f} ms")
        print(f"  aggregation:   {metrics['agg_ms']:.3f} ms")
        print(f"  recovery:      {metrics['recovery_ms']:.3f} ms")

    print("\nRunning Phase 24 Worker Scaling Benchmarks (100 tests)...")
    scaling_res = benchmark_worker_scaling()
    for workers, metrics in scaling_res.items():
        print(
            f"Workers: {workers:2d} | "
            f"Duration: {metrics['total_time_ms']:6.2f} ms | "
            f"Throughput: {metrics['throughput_tests_per_sec']:8.1f} tests/sec"
        )
