"""Bounded Grid Search exploration strategy across discretized parameter dimensions."""

from __future__ import annotations

import itertools
from typing import Any

from aireliability.optimization.models import (
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationProblem,
    OptimizationVariable,
    VariableDomain,
)
from aireliability.optimization.strategies.base import BaseSearchStrategy


def _discretize_variable(var: OptimizationVariable, max_ticks: int = 5) -> list[Any]:
    """Generate discrete evaluation ticks for a variable."""
    if var.domain == VariableDomain.CHOICE:
        return list(var.choices) if var.choices else [var.default_value]

    if var.domain == VariableDomain.BOOL:
        return [True, False]

    if var.domain in (VariableDomain.FLOAT, VariableDomain.INT):
        min_v = var.min_value if var.min_value is not None else 0.0
        max_v = var.max_value if var.max_value is not None else 1.0

        if var.step and var.step > 0:
            ticks: list[Any] = []
            curr = min_v
            while curr <= max_v + 1e-9 and len(ticks) < max_ticks:
                val = (
                    int(round(curr))
                    if var.domain == VariableDomain.INT
                    else round(curr, 4)
                )
                ticks.append(val)
                curr += var.step
            return ticks

        # Equidistant ticks if step is not defined
        steps = max(1, min(max_ticks - 1, 4))
        delta = (max_v - min_v) / steps
        ticks = [
            int(round(min_v + i * delta))
            if var.domain == VariableDomain.INT
            else round(min_v + i * delta, 4)
            for i in range(steps + 1)
        ]
        return ticks

    return [var.default_value]


class GridSearchStrategy(BaseSearchStrategy):
    """Generates candidate configurations systematically via bounded Cartesian product."""

    def __init__(self, max_ticks_per_var: int = 4) -> None:
        super().__init__(name="grid_search")
        self.max_ticks_per_var = max_ticks_per_var

    def generate_candidates(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate bounded Cartesian product of configurations."""
        if not problem.variables:
            return []

        # Baseline starting values
        base_vals = dict(problem.baseline_config.values)

        var_keys = [v.variable_id for v in problem.variables]
        var_ticks = [
            _discretize_variable(v, max_ticks=self.max_ticks_per_var)
            for v in problem.variables
        ]

        candidates: list[OptimizationCandidate] = []
        seen_fingerprints: set[str] = set()

        # Add baseline fingerprint to avoid redundant evaluations
        if problem.baseline_config.fingerprint:
            seen_fingerprints.add(problem.baseline_config.fingerprint)

        if history:
            for past in history:
                seen_fingerprints.add(past.fingerprint)

        limit = budget.max_candidates

        for combo in itertools.product(*var_ticks):
            if len(candidates) >= limit:
                break

            cfg_vals = dict(base_vals)
            for k, val in zip(var_keys, combo, strict=False):
                cfg_vals[k] = val

            cand = self._build_candidate(
                cfg_vals,
                generation_params={"combo_index": len(candidates)},
            )

            if cand.fingerprint not in seen_fingerprints:
                seen_fingerprints.add(cand.fingerprint)
                candidates.append(cand)

        return candidates
