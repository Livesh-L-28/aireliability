"""Benchmark suite for Policy Engine (Phase 44) across rule scales and priority precedence."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.policy.engine import PolicyEngine
from aireliability.policy.models import (
    PolicyAction,
    PolicyAudit,
    PolicyCondition,
    PolicyDecision,
    PolicyOperator,
    PolicyPriority,
    PolicyRule,
    PolicyScope,
    ReliabilityPolicy,
)
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_policy_with_rules(rule_count: int) -> ReliabilityPolicy:
    """Generate synthetic policy containing N prioritized rules."""
    priorities = [
        PolicyPriority.SECURITY,
        PolicyPriority.SAFETY,
        PolicyPriority.TENANT_ISOLATION,
        PolicyPriority.AUTHORIZATION,
        PolicyPriority.COMPLIANCE,
        PolicyPriority.RELIABILITY,
        PolicyPriority.PERFORMANCE,
        PolicyPriority.COST,
    ]
    rules: list[PolicyRule] = []
    for i in range(rule_count):
        p = priorities[i % len(priorities)]
        rules.append(
            PolicyRule(
                rule_id=f"rule_{i:05d}",
                name=f"Policy Rule {i} - {p.value}",
                description=f"Synthetic rule for invariant check {i}",
                priority=p,
                is_hard_constraint=(
                    p in (PolicyPriority.SECURITY, PolicyPriority.SAFETY)
                ),
                conditions=[
                    PolicyCondition(
                        field=f"metric_{i % 20}",
                        operator=PolicyOperator.LT,
                        target_value=0.50,
                    )
                ],
                action=PolicyAction(
                    decision=PolicyDecision.BLOCK
                    if p in (PolicyPriority.SECURITY, PolicyPriority.SAFETY)
                    else PolicyDecision.WARN,
                    message=f"Threshold breached for metric_{i % 20}",
                ),
            )
        )
    return ReliabilityPolicy(
        name=f"Benchmark Policy ({rule_count} rules)",
        version="1.0.0",
        scope=PolicyScope.GLOBAL,
        rules=rules,
    )


def run_policy_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    engine = PolicyEngine()

    policy_10 = make_policy_with_rules(config.sizes.SMALL)
    policy_100 = make_policy_with_rules(config.sizes.MEDIUM)
    policy_1000 = make_policy_with_rules(min(1000, config.sizes.LARGE))

    context_clean = {f"metric_{i}": 0.85 for i in range(20)}
    context_violation = {f"metric_{i}": 0.40 for i in range(20)}

    # 1. Policy Loading / Instantiation
    def bench_policy_loading() -> None:
        _ = make_policy_with_rules(100)

    metrics.append(
        measure_benchmark(
            operation="policy_loading_100_rules",
            target_func=bench_policy_loading,
            input_size="100 rules construction",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("policy_rule_evaluation"),
            seed=config.seed,
        )
    )

    # 2. Rule Evaluation - 10 Rules
    def bench_eval_10() -> None:
        _ = engine.evaluate(context=context_clean, policy=policy_10)

    metrics.append(
        measure_benchmark(
            operation="policy_evaluation_10_rules",
            target_func=bench_eval_10,
            input_size="10 rules context evaluation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("policy_rule_evaluation"),
            seed=config.seed,
        )
    )

    # 3. Rule Evaluation - 100 Rules
    def bench_eval_100() -> None:
        _ = engine.evaluate(context=context_clean, policy=policy_100)

    metrics.append(
        measure_benchmark(
            operation="policy_evaluation_100_rules",
            target_func=bench_eval_100,
            input_size="100 rules context evaluation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("policy_rule_evaluation"),
            seed=config.seed,
        )
    )

    # 4. Rule Evaluation - 1,000 Rules
    def bench_eval_1000() -> None:
        _ = engine.evaluate(context=context_clean, policy=policy_1000)

    metrics.append(
        measure_benchmark(
            operation="policy_evaluation_1000_rules",
            target_func=bench_eval_1000,
            input_size="1,000 rules context evaluation",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("policy_rule_evaluation"),
            seed=config.seed,
        )
    )

    # 5. Priority Precedence Resolution (with violations triggered)
    def bench_priority_resolution() -> None:
        eval_res = engine.evaluate(context=context_violation, policy=policy_100)
        assert eval_res.decision == PolicyDecision.BLOCK
        assert eval_res.effective_priority in (
            PolicyPriority.SECURITY,
            PolicyPriority.SAFETY,
        )

    metrics.append(
        measure_benchmark(
            operation="policy_priority_resolution_enforcement",
            target_func=bench_priority_resolution,
            input_size="100 rules violation precedence check",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("policy_rule_evaluation"),
            seed=config.seed,
        )
    )

    # 6. Explanation & Fingerprinting
    eval_sample = engine.evaluate(context=context_violation, policy=policy_100)

    def bench_explanation_and_fingerprint() -> None:
        _ = eval_sample.fingerprint()
        _ = eval_sample.explanation

    metrics.append(
        measure_benchmark(
            operation="policy_fingerprint_and_explanation",
            target_func=bench_explanation_and_fingerprint,
            input_size="PolicyEvaluation fingerprinting",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("policy_rule_evaluation"),
            seed=config.seed,
        )
    )

    # 7. Policy Audit Event Generation
    def bench_audit_event() -> None:
        _ = PolicyAudit(
            policy_id=eval_sample.policy_id,
            policy_version=eval_sample.policy_version,
            decision=eval_sample.decision,
            actor="benchmark_runner",
            tenant_id="tenant_perf",
            evidence={"violations_count": len(eval_sample.violations)},
        )

    metrics.append(
        measure_benchmark(
            operation="policy_audit_generation",
            target_func=bench_audit_event,
            input_size="PolicyAudit record synthesis",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("policy_rule_evaluation"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_policy_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
