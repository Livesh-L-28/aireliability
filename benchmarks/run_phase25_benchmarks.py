"""Phase 25 — Control Plane and Intelligent Job Scheduling Benchmarks.

Measures:
1. Enqueue, Dequeue, Peek, Remove operations latency (InMemoryJobQueue)
2. Scheduler dispatch and worker assignment latency
3. WorkerManager capacity acquire/release and selection latency
4. End-to-end execution throughput and scaling across 1, 5, 10, 25, 50 workers
"""

import asyncio
import time

from aireliability import (
    ControlPlane,
    ControlPlaneConfig,
    InMemoryJobQueue,
    JobPriority,
    ScheduledJob,
    TestCase,
    WorkerManager,
)


def benchmark_queue_operations():
    """Benchmark InMemoryJobQueue operations across 1000 items."""

    async def run():
        queue = InMemoryJobQueue()
        iterations = 1000

        jobs = [
            ScheduledJob(
                job_id=f"job_{i}",
                test_case=TestCase(id=f"tc_{i}", name=f"tc_{i}", input=f"data_{i}"),
                priority=JobPriority(i % 4),
            )
            for i in range(iterations)
        ]

        # 1. Enqueue Latency
        t0 = time.perf_counter()
        for j in jobs:
            await queue.enqueue(j)
        enqueue_latency_us = ((time.perf_counter() - t0) / iterations) * 1_000_000.0

        # 2. Peek Latency
        t0 = time.perf_counter()
        for _ in range(iterations):
            await queue.peek()
        peek_latency_us = ((time.perf_counter() - t0) / iterations) * 1_000_000.0

        # 3. Dequeue Latency
        t0 = time.perf_counter()
        for _ in range(iterations):
            await queue.dequeue()
        dequeue_latency_us = ((time.perf_counter() - t0) / iterations) * 1_000_000.0

        print(f"InMemoryJobQueue Enqueue Latency:  {enqueue_latency_us:.2f} µs/op")
        print(f"InMemoryJobQueue Peek Latency:     {peek_latency_us:.2f} µs/op")
        print(f"InMemoryJobQueue Dequeue Latency:  {dequeue_latency_us:.2f} µs/op")
        return {
            "enqueue_us": enqueue_latency_us,
            "peek_us": peek_latency_us,
            "dequeue_us": dequeue_latency_us,
        }

    return asyncio.run(run())


def benchmark_worker_manager_operations():
    """Benchmark WorkerManager selection and capacity acquire/release."""

    async def run():
        iterations = 500
        mgr = WorkerManager(default_capacity=10)

        # Register 50 workers
        for i in range(50):
            await mgr.register_worker(f"worker_{i}", capacity=10)

        # 1. Selection Latency
        t0 = time.perf_counter()
        for _ in range(iterations):
            await mgr.select_best_worker()
        selection_latency_us = ((time.perf_counter() - t0) / iterations) * 1_000_000.0

        # 2. Capacity Acquire & Release Latency
        t0 = time.perf_counter()
        for i in range(iterations):
            w_id = f"worker_{i % 50}"
            await mgr.acquire_capacity(w_id)
            await mgr.release_capacity(w_id)
        capacity_cycle_latency_us = (
            (time.perf_counter() - t0) / iterations
        ) * 1_000_000.0

        print(f"WorkerManager Best-Worker Select:  {selection_latency_us:.2f} µs/op")
        print(
            f"WorkerManager Capacity Acquire+Rel: {capacity_cycle_latency_us:.2f} µs/op"
        )
        return {
            "select_us": selection_latency_us,
            "capacity_us": capacity_cycle_latency_us,
        }

    return asyncio.run(run())


def benchmark_control_plane_scaling():
    """Benchmark end-to-end execution scaling across 1, 5, 10, 25, 50 workers."""

    async def run_for_workers(worker_count: int, test_count: int = 100):
        def fast_agent(inputs: dict) -> dict:
            return {"status": "ok"}

        config = ControlPlaneConfig(
            max_concurrency=worker_count,
            worker_default_capacity=2,
        )
        cp = ControlPlane(agent=fast_agent, config=config)

        test_cases = [
            TestCase(id=f"scale_{i}", name=f"scale_{i}", input={"idx": i})
            for i in range(test_count)
        ]

        t0 = time.perf_counter()
        _ = await cp.execute_execution(test_cases, timeout=30.0)
        duration_s = time.perf_counter() - t0
        throughput = test_count / duration_s

        await cp.stop()
        return duration_s, throughput

    worker_counts = [1, 5, 10, 25, 50]
    results = {}
    print("\nScaling Benchmark (100 jobs per run):")
    for wc in worker_counts:
        duration, throughput = asyncio.run(run_for_workers(wc, test_count=100))
        results[wc] = (duration, throughput)
        print(
            f"  {wc:2d} Workers: {duration * 1000.0:.2f} ms total | "
            f"{throughput:.1f} tests/sec"
        )

    return results


def main():
    print("=" * 60)
    print("Phase 25 — Control Plane and Job Scheduling Benchmarks")
    print("=" * 60)
    print("\n1. Queue Operations Benchmark:")
    benchmark_queue_operations()

    print("\n2. Worker Manager Benchmark:")
    benchmark_worker_manager_operations()

    print("\n3. Control Plane Scaling Benchmark:")
    benchmark_control_plane_scaling()
    print("=" * 60)


if __name__ == "__main__":
    main()
