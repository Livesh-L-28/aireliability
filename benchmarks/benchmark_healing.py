"""Benchmark suite for Self-Healing AI Reliability Engine (Phase 37)."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.core.models import FailureReport
from aireliability.failures.taxonomy import FailureCategory
from aireliability.remediation.engine import RemediationEngine
from aireliability.remediation.models import (
    RemediationLifecycleState,
    RepairType,
    RolloutStrategy,
)
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_remediation_failure() -> FailureReport:
    """Generate sample failure report for self-healing tests."""
    return FailureReport(
        failure_id="fail_heal_001",
        trace_id="tr_heal_001",
        category=FailureCategory.TASK,
        message="System prompt lacked safety boundaries for output format",
        evidence={
            "prompt": "Summarize this input",
            "output": "Format error in schema",
            "component": "prompt_generator",
        },
        confidence=0.95,
    )


def run_healing_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    engine = RemediationEngine()
    failure = make_remediation_failure()

    # 1. Remediation Proposal Generation
    def bench_diagnose_and_plan() -> None:
        _ = engine.diagnose_and_plan(
            evidence=failure, explicit_type=RepairType.PROMPT, generate_tests=False
        )

    metrics.append(
        measure_benchmark(
            operation="healing_proposal_generation",
            target_func=bench_diagnose_and_plan,
            input_size="1 failure report prompt repair",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("self_healing_simulation"),
            seed=config.seed,
        )
    )

    proposal = engine.diagnose_and_plan(
        evidence=failure, explicit_type=RepairType.PROMPT, generate_tests=False
    )

    # 2. Simulation & Gate Evaluation
    def bench_simulation() -> None:
        _ = engine.simulate(proposal)

    metrics.append(
        measure_benchmark(
            operation="healing_simulation_and_gates",
            target_func=bench_simulation,
            input_size="RemediationProposal simulation & quality gates",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("self_healing_simulation"),
            seed=config.seed,
        )
    )

    sim_res = engine.simulate(proposal)

    # 3. Gate Checking independently
    def bench_gate_checking() -> None:
        _ = engine.gate_checker.evaluate_gates(proposal, simulation_result=sim_res)

    metrics.append(
        measure_benchmark(
            operation="healing_gate_checking",
            target_func=bench_gate_checking,
            input_size="RemediationProposal gate evaluation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("self_healing_simulation"),
            seed=config.seed,
        )
    )

    # 4. Approval Validation
    def bench_approval() -> None:
        proposal.state = RemediationLifecycleState.SIMULATED
        _ = engine.approval_manager.approve(
            proposal, approver="operator", rationale="Benchmark approval"
        )

    metrics.append(
        measure_benchmark(
            operation="healing_approval_validation",
            target_func=bench_approval,
            input_size="Approval validation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("self_healing_simulation"),
            seed=config.seed,
        )
    )

    # 5. Full Lifecycle (Proposal -> Simulation -> Approval -> Rollout -> Verification -> Promotion)
    def bench_complete_lifecycle() -> None:
        eng = RemediationEngine()
        prop = eng.diagnose_and_plan(
            evidence=failure, explicit_type=RepairType.PROMPT, generate_tests=False
        )
        _ = eng.simulate(prop)
        _ = eng.approve(prop, approver="operator", rationale="Lifecycle approval")
        _ = eng.apply(prop, strategy=RolloutStrategy.DIRECT)
        _ = eng.verify(prop, sample_count=10, remediation_error_rate=0.0)
        _ = eng.promote(prop, actor="operator")

    metrics.append(
        measure_benchmark(
            operation="healing_complete_lifecycle",
            target_func=bench_complete_lifecycle,
            input_size="End-to-end self-healing lifecycle",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("self_healing_simulation"),
            seed=config.seed,
        )
    )

    # 6. Rollback
    def bench_rollback() -> None:
        eng = RemediationEngine()
        prop = eng.diagnose_and_plan(
            evidence=failure, explicit_type=RepairType.PROMPT, generate_tests=False
        )
        _ = eng.simulate(prop)
        _ = eng.approve(prop, approver="operator")
        _ = eng.apply(prop, strategy=RolloutStrategy.DIRECT)
        _ = eng.rollback(prop, reason="Intentional rollback benchmark", actor="system")

    metrics.append(
        measure_benchmark(
            operation="healing_rollback_execution",
            target_func=bench_rollback,
            input_size="Remediation rollback execution",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("self_healing_simulation"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_healing_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
