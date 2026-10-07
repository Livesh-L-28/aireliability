"""Benchmark suite for Reliability Optimization Engine (Phase 38)."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.optimization.engine import OptimizationEngine
from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    OptimizationBudget,
    OptimizationObjective,
    OptimizationProblem,
)
from aireliability.optimization.pareto import find_pareto_frontier
from aireliability.optimization.strategies import (
    BayesianOptimizationStrategy,
    EvolutionarySearchStrategy,
    GridSearchStrategy,
    HillClimbingStrategy,
    LocalSearchStrategy,
    RandomSearchStrategy,
)
from aireliability.optimization.variables import get_default_variable_registry
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_optimization_problem() -> OptimizationProblem:
    """Build a deterministic, lightweight optimization problem."""
    reg = get_default_variable_registry()
    base_cfg = create_configuration({"temperature": 0.5, "top_k": 5})
    return OptimizationProblem(
        name="Reliability Optimization Benchmark Problem",
        baseline_config=base_cfg,
        baseline_metrics={"accuracy": 0.88, "latency_ms": 12.0, "cost": 0.015},
        variables=[reg.get("temperature"), reg.get("top_k")],
        objectives=[
            OptimizationObjective(objective_id="accuracy", metric="accuracy"),
            OptimizationObjective(objective_id="latency_ms", metric="latency_ms"),
        ],
    )


def run_optimization_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    prob = make_optimization_problem()
    budget_small = OptimizationBudget(max_candidates=10)

    # 1. Grid Search Strategy
    grid_strat = GridSearchStrategy(max_ticks_per_var=3)

    def bench_grid_search() -> None:
        _ = grid_strat.generate_candidates(prob, budget_small)

    metrics.append(
        measure_benchmark(
            operation="opt_strategy_grid_search",
            target_func=bench_grid_search,
            input_size="10 candidates 2 variables",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    # 2. Random Search Strategy
    rand_strat = RandomSearchStrategy()

    def bench_random_search() -> None:
        _ = rand_strat.generate_candidates(prob, budget_small, seed=config.seed)

    metrics.append(
        measure_benchmark(
            operation="opt_strategy_random_search",
            target_func=bench_random_search,
            input_size="10 candidates random",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    # 3. Local Search Strategy
    local_strat = LocalSearchStrategy(step_radius=2)

    def bench_local_search() -> None:
        _ = local_strat.generate_candidates(prob, budget_small, seed=config.seed)

    metrics.append(
        measure_benchmark(
            operation="opt_strategy_local_search",
            target_func=bench_local_search,
            input_size="10 candidates local perturbation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    # 4. Hill Climbing Strategy
    hill_strat = HillClimbingStrategy()

    def bench_hill_climbing() -> None:
        _ = hill_strat.generate_candidates(prob, budget_small, seed=config.seed)

    metrics.append(
        measure_benchmark(
            operation="opt_strategy_hill_climbing",
            target_func=bench_hill_climbing,
            input_size="10 candidates hill climbing",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    # 5. Bayesian Search Strategy
    bayes_strat = BayesianOptimizationStrategy()

    def bench_bayesian_search() -> None:
        _ = bayes_strat.generate_candidates(prob, budget_small, seed=config.seed)

    metrics.append(
        measure_benchmark(
            operation="opt_strategy_bayesian",
            target_func=bench_bayesian_search,
            input_size="10 candidates surrogate model",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    # 6. Evolutionary Search Strategy
    evo_strat = EvolutionarySearchStrategy(population_size=6)

    def bench_evolutionary_search() -> None:
        _ = evo_strat.generate_candidates(prob, budget_small, seed=config.seed)

    metrics.append(
        measure_benchmark(
            operation="opt_strategy_evolutionary",
            target_func=bench_evolutionary_search,
            input_size="10 candidates evolutionary",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    # 7. Pareto Frontier Evaluation (50 candidate points)
    budget_50 = OptimizationBudget(max_candidates=50)
    candidates_50 = rand_strat.generate_candidates(prob, budget_50, seed=config.seed)
    # Assign simulated metric evaluations to candidates
    for i, c in enumerate(candidates_50):
        c.objective_values = {
            "accuracy": 0.80 + ((i % 15) * 0.01),
            "latency_ms": 10.0 + ((i % 20) * 0.5),
        }

    def bench_pareto_frontier() -> None:
        _ = find_pareto_frontier(candidates=candidates_50, objectives=prob.objectives)

    metrics.append(
        measure_benchmark(
            operation="opt_pareto_frontier_eval",
            target_func=bench_pareto_frontier,
            input_size="50 candidates 2 objectives",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    # 8. Complete Optimization Engine Run
    engine = OptimizationEngine()

    def bench_complete_optimization_run() -> None:
        _ = engine.run(
            problem=prob,
            budget=OptimizationBudget(max_candidates=5),
            strategy="random",
            seed=config.seed,
        )

    metrics.append(
        measure_benchmark(
            operation="opt_complete_engine_run",
            target_func=bench_complete_optimization_run,
            input_size="End-to-end 5 candidates optimization run",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("optimization_search"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_optimization_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
