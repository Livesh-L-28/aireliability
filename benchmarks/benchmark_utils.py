"""High-precision benchmarking utilities, timing instrumentation, and resource profiling."""

from __future__ import annotations

import gc
import os
import platform
import random
import resource
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from benchmarks.benchmark_config import PerformanceBudget


def get_current_rss_mb() -> float:
    """Retrieve resident set size in megabytes."""
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    # Fallback to resource module (macOS reports bytes, Linux reports KB)
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return usage / (1024 * 1024)
    return usage / 1024


@dataclass
class BenchmarkMetric:
    """Structured performance metrics for an evaluated workload."""

    operation: str
    input_size: str | int
    iterations: int
    warmup_iterations: int
    total_duration_ms: float
    average_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    throughput_ops: float
    memory_initial_mb: float
    memory_peak_mb: float
    memory_final_mb: float
    memory_growth_mb: float
    cold_start_ms: float = 0.0
    status: str = "PASS"
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def compute_percentile(sorted_values: list[float], percentile: float) -> float:
    """Calculate percentile from sorted list of numbers."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (percentile / 100.0)
    f = int(k)
    c = f + 1
    if c < len(sorted_values):
        d0 = sorted_values[f] * (c - k)
        d1 = sorted_values[c] * (k - f)
        return d0 + d1
    return sorted_values[-1]


def measure_cold_start(target_func: Callable[[], Any]) -> tuple[float, Any]:
    """Measure exact cold-start execution duration in milliseconds."""
    t0 = time.perf_counter_ns()
    res = target_func()
    dur_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
    return round(dur_ms, 3), res


def measure_benchmark(
    operation: str,
    target_func: Callable[[], Any],
    input_size: str | int,
    iterations: int = 15,
    warmup_iterations: int = 3,
    budget: PerformanceBudget | None = None,
    seed: int = 42,
    details: dict[str, Any] | None = None,
) -> BenchmarkMetric:
    """Run warm benchmark loop with precise timing and memory profiling."""
    random.seed(seed)
    gc.collect()

    # 1. Cold start measurement
    cold_start_t0 = time.perf_counter_ns()
    target_func()
    cold_start_ms = (time.perf_counter_ns() - cold_start_t0) / 1_000_000.0

    # 2. Warmup iterations
    for _ in range(warmup_iterations):
        target_func()

    gc.collect()
    mem_initial = get_current_rss_mb()
    mem_peak = mem_initial

    latencies_ns: list[int] = []

    # 3. Timed steady-state executions
    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        target_func()
        duration_ns = time.perf_counter_ns() - t0
        latencies_ns.append(duration_ns)

        current_mem = get_current_rss_mb()
        if current_mem > mem_peak:
            mem_peak = current_mem

    gc.collect()
    mem_final = get_current_rss_mb()
    mem_growth = max(0.0, mem_final - mem_initial)

    latencies_ms = [ns / 1_000_000.0 for ns in latencies_ns]
    latencies_ms.sort()

    total_duration_ms = sum(latencies_ms)
    avg_latency = total_duration_ms / len(latencies_ms) if latencies_ms else 0.0
    median_latency = compute_percentile(latencies_ms, 50.0)
    p95_latency = compute_percentile(latencies_ms, 95.0)
    p99_latency = compute_percentile(latencies_ms, 99.0)
    min_latency = latencies_ms[0] if latencies_ms else 0.0
    max_latency = latencies_ms[-1] if latencies_ms else 0.0

    throughput = (
        (iterations / (total_duration_ms / 1000.0)) if total_duration_ms > 0 else 0.0
    )

    # Status evaluation against budget
    status = "PASS"
    if budget:
        if (
            p95_latency > budget.max_p95_ms * 1.5
            or throughput < budget.min_throughput_ops * 0.5
        ):
            status = "REGRESSION"
        elif p95_latency > budget.max_p95_ms or throughput < budget.min_throughput_ops:
            status = "WATCH"

    return BenchmarkMetric(
        operation=operation,
        input_size=input_size,
        iterations=iterations,
        warmup_iterations=warmup_iterations,
        total_duration_ms=round(total_duration_ms, 3),
        average_latency_ms=round(avg_latency, 3),
        median_latency_ms=round(median_latency, 3),
        p95_latency_ms=round(p95_latency, 3),
        p99_latency_ms=round(p99_latency, 3),
        min_latency_ms=round(min_latency, 3),
        max_latency_ms=round(max_latency, 3),
        throughput_ops=round(throughput, 1),
        memory_initial_mb=round(mem_initial, 2),
        memory_peak_mb=round(mem_peak, 2),
        memory_final_mb=round(mem_final, 2),
        memory_growth_mb=round(mem_growth, 2),
        cold_start_ms=round(cold_start_ms, 3),
        status=status,
        details=details or {},
    )


def measure_concurrency(
    worker_fn: Callable[[], bool],
    worker_counts: list[int] = (1, 2, 4, 8),
    requests_per_worker: int = 50,
) -> list[dict[str, Any]]:
    """Evaluate multi-worker execution throughput, p95/p99 latency, and error rate."""
    results: list[dict[str, Any]] = []

    for workers in worker_counts:
        latencies_ms: list[float] = []
        errors = 0
        total_requests = workers * requests_per_worker

        def task() -> tuple[float, bool]:
            t0 = time.perf_counter_ns()
            try:
                ok = worker_fn()
                dur_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
                return dur_ms, bool(ok)
            except Exception:
                dur_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
                return dur_ms, False

        t_start = time.perf_counter_ns()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(task) for _ in range(total_requests)]
            for fut in as_completed(futures):
                dur, success = fut.result()
                latencies_ms.append(dur)
                if not success:
                    errors += 1

        total_wall_ms = (time.perf_counter_ns() - t_start) / 1_000_000.0
        latencies_ms.sort()

        throughput = (
            (total_requests / (total_wall_ms / 1000.0)) if total_wall_ms > 0 else 0.0
        )
        p50 = compute_percentile(latencies_ms, 50.0)
        p95 = compute_percentile(latencies_ms, 95.0)
        p99 = compute_percentile(latencies_ms, 99.0)

        results.append(
            {
                "workers": workers,
                "total_requests": total_requests,
                "wall_time_ms": round(total_wall_ms, 2),
                "throughput_ops": round(throughput, 1),
                "p50_ms": round(p50, 3),
                "p95_ms": round(p95, 3),
                "p99_ms": round(p99, 3),
                "errors": errors,
                "error_rate": round(errors / total_requests, 4),
            }
        )

    return results
