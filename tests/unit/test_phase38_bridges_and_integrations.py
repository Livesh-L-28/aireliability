"""Unit tests for Phase 36, Phase 37, Knowledge Graph, and Observability bridges."""

from __future__ import annotations

from aireliability.graph.graph import KnowledgeGraph
from aireliability.observability.manager import ObservabilityManager
from aireliability.optimization.deployment_bridge import OptimizationDeploymentBridge
from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.graph_bridge import OptimizationGraphBridge
from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationObjective,
    OptimizationProblem,
    OptimizationResult,
    ParetoFrontier,
    StoppingReason,
)
from aireliability.optimization.observability_bridge import (
    OptimizationObservabilityBridge,
)
from aireliability.optimization.test_bridge import OptimizationTestBridge
from aireliability.remediation.models import (
    RemediationLifecycleState,
    RepairType,
    RolloutStrategy,
)


def _build_test_context() -> tuple[
    OptimizationProblem, OptimizationCandidate, OptimizationResult
]:
    base_cfg = create_configuration({"temperature": 0.7, "top_k": 5})
    prob = OptimizationProblem(
        name="Integration Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "cost": 0.02},
        objectives=[
            OptimizationObjective(objective_id="quality", metric="quality"),
            OptimizationObjective(objective_id="cost", metric="cost"),
        ],
    )

    cand_cfg = create_configuration({"temperature": 0.4, "top_k": 8})
    cand = OptimizationCandidate(
        candidate_id="cand_bridge_1",
        configuration=cand_cfg,
        fingerprint=cand_cfg.fingerprint,
        objective_values={
            "quality": 0.95,
            "cost": 0.015,
            "safety": 0.98,
            "security": 0.99,
        },
        is_pareto=True,
    )

    frontier = ParetoFrontier(
        points=[],
        objective_ids=["quality", "cost"],
        non_dominated_candidate_ids=["cand_bridge_1"],
        dominated_candidate_ids=[],
    )

    res = OptimizationResult(
        problem=prob,
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "cost": 0.02},
        candidates=[cand],
        pareto_frontier=frontier,
        selected_candidate=cand,
        stopping_reason=StoppingReason.COMPLETED,
    )
    return prob, cand, res


def test_phase36_test_bridge() -> None:
    """Test requesting Phase 36 test generation for modified parameters."""
    prob, cand, _ = _build_test_context()
    bridge = OptimizationTestBridge()

    tests = bridge.request_validation_tests(cand, prob, max_tests=2)
    assert isinstance(tests, list)


def test_phase37_deployment_bridge_canary_and_verify() -> None:
    """Test converting candidate to RemediationProposal, deploying canary, and verifying."""
    prob, cand, _ = _build_test_context()
    bridge = OptimizationDeploymentBridge()

    # 1. Create Proposal
    proposal = bridge.create_remediation_proposal(cand, prob)
    assert proposal.repair_type in (RepairType.CONFIG, RepairType.RETRIEVAL)
    assert len(proposal.patches) == 1
    assert proposal.patches[0].patched_value == cand.configuration.values

    # 2. Deploy Canary
    state = bridge.deploy(
        proposal, strategy=RolloutStrategy.CANARY, canary_percentage=15.0
    )
    assert state.strategy == RolloutStrategy.CANARY
    assert state.active_percentage == 15.0
    assert proposal.state == RemediationLifecycleState.CANARY

    # 3. Verify
    verified = bridge.verify(proposal, observed_error_rate=0.01, sample_count=50)
    assert verified is True
    assert proposal.state == RemediationLifecycleState.VERIFIED

    # 4. Promote
    bridge.promote(proposal, actor="test_runner")
    assert proposal.state == RemediationLifecycleState.PROMOTED


def test_phase37_deployment_bridge_rollback() -> None:
    """Test rolling back an optimization deployment via Phase 37 rollback manager."""
    prob, cand, _ = _build_test_context()
    bridge = OptimizationDeploymentBridge()

    proposal = bridge.create_remediation_proposal(cand, prob)
    bridge.deploy(proposal, strategy=RolloutStrategy.CANARY)

    bridge.rollback(proposal, reason="Degradation test", actor="operator")
    assert proposal.state == RemediationLifecycleState.ROLLED_BACK


def test_knowledge_graph_bridge_sync_and_query() -> None:
    """Test synchronizing run, baseline, and candidates to Knowledge Graph and querying history."""
    prob, cand, res = _build_test_context()
    graph = KnowledgeGraph()
    bridge = OptimizationGraphBridge(graph=graph)

    bridge.sync_optimization_result(res)

    # Graph should have nodes: Run, Baseline, Candidate, Metrics
    assert len(graph.list_nodes()) >= 3
    assert len(graph.list_edges()) >= 2

    # Query historical
    history_cands = bridge.query_historical_candidates(prob)
    assert len(history_cands) >= 1
    assert history_cands[0]["configuration"] == cand.configuration.values


def test_observability_bridge_metrics() -> None:
    """Test observability bridge emits metrics without exceptions."""
    prob, cand, res = _build_test_context()
    obs_manager = ObservabilityManager()
    bridge = OptimizationObservabilityBridge(manager=obs_manager)

    bridge.record_run_started("prob_1", strategy="random")
    bridge.record_candidate_generated("random")
    bridge.record_evaluation("cand_1", 0.12)
    bridge.record_run_completed(res)
    bridge.record_deployment("canary")
    bridge.record_rollback("regression")

    # Metrics should be recorded in in-memory metrics engine
    assert len(obs_manager.metrics.counters) > 0
    prom_str = obs_manager.metrics.render_prometheus()
    assert "optimization_runs_total" in prom_str
