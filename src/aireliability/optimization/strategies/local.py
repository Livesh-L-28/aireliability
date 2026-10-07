"""Local neighborhood perturbation search starting from baseline configuration."""

from __future__ import annotations

from typing import Any

from aireliability.optimization.models import (
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationProblem,
    OptimizationVariable,
    VariableDomain,
)
from aireliability.optimization.strategies.base import BaseSearchStrategy


def _get_neighbors(
    var: OptimizationVariable, current_val: Any, num_steps: int = 2
) -> list[Any]:
    """Generate local adjacent neighbor values for a single variable."""
    neighbors: list[Any] = []

    if var.domain == VariableDomain.CHOICE and var.choices:
        try:
            curr_idx = var.choices.index(current_val)
        except ValueError:
            curr_idx = 0
        for step in range(1, num_steps + 1):
            if curr_idx - step >= 0:
                neighbors.append(var.choices[curr_idx - step])
            if curr_idx + step < len(var.choices):
                neighbors.append(var.choices[curr_idx + step])
        return neighbors

    if var.domain == VariableDomain.BOOL:
        return [not current_val]

    if var.domain in (VariableDomain.FLOAT, VariableDomain.INT):
        min_v = var.min_value if var.min_value is not None else 0.0
        max_v = var.max_value if var.max_value is not None else 1.0
        step_sz = (
            var.step
            if var.step and var.step > 0
            else ((max_v - min_v) / 10.0 if max_v > min_v else 0.1)
        )

        curr_num = float(current_val if current_val is not None else min_v)

        for s in range(1, num_steps + 1):
            # Downward neighbor
            down = curr_num - s * step_sz
            if down >= min_v - 1e-9:
                val = (
                    int(round(down))
                    if var.domain == VariableDomain.INT
                    else round(down, 4)
                )
                neighbors.append(val)
            # Upward neighbor
            up = curr_num + s * step_sz
            if up <= max_v + 1e-9:
                val = (
                    int(round(up)) if var.domain == VariableDomain.INT else round(up, 4)
                )
                neighbors.append(val)

    return neighbors


class LocalSearchStrategy(BaseSearchStrategy):
    """Explores neighboring parameter configurations around the current baseline."""

    def __init__(self, step_radius: int = 2) -> None:
        super().__init__(name="local_search")
        self.step_radius = step_radius

    def generate_candidates(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate neighboring configurations around baseline."""
        if not problem.variables:
            return []

        base_vals = dict(problem.baseline_config.values)

        candidates: list[OptimizationCandidate] = []
        seen_fingerprints: set[str] = set()

        if problem.baseline_config.fingerprint:
            seen_fingerprints.add(problem.baseline_config.fingerprint)

        if history:
            for past in history:
                seen_fingerprints.add(past.fingerprint)

        limit = budget.max_candidates

        # 1-variable perturbations (orthogonal steps)
        for var in problem.variables:
            if len(candidates) >= limit:
                break

            curr_val = base_vals.get(var.variable_id, var.default_value)
            adjacents = _get_neighbors(var, curr_val, num_steps=self.step_radius)

            for neighbor_val in adjacents:
                if len(candidates) >= limit:
                    break

                perturbed = dict(base_vals)
                perturbed[var.variable_id] = neighbor_val

                cand = self._build_candidate(
                    perturbed,
                    generation_params={
                        "perturbed_variable": var.variable_id,
                        "neighbor_value": neighbor_val,
                    },
                )

                if cand.fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(cand.fingerprint)
                    candidates.append(cand)

        # 2-variable joint perturbations if budget allows
        if len(candidates) < limit and len(problem.variables) > 1:
            for i in range(len(problem.variables)):
                for j in range(i + 1, len(problem.variables)):
                    if len(candidates) >= limit:
                        break
                    var_a = problem.variables[i]
                    var_b = problem.variables[j]

                    neighbors_a = _get_neighbors(
                        var_a,
                        base_vals.get(var_a.variable_id, var_a.default_value),
                        num_steps=1,
                    )
                    neighbors_b = _get_neighbors(
                        var_b,
                        base_vals.get(var_b.variable_id, var_b.default_value),
                        num_steps=1,
                    )

                    for val_a in neighbors_a:
                        for val_b in neighbors_b:
                            if len(candidates) >= limit:
                                break

                            perturbed = dict(base_vals)
                            perturbed[var_a.variable_id] = val_a
                            perturbed[var_b.variable_id] = val_b

                            cand = self._build_candidate(
                                perturbed,
                                generation_params={
                                    "perturbed_variables": [
                                        var_a.variable_id,
                                        var_b.variable_id,
                                    ],
                                },
                            )

                            if cand.fingerprint not in seen_fingerprints:
                                seen_fingerprints.add(cand.fingerprint)
                                candidates.append(cand)

        return candidates
