"""Phase 14 Real-World Reliability Benchmark Runner.

Executes and verifies:
1. Scenario A: Tool Ordering (get_order -> refund_order -> cancel_order)
   Detects: FailureCategory.TOOL, FailureType.WRONG_ORDER
2. Scenario B: Wrong Tool (get_order vs delete_order)
   Detects: FailureCategory.TOOL, FailureType.WRONG_TOOL
3. Scenario C: Wrong Tool Arguments (refund_order(order_id="123") vs 456)
   Detects: FailureCategory.TOOL, FailureType.WRONG_ARGUMENT
4. Scenario D: Missing Required Tool (omitting refund_order)
   Detects: FailureCategory.TOOL, FailureType.WRONG_TOOL
5. Scenario E: Output Regression (refund completed vs cancelled)
   Detects: FailureCategory.TASK, FailureType.TASK_INCORRECT
6. Scenario F: Latency Regression (100 ms baseline vs 500 ms current)
   Detects: FailureCategory.PERFORMANCE, FailureType.LATENCY
7. Full Regression Lifecycle (Faulty -> Fix -> Reintroduce -> REGRESSION)
8. Baseline Classification States (REGRESSION, KNOWN_FAILURE, FIXED, PASSING)
9. Failure Traceability Chain (RegressionTest -> FailureReport -> Trace -> TestCase)
10. Execution Overhead Measurements (Mean, Median, Min, Max over repeated local runs)
"""

import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure workspace root and src in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    RunResult,
    TestCase,
)
from aireliability.evaluation import MaxLatency
from aireliability.execution.runner import ReliabilityRunner
from aireliability.failures.taxonomy import FailureCategory, FailureType
from aireliability.regression.baseline import (
    BaselineManager,
    ComparisonStatus,
)
from aireliability.regression.generator import RegressionGenerator
from benchmarks.scenarios.latency_regression import (
    agent_f_faulty,
    agent_f_nominal,
    get_scenario_f,
)
from benchmarks.scenarios.missing_tool import (
    agent_d_faulty,
    agent_d_nominal,
    get_scenario_d,
)
from benchmarks.scenarios.output_regression import (
    agent_e_faulty,
    agent_e_nominal,
    get_scenario_e,
)
from benchmarks.scenarios.tool_order import (
    agent_a_faulty,
    agent_a_nominal,
    get_scenario_a,
)
from benchmarks.scenarios.wrong_arguments import (
    agent_c_faulty,
    agent_c_nominal,
    get_scenario_c,
)
from benchmarks.scenarios.wrong_tool import (
    agent_b_faulty,
    agent_b_nominal,
    get_scenario_b,
)


class SimulatedLatencyAdapter:
    """Deterministic latency adapter for benchmarks."""

    def __init__(self, latency_ms: float) -> None:
        self.latency_ms = latency_ms

    def execute(self, agent: Any, test_case: TestCase) -> ExecutionTrace:
        start = datetime.now(UTC)
        end = start + timedelta(milliseconds=self.latency_ms)
        output = agent(test_case.input) if callable(agent) else "ok"
        return ExecutionTrace(
            test_id=test_case.id,
            input=test_case.input,
            output=output,
            status=ExecutionStatus.COMPLETED,
            started_at=start,
            completed_at=end,
            latency_ms=self.latency_ms,
        )


def run_scenario_benchmarks() -> list[dict[str, Any]]:
    """Run all 6 scenarios and return empirical detection metrics."""
    scenarios_data = [
        {
            "id": "Scenario A",
            "name": "Tool Ordering",
            "setup": get_scenario_a,
            "nominal_fn": agent_a_nominal,
            "faulty_fn": agent_a_faulty,
            "expected_cat": FailureCategory.TOOL.value,
            "expected_type": FailureType.WRONG_ORDER.value,
        },
        {
            "id": "Scenario B",
            "name": "Wrong Tool",
            "setup": get_scenario_b,
            "nominal_fn": agent_b_nominal,
            "faulty_fn": agent_b_faulty,
            "expected_cat": FailureCategory.TOOL.value,
            "expected_type": FailureType.WRONG_TOOL.value,
        },
        {
            "id": "Scenario C",
            "name": "Wrong Tool Arguments",
            "setup": get_scenario_c,
            "nominal_fn": agent_c_nominal,
            "faulty_fn": agent_c_faulty,
            "expected_cat": FailureCategory.TOOL.value,
            "expected_type": FailureType.WRONG_ARGUMENT.value,
        },
        {
            "id": "Scenario D",
            "name": "Missing Required Tool",
            "setup": get_scenario_d,
            "nominal_fn": agent_d_nominal,
            "faulty_fn": agent_d_faulty,
            "expected_cat": FailureCategory.TOOL.value,
            "expected_type": FailureType.WRONG_TOOL.value,
        },
        {
            "id": "Scenario E",
            "name": "Output Regression",
            "setup": get_scenario_e,
            "nominal_fn": agent_e_nominal,
            "faulty_fn": agent_e_faulty,
            "expected_cat": FailureCategory.TASK.value,
            "expected_type": FailureType.TASK_INCORRECT.value,
        },
        {
            "id": "Scenario F",
            "name": "Latency Regression",
            "setup": get_scenario_f,
            "nominal_fn": agent_f_nominal,
            "faulty_fn": agent_f_faulty,
            "expected_cat": FailureCategory.PERFORMANCE.value,
            "expected_type": FailureType.LATENCY.value,
            "is_latency": True,
        },
    ]

    results: list[dict[str, Any]] = []

    for sc in scenarios_data:
        tc, evals, nom_steps, flt_steps = sc["setup"]()
        generator = RegressionGenerator()
        baseline_mgr = BaselineManager()

        if sc.get("is_latency"):
            runner_nominal = ReliabilityRunner(
                agent=sc["nominal_fn"],
                adapter=SimulatedLatencyAdapter(100.0),
                evaluators=evals,
            )
            runner_faulty = ReliabilityRunner(
                agent=sc["faulty_fn"],
                adapter=SimulatedLatencyAdapter(500.0),
                evaluators=evals,
            )
            nom_res = runner_nominal.run(tc)
            flt_res = runner_faulty.run(tc)
        else:
            runner_nominal = ReliabilityRunner(agent=sc["nominal_fn"], evaluators=evals)
            runner_faulty = ReliabilityRunner(agent=sc["faulty_fn"], evaluators=evals)
            nom_res = runner_nominal.run(tc, steps=nom_steps)
            flt_res = runner_faulty.run(tc, steps=flt_steps)

        # Baseline snapshot with passing nominal run
        baseline_mgr.create_baseline([nom_res], name="reference")

        # Verify failure detection
        detected_categories = [f.category for f in flt_res.failures]
        detected_types = [f.type for f in flt_res.failures]
        failure_detected = (
            sc["expected_cat"] in detected_categories
            and sc["expected_type"] in detected_types
        )

        # Generate regression test from primary failure
        primary_failure = flt_res.failures[0] if flt_res.failures else None
        regression_generated = False
        re_detected = False

        if primary_failure:
            reg_test = generator.generate(primary_failure, tc)
            regression_generated = (
                reg_test.source_failure_id == primary_failure.failure_id
            )

            # Re-running faulty logic on synthesized regression test
            if sc.get("is_latency"):
                re_run_res = runner_faulty.run(reg_test.test_case)
            else:
                re_run_res = runner_faulty.run(reg_test.test_case, steps=flt_steps)

            summary = baseline_mgr.compare([re_run_res], baseline_name="reference")
            re_detected = summary.has_regressions

        results.append(
            {
                "id": sc["id"],
                "scenario": sc["name"],
                "nominal_passed": nom_res.passed,
                "expected_category": sc["expected_cat"],
                "expected_type": sc["expected_type"],
                "detected": failure_detected,
                "detected_types": detected_types,
                "regression_generated": regression_generated,
                "regression_re_detected": re_detected,
            }
        )

    return results


def measure_detailed_overhead(iterations: int = 1_000) -> dict[str, Any]:
    """Measure exact overhead: Agent execution only vs Agent + aireliability."""
    from benchmarks.scenarios.tool_order import (
        agent_a_nominal,
        get_scenario_a,
    )

    tc, evals, nominal_steps, _ = get_scenario_a()
    payload = tc.input
    runner = ReliabilityRunner(agent=agent_a_nominal, evaluators=evals)

    # 1. Measure raw agent execution time (microseconds)
    raw_times_us: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = agent_a_nominal(payload)
        t1 = time.perf_counter()
        raw_times_us.append((t1 - t0) * 1_000_000)

    # 2. Measure wrapped execution time (agent + runner + trace + evaluation)
    wrapped_times_us: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = runner.run(tc, steps=nominal_steps)
        t1 = time.perf_counter()
        wrapped_times_us.append((t1 - t0) * 1_000_000)

    # 3. Calculate added overhead per iteration
    overhead_us = [w - r for w, r in zip(wrapped_times_us, raw_times_us, strict=True)]

    return {
        "iterations": iterations,
        "raw_agent_us": {
            "mean": round(statistics.mean(raw_times_us), 3),
            "median": round(statistics.median(raw_times_us), 3),
            "min": round(min(raw_times_us), 3),
            "max": round(max(raw_times_us), 3),
        },
        "with_aireliability_us": {
            "mean": round(statistics.mean(wrapped_times_us), 3),
            "median": round(statistics.median(wrapped_times_us), 3),
            "min": round(min(wrapped_times_us), 3),
            "max": round(max(wrapped_times_us), 3),
        },
        "added_overhead_us": {
            "mean": round(statistics.mean(overhead_us), 3),
            "median": round(statistics.median(overhead_us), 3),
            "min": round(min(overhead_us), 3),
            "max": round(max(overhead_us), 3),
        },
    }


def verify_baseline_classification_states() -> dict[str, bool]:
    """Verify all four baseline comparison states."""
    mgr = BaselineManager()
    tc_reg = TestCase(id="tc_reg", name="test_regression", input="in")
    tc_known = TestCase(id="tc_known", name="test_known_fail", input="in")
    tc_fixed = TestCase(id="tc_fixed", name="test_fixed", input="in")
    tc_pass = TestCase(id="tc_pass", name="test_passing", input="in")

    # Baseline:
    # tc_reg was True
    # tc_known was False
    # tc_fixed was False
    # tc_pass was True
    res_b = [
        RunResult(
            test=tc_reg,
            trace=ExecutionTrace(test_id=tc_reg.id),
            evaluations=[],
            failures=[],
            passed=True,
        ),
        RunResult(
            test=tc_known,
            trace=ExecutionTrace(test_id=tc_known.id),
            evaluations=[],
            failures=[],
            passed=False,
        ),
        RunResult(
            test=tc_fixed,
            trace=ExecutionTrace(test_id=tc_fixed.id),
            evaluations=[],
            failures=[],
            passed=False,
        ),
        RunResult(
            test=tc_pass,
            trace=ExecutionTrace(test_id=tc_pass.id),
            evaluations=[],
            failures=[],
            passed=True,
        ),
    ]
    mgr.create_baseline(res_b, name="b_suite")

    # Current runs:
    res_c = [
        RunResult(
            test=tc_reg,
            trace=ExecutionTrace(test_id=tc_reg.id),
            evaluations=[],
            failures=[],
            passed=False,
        ),
        RunResult(
            test=tc_known,
            trace=ExecutionTrace(test_id=tc_known.id),
            evaluations=[],
            failures=[],
            passed=False,
        ),
        RunResult(
            test=tc_fixed,
            trace=ExecutionTrace(test_id=tc_fixed.id),
            evaluations=[],
            failures=[],
            passed=True,
        ),
        RunResult(
            test=tc_pass,
            trace=ExecutionTrace(test_id=tc_pass.id),
            evaluations=[],
            failures=[],
            passed=True,
        ),
    ]
    summary = mgr.compare(res_c, baseline_name="b_suite")

    return {
        "regression_verified": len(summary.regressions) == 1
        and summary.regressions[0].status == ComparisonStatus.REGRESSION,
        "known_failure_verified": len(summary.known_failures) == 1
        and summary.known_failures[0].status == ComparisonStatus.KNOWN_FAILURE,
        "fixed_verified": len(summary.fixed) == 1
        and summary.fixed[0].status == ComparisonStatus.FIXED,
        "passing_verified": len(summary.passing) == 1
        and summary.passing[0].status == ComparisonStatus.PASSING,
    }


def verify_traceability_chain() -> dict[str, str]:
    """Verify complete audit trail linking RegressionTest to TestCase."""
    tc = TestCase(id="tc_root", name="test_traceability_demo", input="123")
    runner = ReliabilityRunner(
        agent=lambda _: "delayed",
        evaluators=[MaxLatency(5.0)],
        adapter=SimulatedLatencyAdapter(20.0),
    )
    run_res = runner.run(tc)
    failure = run_res.failures[0]

    generator = RegressionGenerator()
    reg_test = generator.generate(failure, tc)

    return {
        "regression_test_id": reg_test.id,
        "source_failure_id": reg_test.source_failure_id,
        "trace_id": failure.trace_id,
        "originating_test_id": run_res.trace.test_id or tc.id,
        "chain_intact": str(
            reg_test.source_failure_id == failure.failure_id
            and failure.trace_id == run_res.trace.trace_id
            and run_res.trace.test_id == tc.id
        ),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 14 Real-World Reliability Benchmark Runner"
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run lightweight smoke benchmark with 100 iterations instead of 1,000",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Overhead measurement iterations (default: 1000, or 100 if --smoke)",
    )
    args = parser.parse_args()

    num_iterations = 100 if args.smoke else (args.iterations or 1_000)
    mode_str = "Smoke (CI)" if args.smoke else "Full Benchmark"

    print("=" * 70)
    print("AI Reliability Engine: Phase 14 Real-World Reliability Benchmark")
    print(f"Mode: {mode_str} ({num_iterations} iterations)")
    print("=" * 70)

    print("\n1. Running Scenario Benchmarks (A through F)...")
    scenarios_results = run_scenario_benchmarks()
    for s in scenarios_results:
        status_sym = "✓" if s["detected"] and s["regression_re_detected"] else "✗"
        print(
            f"  {status_sym} [{s['id']}] {s['scenario']}: "
            f"Detected={s['detected']} ({s['detected_types']}), "
            f"Regression Generated={s['regression_generated']}, "
            f"Re-detected={s['regression_re_detected']}"
        )

    print("\n2. Verifying Baseline Classification States...")
    baseline_states = verify_baseline_classification_states()
    for state_name, passed in baseline_states.items():
        print(f"  ✓ {state_name}: {passed}")

    print("\n3. Verifying Audit Traceability Chain...")
    traceability = verify_traceability_chain()
    print(f"  ✓ Chain Intact: {traceability['chain_intact']}")
    print(
        f"    {traceability['regression_test_id']} -> "
        f"{traceability['source_failure_id']} -> "
        f"{traceability['trace_id']} -> "
        f"{traceability['originating_test_id']}"
    )

    print(f"\n4. Measuring Execution Overhead ({num_iterations} runs)...")
    overhead_metrics = measure_detailed_overhead(num_iterations)
    raw_m = overhead_metrics["raw_agent_us"]["mean"]
    raw_med = overhead_metrics["raw_agent_us"]["median"]
    print(f"  Raw Agent Execution:       {raw_m} µs (median: {raw_med} µs)")

    wr_m = overhead_metrics["with_aireliability_us"]["mean"]
    wr_med = overhead_metrics["with_aireliability_us"]["median"]
    print(f"  With aireliability:        {wr_m} µs (median: {wr_med} µs)")

    ov_m = overhead_metrics["added_overhead_us"]["mean"]
    ov_min = overhead_metrics["added_overhead_us"]["min"]
    ov_max = overhead_metrics["added_overhead_us"]["max"]
    print(
        f"  Added Engine Overhead:     {ov_m} µs (min: {ov_min} µs, max: {ov_max} µs)"
    )

    # Save complete empirical report to json
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "system": {
            "os": f"{platform.system()} {platform.release()}",
            "arch": platform.machine(),
            "python": platform.python_version(),
        },
        "scenarios": scenarios_results,
        "baseline_states": baseline_states,
        "traceability": traceability,
        "overhead": overhead_metrics,
    }

    report_path = Path(__file__).parent / "phase14_results.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved empirical report to {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
