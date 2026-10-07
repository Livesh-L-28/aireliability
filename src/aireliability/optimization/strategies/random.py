"""Deterministic pseudo-random search strategy with seed reproducibility."""

from __future__ import annotations

import random
from typing import Any

from aireliability.optimization.models import (
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationProblem,
    OptimizationVariable,
    VariableDomain,
)
from aireliability.optimization.strategies.base import BaseSearchStrategy


def _sample_variable(var: OptimizationVariable, rng: random.Random) -> Any:
    """Sample a random parameter value according to its domain boundaries."""
    if var.domain == VariableDomain.CHOICE:
        if var.choices:
            return rng.choice(var.choices)
        return var.default_value

    if var.domain == VariableDomain.BOOL:
        return rng.choice([True, False])

    if var.domain == VariableDomain.INT:
        min_v = int(var.min_value if var.min_value is not None else 0)
        max_v = int(var.max_value if var.max_value is not None else 10)
        if var.step and var.step > 1:
            step = int(var.step)
            ticks = list(range(min_v, max_v + 1, step))
            return rng.choice(ticks) if ticks else min_v
        return rng.randint(min_v, max_v)

    if var.domain == VariableDomain.FLOAT:
        min_v = var.min_value if var.min_value is not None else 0.0
        max_v = var.max_value if var.max_value is not None else 1.0
        val = rng.uniform(min_v, max_v)
        if var.step and var.step > 0:
            val = round(round((val - min_v) / var.step) * var.step + min_v, 4)
            val = max(min_v, min(max_v, val))
        return round(val, 4)

    return var.default_value


class RandomSearchStrategy(BaseSearchStrategy):
    """Generates candidate configurations via seeded deterministic pseudo-random sampling."""

    def __init__(self) -> None:
        super().__init__(name="random_search")

    def generate_candidates(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate pseudo-random configurations bounded by budget and variables."""
        if not problem.variables:
            return []

        rng = random.Random(seed)
        base_vals = dict(problem.baseline_config.values)

        candidates: list[OptimizationCandidate] = []
        seen_fingerprints: set[str] = set()

        if problem.baseline_config.fingerprint:
            seen_fingerprints.add(problem.baseline_config.fingerprint)

        if history:
            for past in history:
                seen_fingerprints.add(past.fingerprint)

        limit = budget.max_candidates
        max_attempts = limit * 20
        attempts = 0

        while len(candidates) < limit and attempts < max_attempts:
            attempts += 1
            cfg_vals = dict(base_vals)

            for var in problem.variables:
                cfg_vals[var.variable_id] = _sample_variable(var, rng)

            cand = self._build_candidate(
                cfg_vals,
                generation_params={"sample_index": len(candidates), "seed": seed},
            )

            if cand.fingerprint not in seen_fingerprints:
                seen_fingerprints.add(cand.fingerprint)
                candidates.append(cand)

        return candidates
