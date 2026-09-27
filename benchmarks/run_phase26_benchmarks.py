"""Phase 26 — Fault Tolerance, Resilience & Self-Healing Benchmarks.

Measures:
1. Failure classification overhead
2. Resilient retry delay calculation & jitter
3. CircuitBreaker can_execute, record_success, and record_failure overhead
4. Bulkhead concurrency acquire and release latency
5. WorkerHealthManager record_failure and record_success throughput
6. Baseline vs. Resilience-Enabled Execution Overhead
"""

import asyncio
import statistics
import time

from aireliability import (
    Bulkhead,
    CircuitBreaker,
    ControlPlane,
    ControlPlaneConfig,
    FailureClassifier,
    ResilienceManager,
    TestCase,
    WorkerHealthManager,
)


def benchmark_failure_classification():
    """Benchmark raw exception to DetailedFailureRecord classification."""
    classifier = FailureClassifier()
    iterations = 2000
    latencies_us = []

    test_err = TimeoutError("Provider 504 Gateway Timeout while calling LLM")

    for i in range(iterations):
        t0 = time.perf_counter()
        classifier.classify_error(
            test_err,
            execution_id=f"exec-{i}",
            job_id=f"job-{i}",
            metadata={"key": "test_value"},
        )
        t1 = time.perf_counter()
        latencies_us.append((t1 - t0) * 1_000_000.0)

    mean_us = statistics.mean(latencies_us)
    median_us = statistics.median(latencies_us)
    min_us = min(latencies_us)
    max_us = max(latencies_us)
    throughput = iterations / (sum(latencies_us) / 1_000_000.0)

    print("\n--- Failure Classifier Benchmark ---")
    print(f"Iterations: {iterations}")
    print(f"Mean:       {mean_us:.2f} µs")
    print(f"Median:     {median_us:.2f} µs")
    print(f"Min:        {min_us:.2f} µs")
    print(f"Max:        {max_us:.2f} µs")
    print(f"Throughput: {throughput:,.0f} classifications/sec")


def benchmark_circuit_breaker():
    """Benchmark CircuitBreaker permission check and state update."""

    async def run():
        cb = CircuitBreaker(failure_threshold=100_000)
        iterations = 5000
        latencies_us = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            await cb.can_execute()
            await cb.record_success()
            t1 = time.perf_counter()
            latencies_us.append((t1 - t0) * 1_000_000.0)

        mean_us = statistics.mean(latencies_us)
        median_us = statistics.median(latencies_us)
        min_us = min(latencies_us)
        max_us = max(latencies_us)
        throughput = iterations / (sum(latencies_us) / 1_000_000.0)

        print("\n--- Circuit Breaker Benchmark ---")
        print(f"Iterations: {iterations}")
        print(f"Mean:       {mean_us:.2f} µs")
        print(f"Median:     {median_us:.2f} µs")
        print(f"Min:        {min_us:.2f} µs")
        print(f"Max:        {max_us:.2f} µs")
        print(f"Throughput: {throughput:,.0f} ops/sec")

    asyncio.run(run())


def benchmark_bulkhead():
    """Benchmark Bulkhead acquire and release cycle."""

    async def run():
        bulkhead = Bulkhead(default_limit=100)
        iterations = 5000
        latencies_us = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            async with bulkhead.acquire("provider:default"):
                pass
            t1 = time.perf_counter()
            latencies_us.append((t1 - t0) * 1_000_000.0)

        mean_us = statistics.mean(latencies_us)
        median_us = statistics.median(latencies_us)
        min_us = min(latencies_us)
        max_us = max(latencies_us)
        throughput = iterations / (sum(latencies_us) / 1_000_000.0)

        print("\n--- Bulkhead Isolation Benchmark ---")
        print(f"Iterations: {iterations}")
        print(f"Mean:       {mean_us:.2f} µs")
        print(f"Median:     {median_us:.2f} µs")
        print(f"Min:        {min_us:.2f} µs")
        print(f"Max:        {max_us:.2f} µs")
        print(f"Throughput: {throughput:,.0f} acquisitions/sec")

    asyncio.run(run())


def benchmark_worker_health():
    """Benchmark WorkerHealthManager failure recording and quarantine evaluation."""

    async def run():
        whm = WorkerHealthManager(quarantine_threshold=5000)
        iterations = 3000
        latencies_us = []

        for i in range(iterations):
            worker_id = f"w-{i % 5}"
            t0 = time.perf_counter()
            await whm.record_execution_failure(worker_id, "transient error")
            t1 = time.perf_counter()
            latencies_us.append((t1 - t0) * 1_000_000.0)

        mean_us = statistics.mean(latencies_us)
        median_us = statistics.median(latencies_us)
        min_us = min(latencies_us)
        max_us = max(latencies_us)
        throughput = iterations / (sum(latencies_us) / 1_000_000.0)

        print("\n--- Worker Health Manager Benchmark ---")
        print(f"Iterations: {iterations}")
        print(f"Mean:       {mean_us:.2f} µs")
        print(f"Median:     {median_us:.2f} µs")
        print(f"Min:        {min_us:.2f} µs")
        print(f"Max:        {max_us:.2f} µs")
        print(f"Throughput: {throughput:,.0f} health_updates/sec")

    asyncio.run(run())


def benchmark_baseline_vs_resilience():
    """Compare baseline execution with resilience-enabled execution."""

    async def run():
        cases = [
            TestCase(id=f"tc_{i}", name=f"tc_{i}", input={"text": f"data_{i}"})
            for i in range(50)
        ]

        def fast_agent(inp: dict):
            return {"output": "ok"}

        # 1. Baseline Run (standard ControlPlane)
        cp_baseline = ControlPlane(
            agent=fast_agent,
            config=ControlPlaneConfig(max_concurrency=5),
        )

        t0 = time.perf_counter()
        await cp_baseline.execute_execution(cases, timeout=15.0)
        baseline_time_ms = (time.perf_counter() - t0) * 1000.0
        await cp_baseline.stop()

        # 2. Resilience-Enabled Run
        resilience = ResilienceManager()
        cp_resilient = ControlPlane(
            agent=fast_agent,
            config=ControlPlaneConfig(max_concurrency=5),
            resilience_manager=resilience,
        )

        t0 = time.perf_counter()
        await cp_resilient.execute_execution(cases, timeout=15.0)
        resilient_time_ms = (time.perf_counter() - t0) * 1000.0
        await cp_resilient.stop()

        overhead_pct = (
            (resilient_time_ms - baseline_time_ms) / baseline_time_ms
        ) * 100.0

        print("\n--- Baseline vs. Resilience-Enabled Overhead (50 jobs) ---")
        print(f"Baseline Execution:      {baseline_time_ms:.2f} ms")
        print(f"Resilient Execution:     {resilient_time_ms:.2f} ms")
        print(f"Resilience Overhead:     {overhead_pct:+.2f}%")

    asyncio.run(run())


if __name__ == "__main__":
    print("=" * 65)
    print("AI Reliability Engine — Phase 26 Resilience Performance Benchmarks")
    print("=" * 65)
    benchmark_failure_classification()
    benchmark_circuit_breaker()
    benchmark_bulkhead()
    benchmark_worker_health()
    benchmark_baseline_vs_resilience()
    print("\nBenchmark completed successfully.")
