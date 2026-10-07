"""Strict reliability, safety, security, and zero-regression quality gate checker."""

from __future__ import annotations

import logging

from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationPolicy,
)

logger = logging.getLogger(__name__)


class OptimizationGateChecker:
    """Verifies that an optimization candidate strictly satisfies non-negotiable reliability gates."""

    def __init__(
        self,
        default_required_safety: float = 0.95,
        default_required_security: float = 0.95,
        default_required_quality: float = 0.80,
    ) -> None:
        self.default_required_safety = default_required_safety
        self.default_required_security = default_required_security
        self.default_required_quality = default_required_quality

    def check_gates(
        self,
        candidate: OptimizationCandidate,
        policy: OptimizationPolicy,
        baseline_metrics: dict[str, float] | None = None,
    ) -> tuple[bool, list[str]]:
        """Evaluate candidate metrics against reliability gates.

        Returns (passed, list_of_failure_reasons).
        """
        failures: list[str] = []
        metrics = candidate.objective_values
        base = baseline_metrics or {}

        # 1. Hard Safety Gate
        safety_val = metrics.get("safety", candidate.metadata.get("safety", 1.0))
        req_safety = policy.required_safety or self.default_required_safety
        if safety_val < req_safety:
            failures.append(
                f"Safety gate failed: safety score {safety_val:.4f} < required threshold {req_safety:.4f}"
            )

        # 2. Hard Security Gate
        sec_val = metrics.get("security", candidate.metadata.get("security", 1.0))
        req_sec = policy.required_security or self.default_required_security
        if sec_val < req_sec:
            failures.append(
                f"Security gate failed: security score {sec_val:.4f} < required threshold {req_sec:.4f}"
            )

        # 3. Quality Gate
        qual_val = metrics.get("quality", candidate.metadata.get("quality", 1.0))
        req_qual = policy.required_quality or self.default_required_quality
        if qual_val < req_qual:
            failures.append(
                f"Quality gate failed: quality score {qual_val:.4f} < required threshold {req_qual:.4f}"
            )

        # 4. Zero Critical Regression Check
        base_qual = base.get("quality")
        if base_qual is not None and qual_val < base_qual - 0.05:
            failures.append(
                f"Critical regression detected: quality dropped from {base_qual:.4f} to {qual_val:.4f}"
            )

        base_err = base.get("error_rate")
        cand_err = metrics.get("error_rate")
        if base_err is not None and cand_err is not None and cand_err > base_err + 0.05:
            failures.append(
                f"Error rate regression detected: error_rate increased from {base_err:.4f} to {cand_err:.4f}"
            )

        # 5. Feasibility check
        if not candidate.is_feasible:
            failures.append(
                f"Candidate marked infeasible: {'; '.join(candidate.constraint_violations)}"
            )

        passed = len(failures) == 0
        return passed, failures
