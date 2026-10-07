"""End-to-end integration tests for Phase 38 AI Reliability Optimization."""

from __future__ import annotations

from aireliability.graph.graph import KnowledgeGraph
from aireliability.optimization.deployment_bridge import OptimizationDeploymentBridge
from aireliability.optimization.engine import OptimizationEngine
from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    ConstraintOperator,
    ObjectiveDirection,
    OptimizationBudget,
    OptimizationConstraint,
    OptimizationObjective,
    OptimizationPolicy,
    OptimizationProblem,
    SelectionStrategy,
    StoppingReason,
)
from aireliability.optimization.variables import get_default_variable_registry
from aireliability.remediation.models import (
    RemediationLifecycleState,
    RolloutStrategy,
)


def test_end_to_end_optimization_lifecycle() -> None:
    """Test complete Phase 38 optimization lifecycle from problem definition to graph sync."""
    registry = get_default_variable_registry()
    graph = KnowledgeGraph()
    engine = OptimizationEngine()

    base_cfg = create_configuration(
        {"temperature": 0.8, "top_k": 4, "tool_timeout": 3.0},
        description="Production Baseline",
    )
    base_metrics = {
        "quality": 0.88,
        "latency": 0.90,
        "cost": 0.025,
        "safety": 0.98,
        "security": 0.99,
        "error_rate": 0.03,
    }

    problem = OptimizationProblem(
        name="Production Search Optimization",
        baseline_config=base_cfg,
        baseline_metrics=base_metrics,
        variables=[
            registry.get("temperature"),
            registry.get("top_k"),
            registry.get("tool_timeout"),
        ],
        objectives=[
            OptimizationObjective(
                objective_id="quality",
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
        ],
        constraints=[
            OptimizationConstraint(
                constraint_id="c_safety",
                metric="safety",
                operator=ConstraintOperator.GE,
                threshold=0.95,
                is_hard=True,
            ),
            OptimizationConstraint(
                constraint_id="c_quality",
                metric="quality",
                operator=ConstraintOperator.GE,
                threshold=0.85,
                is_hard=True,
            ),
        ],
    )

    budget = OptimizationBudget(max_candidates=10, max_evaluations=20)
    policy = OptimizationPolicy(
        selection_strategy=SelectionStrategy.BALANCED,
        required_safety=0.95,
    )

    result = engine.run(
        problem=problem,
        budget=budget,
        strategy="random",
        policy=policy,
        seed=101,
        graph=graph,
    )

    # Validations
    assert result.stopping_reason == StoppingReason.COMPLETED
    assert len(result.candidates) > 0
    assert len(result.pareto_frontier.non_dominated_candidate_ids) > 0
    assert result.selected_candidate is not None
    assert result.selected_candidate.is_pareto is True
    assert result.selected_candidate.is_feasible is True
    assert result.confidence > 0.0

    # Knowledge Graph verification
    assert len(graph.list_nodes()) >= 3
    assert len(graph.list_edges()) >= 2


def test_end_to_end_phase37_deployment_and_promotion() -> None:
    """Test selected candidate routes through Phase 37 canary rollout and promotion."""
    engine = OptimizationEngine()
    registry = get_default_variable_registry()

    base_cfg = create_configuration({"temperature": 0.7, "top_k": 5})
    prob = OptimizationProblem(
        name="Deploy Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.89, "cost": 0.02},
        variables=[registry.get("temperature"), registry.get("top_k")],
        objectives=[OptimizationObjective(objective_id="quality", metric="quality")],
    )

    result = engine.run(
        problem=prob,
        budget=OptimizationBudget(max_candidates=5),
        strategy="random",
        seed=42,
    )

    assert result.selected_candidate is not None

    # Route through Phase 37 deployment bridge
    bridge = OptimizationDeploymentBridge()
    proposal = bridge.create_remediation_proposal(
        candidate=result.selected_candidate,
        problem=prob,
    )

    # 1. Canary deploy
    rollout = bridge.deploy(
        proposal=proposal,
        strategy=RolloutStrategy.CANARY,
        canary_percentage=20.0,
    )
    assert rollout.strategy == RolloutStrategy.CANARY
    assert proposal.state == RemediationLifecycleState.CANARY

    # 2. Telemetry verification
    healthy = bridge.verify(proposal, observed_error_rate=0.01, sample_count=60)
    assert healthy is True
    assert proposal.state == RemediationLifecycleState.VERIFIED

    # 3. Permanent Promotion
    bridge.promote(proposal, actor="operator")
    assert proposal.state == RemediationLifecycleState.PROMOTED


def test_edge_case_no_feasible_solution_safeguard() -> None:
    """When an impossible safety threshold is required, engine refuses to deploy unsafe configs."""
    engine = OptimizationEngine()
    registry = get_default_variable_registry()

    base_cfg = create_configuration({"temperature": 0.7})
    prob = OptimizationProblem(
        name="Impossible Safety Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90},
        variables=[registry.get("temperature")],
        objectives=[OptimizationObjective(objective_id="quality", metric="quality")],
        constraints=[
            OptimizationConstraint(
                constraint_id="impossible_safety",
                metric="safety",
                operator=ConstraintOperator.GE,
                threshold=1.50,  # Impossible threshold > 1.0!
                is_hard=True,
            )
        ],
    )

    result = engine.run(
        problem=prob,
        budget=OptimizationBudget(max_candidates=4),
        strategy="random",
    )

    assert result.stopping_reason == StoppingReason.NO_FEASIBLE_CONFIGURATION
    assert result.selected_candidate is None
    assert len(result.pareto_frontier.non_dominated_candidate_ids) == 0


def test_budget_exhaustion_early_stopping() -> None:
    """Test optimization engine halts immediately when candidate or evaluation budget is exhausted."""
    engine = OptimizationEngine()
    registry = get_default_variable_registry()

    base_cfg = create_configuration({"temperature": 0.5, "top_k": 5})
    prob = OptimizationProblem(
        name="Budget Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90},
        variables=[registry.get("temperature"), registry.get("top_k")],
        objectives=[OptimizationObjective(objective_id="quality", metric="quality")],
    )

    # Extremely tight budget: max 2 evaluations
    budget = OptimizationBudget(max_candidates=10, max_evaluations=2)
    result = engine.run(
        problem=prob,
        budget=budget,
        strategy="random",
    )

    assert result.stopping_reason == StoppingReason.BUDGET_EXHAUSTED
    assert len(result.candidates) <= 2
