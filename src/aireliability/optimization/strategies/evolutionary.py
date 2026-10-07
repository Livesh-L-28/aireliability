"""Bounded evolutionary genetic search strategy with selection, crossover, and mutation."""

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
from aireliability.optimization.strategies.climbing import _compute_scalar_score
from aireliability.optimization.strategies.random import _sample_variable


def _mutate_variable(
    var: OptimizationVariable,
    current_val: Any,
    rng: random.Random,
    mutation_rate: float = 0.2,
) -> Any:
    """Mutate a variable value with given probability."""
    if rng.random() > mutation_rate:
        return current_val

    if var.domain == VariableDomain.CHOICE and var.choices:
        return rng.choice(var.choices)

    if var.domain == VariableDomain.BOOL:
        return not current_val

    if var.domain in (VariableDomain.FLOAT, VariableDomain.INT):
        min_v = var.min_value if var.min_value is not None else 0.0
        max_v = var.max_value if var.max_value is not None else 1.0
        step = (
            var.step
            if var.step and var.step > 0
            else ((max_v - min_v) / 10.0 if max_v > min_v else 0.1)
        )

        direction = 1 if rng.random() > 0.5 else -1
        delta = step * direction
        new_val = float(current_val if current_val is not None else min_v) + delta
        new_val = max(min_v, min(max_v, new_val))

        if var.domain == VariableDomain.INT:
            return int(round(new_val))
        return round(new_val, 4)

    return current_val


def _crossover_configurations(
    cfg_a: dict[str, Any],
    cfg_b: dict[str, Any],
    variables: list[OptimizationVariable],
    rng: random.Random,
) -> dict[str, Any]:
    """Perform uniform crossover combining attributes from two parent configurations."""
    child: dict[str, Any] = {}
    for var in variables:
        k = var.variable_id
        val_a = cfg_a.get(k, var.default_value)
        val_b = cfg_b.get(k, var.default_value)

        # Uniform crossover: 50% chance of inheriting from either parent
        child[k] = val_a if rng.random() < 0.5 else val_b

    return child


class EvolutionarySearchStrategy(BaseSearchStrategy):
    """Bounded genetic algorithm generating candidate configurations across generations."""

    def __init__(
        self,
        population_size: int = 10,
        mutation_rate: float = 0.25,
        crossover_rate: float = 0.7,
    ) -> None:
        super().__init__(name="evolutionary_search")
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate

    def generate_candidates(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate candidates across bounded evolutionary generations."""
        if not problem.variables:
            return []

        rng = random.Random(seed)
        limit = budget.max_candidates
        max_generations = min(
            budget.max_generations, max(1, limit // max(1, self.population_size))
        )

        # Step 1: Initialize population from evaluated history or baseline/random
        population: list[dict[str, Any]] = []
        base_vals = dict(problem.baseline_config.values)

        if history:
            evaluated = [c for c in history if c.is_feasible and c.objective_values]
            if evaluated:
                # Elite selection: sort by scalar utility
                evaluated.sort(
                    key=lambda c: _compute_scalar_score(c, problem.objectives),
                    reverse=True,
                )
                population = [
                    dict(c.configuration.values)
                    for c in evaluated[: self.population_size]
                ]

        # If population not full, pad with baseline and random perturbations
        if not population:
            population.append(dict(base_vals))

        while len(population) < self.population_size:
            random_cfg = dict(base_vals)
            for var in problem.variables:
                random_cfg[var.variable_id] = _sample_variable(var, rng)
            population.append(random_cfg)

        candidates: list[OptimizationCandidate] = []
        seen_fingerprints: set[str] = set()

        if problem.baseline_config.fingerprint:
            seen_fingerprints.add(problem.baseline_config.fingerprint)

        if history:
            for past in history:
                seen_fingerprints.add(past.fingerprint)

        # Step 2: Evolve across generations
        for gen in range(1, max_generations + 1):
            if len(candidates) >= limit:
                break

            next_population: list[dict[str, Any]] = []

            for _ in range(self.population_size):
                if len(candidates) >= limit:
                    break

                # Tournament selection of 2 parents
                parent_a = rng.choice(population)
                parent_b = rng.choice(population)

                # Crossover
                if rng.random() < self.crossover_rate and len(population) > 1:
                    child_cfg = _crossover_configurations(
                        parent_a, parent_b, problem.variables, rng
                    )
                else:
                    child_cfg = dict(parent_a)

                # Mutation
                for var in problem.variables:
                    child_cfg[var.variable_id] = _mutate_variable(
                        var, child_cfg[var.variable_id], rng, self.mutation_rate
                    )

                next_population.append(child_cfg)

                cand = self._build_candidate(
                    child_cfg,
                    generation_params={
                        "generation": gen,
                        "crossover_applied": True,
                        "mutation_rate": self.mutation_rate,
                    },
                )

                if cand.fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(cand.fingerprint)
                    candidates.append(cand)

            population = next_population if next_population else population

        return candidates
