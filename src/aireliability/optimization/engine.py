"""Unified Optimization Engine orchestrating search, evaluation, Pareto analysis, and governance."""

from __future__ import annotations

import logging
import time

from aireliability.graph.graph import KnowledgeGraph
from aireliability.optimization.deployment_bridge import OptimizationDeploymentBridge
from aireliability.optimization.evaluator import OptimizationEvaluator
from aireliability.optimization.gates import OptimizationGateChecker
from aireliability.optimization.generator import CandidateGenerator
from aireliability.optimization.graph_bridge import OptimizationGraphBridge
from aireliability.optimization.models import (
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationPolicy,
    OptimizationProblem,
    OptimizationResult,
    StoppingReason,
)
from aireliability.optimization.observability_bridge import (
    OptimizationObservabilityBridge,
)
from aireliability.optimization.pareto import find_pareto_frontier
from aireliability.optimization.selector import OptimizationSelector
from aireliability.optimization.test_bridge import OptimizationTestBridge

logger = logging.getLogger(__name__)


class OptimizationEngine:
    """Production-grade AI Reliability Optimization Engine.

    Coordinates:
    Baseline -> Problem Definition -> Candidate Generation -> Search / Experiment ->
    Evaluation Loop (with caching) -> Constraint Check (Hard Vetoes) ->
    Pareto Analysis -> Reliability Quality Gates -> Policy Selection ->
    Phase 37 Deployment Bridge -> Knowledge Graph & Audit Learning Loop.
    """

    def __init__(
        self,
        generator: CandidateGenerator | None = None,
        evaluator: OptimizationEvaluator | None = None,
        gate_checker: OptimizationGateChecker | None = None,
        selector: OptimizationSelector | None = None,
        test_bridge: OptimizationTestBridge | None = None,
        deployment_bridge: OptimizationDeploymentBridge | None = None,
        graph_bridge: OptimizationGraphBridge | None = None,
        obs_bridge: OptimizationObservabilityBridge | None = None,
    ) -> None:
        self.generator = generator or CandidateGenerator()
        self.evaluator = evaluator or OptimizationEvaluator()
        self.gate_checker = gate_checker or OptimizationGateChecker()
        self.selector = selector or OptimizationSelector(self.gate_checker)
        self.test_bridge = test_bridge or OptimizationTestBridge()
        self.deployment_bridge = deployment_bridge or OptimizationDeploymentBridge()
        self.graph_bridge = graph_bridge or OptimizationGraphBridge()
        self.obs_bridge = obs_bridge or OptimizationObservabilityBridge()

        self._history: list[OptimizationResult] = []

    def run(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget | None = None,
        strategy: str = "random",
        policy: OptimizationPolicy | None = None,
        seed: int = 42,
        generate_validation_tests: bool = False,
        graph: KnowledgeGraph | None = None,
    ) -> OptimizationResult:
        """Execute end-to-end multi-objective optimization search and selection."""
        t_start = time.perf_counter()
        active_budget = budget or OptimizationBudget()
        active_policy = policy or OptimizationPolicy()

        self.obs_bridge.record_run_started(problem.problem_id, strategy=strategy)

        # Step 1: Historical warm-start inspection from Knowledge Graph if available
        historical_cands = self.graph_bridge.query_historical_candidates(
            problem, graph=graph
        )
        if historical_cands:
            logger.info(
                "Knowledge Graph provided %d prior candidates for warm-start",
                len(historical_cands),
            )

        # Step 2: Generate candidate configurations
        candidates = self.generator.generate(
            problem=problem,
            budget=active_budget,
            strategy=strategy,
            seed=seed,
        )

        for c in candidates:
            c.metadata["optimization_id"] = problem.problem_id
            self.obs_bridge.record_candidate_generated(strategy=strategy)

        # Step 3: Phase 36 targeted test synthesis if requested
        if generate_validation_tests and candidates:
            self.test_bridge.request_validation_tests(
                candidate=candidates[0],
                problem=problem,
            )

        # Step 4: Bounded evaluation loop
        evaluated_candidates: list[OptimizationCandidate] = []
        all_experiments = []
        eval_count = 0
        total_eval_cost = 0.0
        stopping_reason = StoppingReason.COMPLETED

        for cand in candidates:
            elapsed = time.perf_counter() - t_start

            # Check budget bounds
            if elapsed > active_budget.max_runtime_seconds:
                stopping_reason = StoppingReason.BUDGET_EXHAUSTED
                logger.warning("Optimization halted: max runtime exceeded")
                break

            if eval_count >= active_budget.max_evaluations:
                stopping_reason = StoppingReason.BUDGET_EXHAUSTED
                logger.warning("Optimization halted: max evaluations exceeded")
                break

            if total_eval_cost >= active_budget.max_cost:
                stopping_reason = StoppingReason.BUDGET_EXHAUSTED
                logger.warning("Optimization halted: max cost exceeded")
                break

            eval_t0 = time.perf_counter()
            evaluated_cand, exps = self.evaluator.evaluate_candidate(
                candidate=cand,
                problem=problem,
                repeats=active_policy.repeated_evaluations,
                seed=seed,
            )
            eval_dur = time.perf_counter() - eval_t0

            self.obs_bridge.record_evaluation(cand.candidate_id, eval_dur)

            eval_count += active_policy.repeated_evaluations
            eval_cost = cand.objective_values.get("cost", 0.0)
            total_eval_cost += eval_cost

            evaluated_candidates.append(evaluated_cand)
            all_experiments.extend(exps)

        # Step 5: Multi-objective Pareto Analysis
        frontier = find_pareto_frontier(
            candidates=evaluated_candidates,
            objectives=problem.objectives,
            constraints=problem.constraints,
        )

        # Step 6: Policy-driven candidate selection and reliability gates
        selected_cand, decision, explanation = self.selector.select(
            frontier=frontier,
            candidates=evaluated_candidates,
            policy=active_policy,
            baseline_metrics=problem.baseline_metrics,
        )

        # Step 7: Finalize stopping condition
        if stopping_reason != StoppingReason.BUDGET_EXHAUSTED and not selected_cand:
            stopping_reason = StoppingReason.NO_FEASIBLE_CONFIGURATION

        total_duration = time.perf_counter() - t_start

        # Calculate overall confidence
        conf_scores = [c.confidence for c in evaluated_candidates if c.confidence > 0]
        avg_confidence = sum(conf_scores) / len(conf_scores) if conf_scores else 0.95

        result = OptimizationResult(
            problem=problem,
            baseline_config=problem.baseline_config,
            baseline_metrics=problem.baseline_metrics,
            candidates=evaluated_candidates,
            pareto_frontier=frontier,
            selected_candidate=selected_cand,
            stopping_reason=stopping_reason,
            budget_used={
                "evaluations": eval_count,
                "candidates": len(evaluated_candidates),
                "cost": round(total_eval_cost, 4),
                "runtime_seconds": round(total_duration, 4),
            },
            duration_seconds=round(total_duration, 4),
            confidence=round(avg_confidence, 4),
            experiments=all_experiments,
            decision=decision,
            provenance={
                "strategy": strategy,
                "seed": seed,
                "policy_id": active_policy.policy_id,
            },
        )

        # Step 8: Observability and Knowledge Graph synchronization
        self.obs_bridge.record_run_completed(result)
        self.graph_bridge.sync_optimization_result(result, graph=graph)

        self._history.append(result)
        return result

    def get_history(self) -> list[OptimizationResult]:
        """Return history of executed optimization runs."""
        return list(self._history)
