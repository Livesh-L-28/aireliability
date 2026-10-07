"""Benchmark suite for Deterministic LLM provider and generation throughput."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability_demo.app.llm.deterministic import DeterministicLLM

from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def run_llm_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    """Execute LLM generation benchmarks across multiple payload scales."""
    metrics: list[BenchmarkMetric] = []
    llm = DeterministicLLM()

    # 1. Short Response Generation
    def bench_short() -> None:
        _ = llm.generate("Explain assertions.", scenario="NORMAL")

    m_short = measure_benchmark(
        operation="llm_generate_short",
        target_func=bench_short,
        input_size="short (~50 chars)",
        iterations=config.iterations * 2,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("deterministic_llm"),
        seed=config.seed,
    )
    metrics.append(m_short)

    # 2. Medium Response Generation
    def bench_medium() -> None:
        _ = llm.generate(
            "Explain RAG retrieval and citation validation in AI reliability.",
            scenario="NORMAL",
        )

    m_medium = measure_benchmark(
        operation="llm_generate_medium",
        target_func=bench_medium,
        input_size="medium (~250 chars)",
        iterations=config.iterations * 2,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("deterministic_llm"),
        seed=config.seed,
    )
    metrics.append(m_medium)

    # 3. Long Response Generation
    long_prompt = "Provide a comprehensive audit report detailing multi-tenant policy enforcement, safety controls, regression testing, and prediction forecasting."

    def bench_long() -> None:
        _ = llm.generate(long_prompt, scenario="NORMAL")

    m_long = measure_benchmark(
        operation="llm_generate_long",
        target_func=bench_long,
        input_size="long (~1000 chars)",
        iterations=config.iterations * 2,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("deterministic_llm"),
        seed=config.seed,
    )
    metrics.append(m_long)

    # 4. Response Output Validation Latency
    sample_output = llm.generate(long_prompt, scenario="NORMAL")

    def bench_validation() -> None:
        valid = len(sample_output) > 20 and not sample_output.startswith("ERROR")
        assert valid

    m_val = measure_benchmark(
        operation="llm_output_validation",
        target_func=bench_validation,
        input_size="validation (1000 chars)",
        iterations=config.iterations * 3,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("deterministic_llm"),
        seed=config.seed,
    )
    metrics.append(m_val)

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_llm_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
