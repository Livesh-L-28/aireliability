"""Lightweight provider-independent Bayesian-style optimization with surrogate acquisition."""

from __future__ import annotations

import math
from typing import Any

from aireliability.optimization.models import (
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationProblem,
    OptimizationVariable,
    VariableDomain,
)
from aireliability.optimization.strategies.base import BaseSearchStrategy
from aireliability.optimization.strategies.climbing import _compute_scalar_score
from aireliability.optimization.strategies.random import RandomSearchStrategy


def _distance_between(
    cfg_a: dict[str, Any],
    cfg_b: dict[str, Any],
    variables: list[OptimizationVariable],
) -> float:
    """Calculate normalized Euclidean distance between two configurations."""
    dist_sq = 0.0
    for var in variables:
        k = var.variable_id
        val_a = cfg_a.get(k)
        val_b = cfg_b.get(k)

        if val_a is None or val_b is None:
            dist_sq += 1.0
            continue

        if var.domain in (VariableDomain.FLOAT, VariableDomain.INT):
            min_v = var.min_value if var.min_value is not None else 0.0
            max_v = var.max_value if var.max_value is not None else 1.0
            span = max(max_v - min_v, 1e-6)
            diff = (float(val_a) - float(val_b)) / span
            dist_sq += diff * diff
        elif var.domain == VariableDomain.CHOICE or var.domain == VariableDomain.BOOL:
            dist_sq += 0.0 if val_a == val_b else 1.0

    return math.sqrt(dist_sq)


class BayesianOptimizationStrategy(BaseSearchStrategy):
    """Surrogate-assisted optimization balancing exploitation and exploration."""

    def __init__(self, kappa: float = 1.96, pool_multiplier: int = 5) -> None:
        super().__init__(name="bayesian_optimization")
        self.kappa = kappa
        self.pool_multiplier = pool_multiplier
        self._sampler = RandomSearchStrategy()

    def generate_candidates(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate candidate configurations selected by surrogate acquisition scoring."""
        if not problem.variables:
            return []

        # If no history yet, warm start using pseudo-random exploration
        evaluated_history = [
            c for c in (history or []) if c.is_feasible and c.objective_values
        ]
        if not evaluated_history:
            warm_cands = self._sampler.generate_candidates(problem, budget, seed=seed)
            for c in warm_cands:
                c.generation_strategy = self.name
            return warm_cands

        # Compute scalar utility for evaluated history items
        history_scores = [
            (c, _compute_scalar_score(c, problem.objectives)) for c in evaluated_history
        ]
        min_score = min(s for _, s in history_scores)
        max_score = max(s for _, s in history_scores)
        score_span = max(max_score - min_score, 1e-6)

        # Normalized scores
        norm_scores = [(c, (s - min_score) / score_span) for c, s in history_scores]

        # Generate a candidate pool
        pool_budget = OptimizationBudget(
            max_candidates=budget.max_candidates * self.pool_multiplier
        )
        pool = self._sampler.generate_candidates(
            problem, pool_budget, seed=seed + 101, history=history
        )

        if not pool:
            return []

        # Evaluate surrogate acquisition score for each pool candidate
        scored_pool: list[tuple[OptimizationCandidate, float]] = []

        for cand in pool:
            cfg = cand.configuration.values

            # Inverse-distance weighted mean estimation (Surrogate mean mu)
            weights: list[float] = []
            min_dist = float("inf")

            for past_cand, _ in norm_scores:
                dist = _distance_between(
                    cfg, past_cand.configuration.values, problem.variables
                )
                min_dist = min(min_dist, dist)
                w = 1.0 / (dist + 1e-4)
                weights.append(w)

            total_w = sum(weights)
            mu = (
                sum(w * s for w, (_, s) in zip(weights, norm_scores, strict=False))
                / total_w
                if total_w > 0
                else 0.5
            )

            # Uncertainty estimate sigma proportional to distance to nearest known sample
            sigma = min(1.0, min_dist)

            # Upper Confidence Bound (UCB) acquisition value
            acq_score = mu + self.kappa * sigma
            scored_pool.append((cand, acq_score))

        # Sort pool by acquisition score descending
        scored_pool.sort(key=lambda item: item[1], reverse=True)

        selected: list[OptimizationCandidate] = []
        limit = budget.max_candidates

        for cand, acq in scored_pool[:limit]:
            cand.generation_strategy = self.name
            cand.generation_params = {"acquisition_score": round(acq, 4)}
            selected.append(cand)

        return selected
