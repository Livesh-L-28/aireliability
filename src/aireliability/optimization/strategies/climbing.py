"""Hill Climbing iterative ascent/descent strategy."""

from __future__ import annotations

from aireliability.optimization.models import (
    ObjectiveDirection,
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationObjective,
    OptimizationProblem,
)
from aireliability.optimization.strategies.base import BaseSearchStrategy
from aireliability.optimization.strategies.local import _get_neighbors


def _compute_scalar_score(
    candidate: OptimizationCandidate, objectives: list[OptimizationObjective]
) -> float:
    """Compute scalarized performance score for a candidate across objectives."""
    total = 0.0
    for obj in objectives:
        raw_val = candidate.objective_values.get(
            obj.objective_id, candidate.objective_values.get(obj.metric, 0.0)
        )
        weight = obj.weight if obj.weight > 0 else 1.0

        if obj.direction == ObjectiveDirection.MAXIMIZE:
            val = raw_val
        elif obj.direction == ObjectiveDirection.MINIMIZE:
            val = -raw_val
        elif obj.direction == ObjectiveDirection.TARGET:
            target = obj.target_value or 0.0
            val = -abs(raw_val - target)
        else:
            val = raw_val

        total += val * weight
    return total


class HillClimbingStrategy(BaseSearchStrategy):
    """Iteratively climbs along the gradient of improving parameter neighbors."""

    def __init__(self, step_size: int = 1) -> None:
        super().__init__(name="hill_climbing")
        self.step_size = step_size

    def generate_candidates(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate neighboring step candidates around current best known configuration."""
        if not problem.variables:
            return []

        # Determine starting center: best candidate from history, or baseline
        center_vals = dict(problem.baseline_config.values)
        parent_id: str | None = None

        if history:
            evaluated_cands = [
                c for c in history if c.is_feasible and c.objective_values
            ]
            if evaluated_cands:
                best_cand = max(
                    evaluated_cands,
                    key=lambda c: _compute_scalar_score(c, problem.objectives),
                )
                center_vals = dict(best_cand.configuration.values)
                parent_id = best_cand.candidate_id

        candidates: list[OptimizationCandidate] = []
        seen_fingerprints: set[str] = set()

        if problem.baseline_config.fingerprint:
            seen_fingerprints.add(problem.baseline_config.fingerprint)

        if history:
            for past in history:
                seen_fingerprints.add(past.fingerprint)

        limit = budget.max_candidates

        # Generate neighbor mutations around center
        for var in problem.variables:
            if len(candidates) >= limit:
                break

            curr_val = center_vals.get(var.variable_id, var.default_value)
            neighbors = _get_neighbors(var, curr_val, num_steps=self.step_size)

            for n_val in neighbors:
                if len(candidates) >= limit:
                    break

                stepped_cfg = dict(center_vals)
                stepped_cfg[var.variable_id] = n_val

                cand = self._build_candidate(
                    stepped_cfg,
                    generation_params={
                        "parent_id": parent_id,
                        "stepped_variable": var.variable_id,
                        "new_value": n_val,
                    },
                    parent_candidate_id=parent_id,
                )

                if cand.fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(cand.fingerprint)
                    candidates.append(cand)

        return candidates
