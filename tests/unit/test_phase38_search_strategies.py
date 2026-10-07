"""Unit tests for Phase 38 Search Strategies."""

from __future__ import annotations

from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    OptimizationBudget,
    OptimizationObjective,
    OptimizationProblem,
)
from aireliability.optimization.strategies import (
    BayesianOptimizationStrategy,
    EvolutionarySearchStrategy,
    GridSearchStrategy,
    HillClimbingStrategy,
    LocalSearchStrategy,
    RandomSearchStrategy,
    get_strategy,
)
from aireliability.optimization.variables import get_default_variable_registry


def _build_test_problem() -> OptimizationProblem:
    reg = get_default_variable_registry()
    base_cfg = create_configuration({"temperature": 0.5, "top_k": 5})
    return OptimizationProblem(
        name="Test Search Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "cost": 0.02},
        variables=[reg.get("temperature"), reg.get("top_k")],
        objectives=[
            OptimizationObjective(objective_id="quality", metric="quality"),
            OptimizationObjective(objective_id="cost", metric="cost"),
        ],
    )


def test_grid_search_strategy() -> None:
    """Test grid search generates bounded Cartesian combinations."""
    prob = _build_test_problem()
    budget = OptimizationBudget(max_candidates=10)
    strat = GridSearchStrategy(max_ticks_per_var=3)

    candidates = strat.generate_candidates(prob, budget)
    assert len(candidates) > 0
    assert len(candidates) <= budget.max_candidates
    # Verify unique fingerprints
    fps = {c.fingerprint for c in candidates}
    assert len(fps) == len(candidates)


def test_random_search_reproducible_seed() -> None:
    """Test random search with identical seed produces identical candidates."""
    prob = _build_test_problem()
    budget = OptimizationBudget(max_candidates=5)
    strat = RandomSearchStrategy()

    run1 = strat.generate_candidates(prob, budget, seed=12345)
    run2 = strat.generate_candidates(prob, budget, seed=12345)
    run_diff = strat.generate_candidates(prob, budget, seed=99999)

    assert len(run1) == 5
    assert [c.fingerprint for c in run1] == [c.fingerprint for c in run2]
    assert [c.fingerprint for c in run1] != [c.fingerprint for c in run_diff]


def test_local_search_strategy() -> None:
    """Test local search generates neighboring perturbations around baseline."""
    prob = _build_test_problem()
    budget = OptimizationBudget(max_candidates=8)
    strat = LocalSearchStrategy(step_radius=1)

    candidates = strat.generate_candidates(prob, budget)
    assert len(candidates) > 0
    assert len(candidates) <= budget.max_candidates

    # Neighboring configurations should have at least one modified parameter
    for c in candidates:
        diffs = [
            k
            for k, v in c.configuration.values.items()
            if prob.baseline_config.values.get(k) != v
        ]
        assert len(diffs) >= 1


def test_hill_climbing_strategy() -> None:
    """Test hill climbing steps around current best known candidate."""
    prob = _build_test_problem()
    budget = OptimizationBudget(max_candidates=5)
    strat = HillClimbingStrategy(step_size=1)

    cands = strat.generate_candidates(prob, budget)
    assert len(cands) > 0
    assert len(cands) <= budget.max_candidates


def test_bayesian_optimization_strategy() -> None:
    """Test surrogate acquisition scoring selects promising candidates."""
    prob = _build_test_problem()
    budget = OptimizationBudget(max_candidates=4)
    strat = BayesianOptimizationStrategy(kappa=1.96)

    cands = strat.generate_candidates(prob, budget, seed=42)
    assert len(cands) > 0
    assert len(cands) <= budget.max_candidates
    assert all(c.generation_strategy == "bayesian_optimization" for c in cands)


def test_evolutionary_search_strategy() -> None:
    """Test evolutionary algorithm performs selection, crossover, and mutation."""
    prob = _build_test_problem()
    budget = OptimizationBudget(max_candidates=6, max_generations=2)
    strat = EvolutionarySearchStrategy(population_size=4)

    cands = strat.generate_candidates(prob, budget, seed=42)
    assert len(cands) > 0
    assert len(cands) <= budget.max_candidates


def test_strategy_factory() -> None:
    """Test get_strategy resolves all registered strategy names."""
    assert isinstance(get_strategy("grid"), GridSearchStrategy)
    assert isinstance(get_strategy("random"), RandomSearchStrategy)
    assert isinstance(get_strategy("local"), LocalSearchStrategy)
    assert isinstance(get_strategy("climbing"), HillClimbingStrategy)
    assert isinstance(get_strategy("bayesian"), BayesianOptimizationStrategy)
    assert isinstance(get_strategy("evolutionary"), EvolutionarySearchStrategy)
