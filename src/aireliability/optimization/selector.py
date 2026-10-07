"""Policy-driven candidate selection from Pareto frontier with tie-breaking hierarchy."""

from __future__ import annotations

import logging

from aireliability.optimization.gates import OptimizationGateChecker
from aireliability.optimization.models import (
    CandidateStatus,
    OptimizationCandidate,
    OptimizationDecision,
    OptimizationPolicy,
    ParetoFrontier,
    SelectionStrategy,
)

logger = logging.getLogger(__name__)


def _tie_break_key(
    cand: OptimizationCandidate,
) -> tuple[float, float, float, float, float, float]:
    """Compute tie-breaking tuple following the mandatory preference hierarchy:

    1. Higher Safety
    2. Higher Security
    3. Higher Reliability
    4. Lower Error Rate (regression stability)
    5. Lower Cost
    6. Lower Latency
    """
    vals = cand.objective_values
    safety = vals.get("safety", 1.0)
    security = vals.get("security", 1.0)
    reliability = vals.get("reliability", 1.0)
    error_rate = vals.get("error_rate", 0.0)
    cost = vals.get("cost", 0.0)
    latency = vals.get("latency", 0.0)

    # In tuple comparison, higher is better, so negate cost, latency, error_rate
    return (
        safety,
        security,
        reliability,
        -error_rate,
        -cost,
        -latency,
    )


class OptimizationSelector:
    """Selects an optimal candidate from the Pareto frontier governed by policy rules."""

    def __init__(self, gate_checker: OptimizationGateChecker | None = None) -> None:
        self.gate_checker = gate_checker or OptimizationGateChecker()

    def select(
        self,
        frontier: ParetoFrontier,
        candidates: list[OptimizationCandidate],
        policy: OptimizationPolicy,
        baseline_metrics: dict[str, float] | None = None,
        explicit_candidate_id: str | None = None,
    ) -> tuple[OptimizationCandidate | None, OptimizationDecision | None, str]:
        """Select the best candidate matching policy strategy and passing all reliability gates.

        Returns (selected_candidate, decision_record, explanation).
        """
        # Lookup map
        cand_map = {c.candidate_id: c for c in candidates}

        # Filter candidates on the non-dominated Pareto frontier
        pareto_cands: list[OptimizationCandidate] = []
        for cid in frontier.non_dominated_candidate_ids:
            if cid in cand_map:
                pareto_cands.append(cand_map[cid])

        # If frontier has no points, fall back to any feasible candidate
        pool = (
            pareto_cands if pareto_cands else [c for c in candidates if c.is_feasible]
        )

        # Filter candidates that pass strict reliability gates
        passing_cands: list[OptimizationCandidate] = []
        gate_failures: dict[str, list[str]] = {}

        for cand in pool:
            passed, reasons = self.gate_checker.check_gates(
                candidate=cand,
                policy=policy,
                baseline_metrics=baseline_metrics,
            )
            if passed:
                passing_cands.append(cand)
            else:
                gate_failures[cand.candidate_id] = reasons

        if not passing_cands:
            explanation = (
                "NO_FEASIBLE_CONFIGURATION: No candidate satisfied all hard constraints "
                f"and reliability quality gates. Evaluated {len(pool)} candidates; "
                f"all violated safety/security/regression thresholds."
            )
            logger.warning(explanation)
            return None, None, explanation

        # Explicit selection if requested
        if (
            policy.selection_strategy == SelectionStrategy.EXPLICIT_SELECTION
            or explicit_candidate_id
        ):
            target_id = explicit_candidate_id
            for c in passing_cands:
                if c.candidate_id == target_id:
                    c.status = CandidateStatus.SELECTED
                    c.explanation = f"Explicitly chosen candidate '{target_id}'"
                    dec = OptimizationDecision(
                        optimization_id=c.metadata.get(
                            "optimization_id", "opt_default"
                        ),
                        selected_candidate_id=c.candidate_id,
                        rationale=c.explanation,
                        risk_tier=policy.allowed_risk,
                    )
                    return c, dec, c.explanation

        # Strategy scoring
        strat = policy.selection_strategy

        def _score_candidate(cand: OptimizationCandidate) -> float:
            vals = cand.objective_values
            norms = cand.normalized_values

            if strat == SelectionStrategy.HIGHEST_QUALITY:
                return vals.get("quality", vals.get("reliability", 0.0))

            if strat == SelectionStrategy.LOWEST_COST:
                # Lower cost is better -> negate
                return -vals.get("cost", 0.0)

            if strat == SelectionStrategy.LOWEST_LATENCY:
                return -vals.get("latency", 0.0)

            if strat == SelectionStrategy.WEIGHTED_PREFERENCE:
                weights = policy.preference_weights
                total = 0.0
                for k, w in weights.items():
                    # Use normalized value if available
                    v = norms.get(k, vals.get(k, 0.0))
                    total += v * w
                return total

            # Default: BALANCED
            # Sum of normalized objective values
            return sum(norms.values()) if norms else vals.get("quality", 0.0)

        # Sort passing candidates by strategy score, then break ties with mandatory safety hierarchy
        passing_cands.sort(
            key=lambda c: (_score_candidate(c), _tie_break_key(c)),
            reverse=True,
        )

        selected = passing_cands[0]
        selected.status = CandidateStatus.SELECTED

        explanation = (
            f"Selected candidate '{selected.candidate_id}' using strategy '{strat.value}'. "
            f"Objective values: {selected.objective_values}. "
            f"Deltas vs baseline: {list(selected.baseline_deltas.keys())}. "
            f"Passed all safety and reliability gates."
        )
        selected.explanation = explanation

        decision = OptimizationDecision(
            optimization_id=selected.metadata.get("optimization_id", "opt_default"),
            selected_candidate_id=selected.candidate_id,
            rationale=explanation,
            risk_tier=policy.allowed_risk,
        )

        return selected, decision, explanation
