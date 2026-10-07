"""Phase 38 Optimization Bridge mapping RAG metrics to multi-objective Pareto optimization."""

from __future__ import annotations

import logging

from aireliability.optimization.engine import OptimizationEngine
from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    ComponentCategory,
    ConstraintOperator,
    ObjectiveDirection,
    OptimizationConstraint,
    OptimizationObjective,
    OptimizationProblem,
    OptimizationResult,
    OptimizationVariable,
    VariableDomain,
)

logger = logging.getLogger(__name__)


class RAGOptimizationBridge:
    """Connects RAG pipeline hyperparameters to Phase 38 multi-objective Pareto optimization."""

    def __init__(self, engine: OptimizationEngine | None = None) -> None:
        self.engine = engine or OptimizationEngine()

    def create_rag_optimization_problem(
        self,
        name: str = "RAG Reliability Optimization",
        target_component: str = "retriever",
        baseline_top_k: int = 5,
        baseline_chunk_size: int = 256,
        baseline_similarity_threshold: float = 0.70,
        min_grounding: float = 0.80,
        min_safety: float = 0.95,
    ) -> OptimizationProblem:
        """Create a multi-objective optimization problem targeting RAG trade-offs."""
        base_vals = {
            "top_k": baseline_top_k,
            "chunk_size": baseline_chunk_size,
            "similarity_threshold": baseline_similarity_threshold,
            "temperature": 0.7,
        }
        base_cfg = create_configuration(
            base_vals, description="Baseline RAG Configuration"
        )

        objectives = [
            OptimizationObjective(
                objective_id="grounding",
                metric="groundedness",
                direction=ObjectiveDirection.MAXIMIZE,
                weight=1.0,
            ),
            OptimizationObjective(
                objective_id="retrieval_recall",
                metric="quality",
                direction=ObjectiveDirection.MAXIMIZE,
                weight=1.0,
            ),
            OptimizationObjective(
                objective_id="cost",
                metric="cost",
                direction=ObjectiveDirection.MINIMIZE,
                weight=1.0,
            ),
            OptimizationObjective(
                objective_id="latency",
                metric="latency",
                direction=ObjectiveDirection.MINIMIZE,
                weight=1.0,
            ),
        ]

        constraints = [
            OptimizationConstraint(
                constraint_id="min_safety",
                metric="safety",
                operator=ConstraintOperator.GE,
                threshold=min_safety,
                is_hard=True,
            ),
            OptimizationConstraint(
                constraint_id="min_grounding",
                metric="groundedness",
                operator=ConstraintOperator.GE,
                threshold=min_grounding,
                is_hard=True,
            ),
        ]

        variables = [
            OptimizationVariable(
                variable_id="top_k",
                name="top_k",
                component=ComponentCategory.RETRIEVAL,
                domain=VariableDomain.INT,
                min_value=1.0,
                max_value=20.0,
                step=1.0,
                default_value=baseline_top_k,
            ),
            OptimizationVariable(
                variable_id="chunk_size",
                name="Context Chunk Size",
                component=ComponentCategory.RAG,
                domain=VariableDomain.INT,
                min_value=64.0,
                max_value=1024.0,
                step=64.0,
                default_value=baseline_chunk_size,
            ),
            OptimizationVariable(
                variable_id="similarity_threshold",
                name="Similarity Cutoff Threshold",
                component=ComponentCategory.RETRIEVAL,
                domain=VariableDomain.FLOAT,
                min_value=0.4,
                max_value=0.95,
                step=0.05,
                default_value=baseline_similarity_threshold,
            ),
        ]

        return OptimizationProblem(
            name=name,
            description="Optimize retrieval top-k, chunk size, and threshold for grounding vs latency/cost",
            baseline_config=base_cfg,
            baseline_metrics={
                "groundedness": 0.85,
                "quality": 0.88,
                "cost": 0.015,
                "latency": 0.75,
                "safety": 0.98,
            },
            variables=variables,
            objectives=objectives,
            constraints=constraints,
        )

    def optimize_rag(
        self,
        problem: OptimizationProblem,
        strategy: str = "grid",
        max_candidates: int = 15,
    ) -> OptimizationResult:
        """Run Pareto optimization on RAG variables."""
        from aireliability.optimization.models import OptimizationBudget

        budget = OptimizationBudget(
            max_candidates=max_candidates, max_evaluations=max_candidates
        )
        return self.engine.run(problem=problem, budget=budget, strategy=strategy)
