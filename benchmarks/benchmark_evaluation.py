"""Benchmark suite for Evaluation Engine across single, batch, semantic, and regression workloads."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.core.models import ExecutionTrace, StepType, TestCase, TraceStep
from aireliability.evaluation import MaxLatency, OutputContains, ToolCalled, ToolOrder
from aireliability.execution.runner import ReliabilityRunner
from aireliability.regression.baseline import BaselineManager
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_dummy_agent() -> tuple[Any, TestCase]:
    tc = TestCase(id="tc_bench", name="benchmark_case", input={"q": "status"})

    def agent(inp: dict) -> dict:
        return {"output": "System operational and healthy", "status": "ok"}

    return agent, tc


def run_evaluation_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    agent, tc = make_dummy_agent()
    evaluators = [
        OutputContains("operational"),
        MaxLatency(500.0),
        ToolCalled("status_check", min_calls=0),
    ]
    runner = ReliabilityRunner(agent=agent, evaluators=evaluators)

    # 1. Single Evaluation
    def bench_single() -> None:
        res = runner.run(tc)
        assert res.passed

    m_single = measure_benchmark(
        operation="evaluation_single",
        target_func=bench_single,
        input_size=1,
        iterations=config.iterations * 3,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("single_evaluation"),
        seed=config.seed,
    )
    metrics.append(m_single)

    # 2. Batch Evaluation - Small (10)
    cases_small = [
        TestCase(id=f"tc_{i}", name=f"case_{i}", input={"q": f"query_{i}"})
        for i in range(config.sizes.SMALL)
    ]

    def bench_batch_small() -> None:
        for c in cases_small:
            _ = runner.run(c)

    m_batch_s = measure_benchmark(
        operation="evaluation_batch_small",
        target_func=bench_batch_small,
        input_size=f"{len(cases_small)} cases",
        iterations=config.iterations,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("batch_evaluation"),
        seed=config.seed,
    )
    metrics.append(m_batch_s)

    # 3. Batch Evaluation - Medium (100)
    cases_med = [
        TestCase(id=f"tc_{i}", name=f"case_{i}", input={"q": f"query_{i}"})
        for i in range(config.sizes.MEDIUM)
    ]

    def bench_batch_medium() -> None:
        for c in cases_med:
            _ = runner.run(c)

    m_batch_m = measure_benchmark(
        operation="evaluation_batch_medium",
        target_func=bench_batch_medium,
        input_size=f"{len(cases_med)} cases",
        iterations=max(3, config.iterations // 2),
        warmup_iterations=1,
        budget=config.budgets.get("batch_evaluation"),
        seed=config.seed,
    )
    metrics.append(m_batch_m)

    # 4. Batch Evaluation - Large (1,000) - only in full mode or scaled in quick/smoke
    cases_large = [
        TestCase(id=f"tc_{i}", name=f"case_{i}", input={"q": f"query_{i}"})
        for i in range(min(1000, config.sizes.LARGE))
    ]

    def bench_batch_large() -> None:
        for c in cases_large:
            _ = runner.run(c)

    m_batch_l = measure_benchmark(
        operation="evaluation_batch_large",
        target_func=bench_batch_large,
        input_size=f"{len(cases_large)} cases",
        iterations=max(2, config.iterations // 4),
        warmup_iterations=1,
        budget=config.budgets.get("batch_evaluation"),
        seed=config.seed,
    )
    metrics.append(m_batch_l)

    # 5. Deterministic Assertion Invariant Checks (Micro-benchmark 10,000 ops)
    trace = ExecutionTrace(
        test_case_id="tc_micro",
        trace_id="tr_micro",
        steps=[
            TraceStep(
                name="init",
                type=StepType.TOOL,
                input={},
                output="ready",
                status="completed",
            ),
            TraceStep(
                name="process",
                type=StepType.TOOL,
                input={},
                output="ok",
                status="completed",
            ),
        ],
        output="Final operation completed verified",
        duration_ms=10.5,
    )
    chk_eval = ToolOrder(["init", "process"])

    def bench_deterministic_eval() -> None:
        for _ in range(100):
            res = chk_eval.evaluate(trace, tc)
            assert res.passed

    m_determ = measure_benchmark(
        operation="evaluation_deterministic_assertion",
        target_func=bench_deterministic_eval,
        input_size="100 assertion evals",
        iterations=config.iterations * 2,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("single_evaluation"),
        seed=config.seed,
    )
    metrics.append(m_determ)

    # 6. Regression Baseline Comparison Evaluation
    from aireliability.core.models import RunResult

    mgr = BaselineManager()
    dummy_tr = ExecutionTrace(test_case_id="t", trace_id="tr")
    base_runs = [
        RunResult(
            test=TestCase(id=f"t_{i}", name=f"t_{i}", input={}),
            trace=dummy_tr,
            passed=True,
        )
        for i in range(config.sizes.MEDIUM)
    ]
    cand_runs = [
        RunResult(
            test=TestCase(id=f"t_{i}", name=f"t_{i}", input={}),
            trace=dummy_tr,
            passed=(i % 10 != 0),
        )
        for i in range(config.sizes.MEDIUM)
    ]
    mgr.create_baseline(base_runs, name="base")

    def bench_regression_cmp() -> None:
        _ = mgr.compare(cand_runs, baseline_name="base")

    m_reg = measure_benchmark(
        operation="evaluation_regression_diff",
        target_func=bench_regression_cmp,
        input_size=f"{len(base_runs)} baseline comparisons",
        iterations=config.iterations * 3,
        warmup_iterations=config.warmup_iterations,
        budget=config.budgets.get("single_evaluation"),
        seed=config.seed,
    )
    metrics.append(m_reg)

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_evaluation_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
