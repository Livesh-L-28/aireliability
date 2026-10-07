"""Quality and safety evaluation gates for simulated remediation proposals."""

from __future__ import annotations

from typing import Any

from aireliability.remediation.models import (
    GateEvaluationResult,
    RemediationProposal,
    SimulationResult,
)


class RemediationGateChecker:
    """Evaluates simulation outcomes against strict reliability and safety gates."""

    def __init__(
        self,
        min_recovery_rate: float = 0.8,
        max_allowed_regressions: int = 0,
        max_latency_overhead_percent: float = 25.0,
    ) -> None:
        self.min_recovery_rate = min_recovery_rate
        self.max_allowed_regressions = max_allowed_regressions
        self.max_latency_overhead_percent = max_latency_overhead_percent

    def evaluate_gates(
        self,
        proposal: RemediationProposal,
        simulation_result: SimulationResult | None = None,
    ) -> GateEvaluationResult:
        """Check all required gates for a proposed remediation."""
        sim = simulation_result or proposal.simulation
        if not sim:
            return GateEvaluationResult(
                gates_passed=False,
                zero_regression_passed=False,
                recovery_rate_passed=False,
                safety_passed=False,
                latency_passed=False,
                failed_gate_reasons=["No simulation result found for proposal."],
            )

        failed_reasons: list[str] = []

        # 1. Zero regression gate
        zero_reg_passed = sim.regressions_count <= self.max_allowed_regressions
        if not zero_reg_passed:
            failed_reasons.append(
                f"Regression gate failed: {sim.regressions_count} regressions detected (max allowed: {self.max_allowed_regressions})."
            )

        # 2. Recovery rate gate
        rec_passed = sim.failure_recovery_rate >= self.min_recovery_rate
        if not rec_passed:
            failed_reasons.append(
                f"Recovery rate gate failed: achieved {sim.failure_recovery_rate:.1%}, required {self.min_recovery_rate:.1%}."
            )

        # 3. Safety gate
        safety_passed = sim.safety_violations_count == 0
        if not safety_passed:
            failed_reasons.append(
                f"Safety gate failed: {sim.safety_violations_count} safety/security violations detected."
            )

        # 4. Latency gate
        latency_passed = (
            sim.latency_overhead_percent <= self.max_latency_overhead_percent
        )
        if not latency_passed:
            failed_reasons.append(
                f"Latency gate failed: {sim.latency_overhead_percent:.1f}% overhead exceeds {self.max_latency_overhead_percent:.1f}% limit."
            )

        all_passed = zero_reg_passed and rec_passed and safety_passed and latency_passed

        metrics_summary: dict[str, Any] = {
            "recovery_rate": sim.failure_recovery_rate,
            "regressions_count": sim.regressions_count,
            "safety_violations_count": sim.safety_violations_count,
            "latency_overhead_percent": sim.latency_overhead_percent,
        }

        gate_result = GateEvaluationResult(
            gates_passed=all_passed,
            zero_regression_passed=zero_reg_passed,
            recovery_rate_passed=rec_passed,
            safety_passed=safety_passed,
            latency_passed=latency_passed,
            failed_gate_reasons=failed_reasons,
            metrics_summary=metrics_summary,
        )

        proposal.gate_evaluation = gate_result
        return gate_result
