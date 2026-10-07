"""Deterministic search strategies package for Phase 38 AI Reliability Optimization."""

from __future__ import annotations

from aireliability.optimization.strategies.base import BaseSearchStrategy
from aireliability.optimization.strategies.bayesian import BayesianOptimizationStrategy
from aireliability.optimization.strategies.climbing import HillClimbingStrategy
from aireliability.optimization.strategies.evolutionary import (
    EvolutionarySearchStrategy,
)
from aireliability.optimization.strategies.grid import GridSearchStrategy
from aireliability.optimization.strategies.local import LocalSearchStrategy
from aireliability.optimization.strategies.random import RandomSearchStrategy

STRATEGY_REGISTRY: dict[str, type[BaseSearchStrategy]] = {
    "grid": GridSearchStrategy,
    "grid_search": GridSearchStrategy,
    "random": RandomSearchStrategy,
    "random_search": RandomSearchStrategy,
    "local": LocalSearchStrategy,
    "local_search": LocalSearchStrategy,
    "climbing": HillClimbingStrategy,
    "hill_climbing": HillClimbingStrategy,
    "bayesian": BayesianOptimizationStrategy,
    "bayesian_optimization": BayesianOptimizationStrategy,
    "evolutionary": EvolutionarySearchStrategy,
    "evolutionary_search": EvolutionarySearchStrategy,
}


def get_strategy(name: str) -> BaseSearchStrategy:
    """Fetch an instantiated search strategy by name."""
    normalized = name.strip().lower()
    if normalized not in STRATEGY_REGISTRY:
        available = sorted(set(STRATEGY_REGISTRY.keys()))
        raise KeyError(
            f"Unknown search strategy '{name}'. Available strategies: {available}"
        )
    return STRATEGY_REGISTRY[normalized]()


__all__ = [
    "STRATEGY_REGISTRY",
    "BaseSearchStrategy",
    "BayesianOptimizationStrategy",
    "EvolutionarySearchStrategy",
    "GridSearchStrategy",
    "HillClimbingStrategy",
    "LocalSearchStrategy",
    "RandomSearchStrategy",
    "get_strategy",
]
