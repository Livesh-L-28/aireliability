"""Integration tests validating the complete end-to-end Self-Healing Reliability Engine loop."""

from aireliability.core.models import FailureReport
from aireliability.graph.graph import KnowledgeGraph
from aireliability.graph.models import GraphNode, GraphNodeType, GraphRelationship
from aireliability.intelligence.models import (
    ConfidenceLevel,
    IntelligenceConfidence,
    ReliabilityRecommendation,
)
from aireliability.remediation.engine import RemediationEngine
from aireliability.remediation.models import (
    HealingPolicyConfig,
    RemediationLifecycleState,
    RemediationRiskTier,
    RepairType,
    RolloutHealthStatus,
    RolloutStrategy,
)
from aireliability.remediation.policy import HealingPolicy


def test_end_to_end_closed_loop_promotion_workflow() -> None:
    """Full lifecycle from failure evidence to canary verification and baseline promotion."""
    engine = RemediationEngine()
    graph = KnowledgeGraph()

    # Step 1: Detect Failure Evidence
    failure = FailureReport(
        failure_id="fail_prod_404",
        trace_id="tr_prod_404",
        category="retrieval",
        message="retrieval failure: top_k too low, customer query returned 0 documents",
    )
    fail_node = GraphNode.create(
        node_type=GraphNodeType.FAILURE,
        source_id="fail_prod_404",
        name="Retriever Underflow Failure",
    )
    graph.add_node(fail_node)

    # Step 2: Diagnosis & Planning (Generates Patches and Phase 36 Tests)
    proposal = engine.diagnose_and_plan(
        failure,
        context={"target_component": "faq_retriever"},
    )
    assert proposal.repair_type == RepairType.RETRIEVAL
    assert proposal.state == RemediationLifecycleState.PROPOSED
    assert len(proposal.patches) > 0
    assert len(proposal.generated_test_ids) > 0

    # Step 3: Simulation Sandbox Execution
    sim_result = engine.simulate(
        proposal, baseline_test_cases=["golden_regression_test_1"]
    )
    assert sim_result.passed is True
    assert proposal.gate_evaluation is not None
    assert proposal.gate_evaluation.gates_passed is True

    # Step 4: Approval Flow
    assert proposal.state == RemediationLifecycleState.NEEDS_APPROVAL
    appr = engine.approve(proposal, approver="alice", rationale="Verified in staging")
    assert proposal.state == RemediationLifecycleState.APPROVED
    assert appr.approved is True

    # Step 5: Rollout (Canary Deployment)
    rollout_state = engine.apply(
        proposal, strategy=RolloutStrategy.CANARY, percentage=10.0
    )
    assert proposal.state == RemediationLifecycleState.CANARY
    assert rollout_state.active_percentage == 10.0

    # Step 6: Verification
    is_healthy = engine.verify(
        proposal,
        sample_count=50,
        remediation_error_rate=0.005,
        baseline_error_rate=0.01,
    )
    assert is_healthy is True
    assert proposal.state == RemediationLifecycleState.VERIFIED

    # Step 7: Promotion to Permanent Baseline
    promoted = engine.promote(
        proposal, actor="alice", notes="Promotion verified 0 regressions"
    )
    assert promoted is True
    assert proposal.state == RemediationLifecycleState.PROMOTED
    assert proposal.rollout_state.active_percentage == 100.0

    # Step 8: Knowledge Graph & Audit Synchronization
    rem_node = engine.sync_to_graph(proposal, graph)
    assert graph.has_node(rem_node.node_id) is True

    # Validate graph relationships
    remedy_edges = graph.list_edges(
        source_node_id=fail_node.node_id, target_node_id=rem_node.node_id
    )
    assert len(remedy_edges) == 1
    assert remedy_edges[0].relationship_type == GraphRelationship.RECOMMENDS


def test_end_to_end_auto_rollback_on_degraded_telemetry() -> None:
    """Degraded canary telemetry triggers automated rollback and returns to pre-patch state."""
    engine = RemediationEngine()
    failure = FailureReport(
        failure_id="fail_perf_100",
        trace_id="tr_perf_100",
        category="performance",
        message="timeout in model execution",
    )
    proposal = engine.diagnose_and_plan(failure)
    engine.simulate(proposal)
    engine.approve(proposal, approver="ops_lead")
    engine.apply(proposal, strategy=RolloutStrategy.CANARY, percentage=10.0)

    # Telemetry registers high error rate (18% errors vs 5% max allowed)
    verified = engine.verify(
        proposal,
        sample_count=40,
        remediation_error_rate=0.18,
        baseline_error_rate=0.02,
    )
    assert verified is False
    assert proposal.state == RemediationLifecycleState.ROLLED_BACK
    assert proposal.rollout_state.active_percentage == 0.0
    assert proposal.rollout_state.health_status == RolloutHealthStatus.CRITICAL
    assert "Degradation detected" in proposal.audit_trail[-1].reason


def test_intelligence_cluster_and_recommendation_healing() -> None:
    """Intelligence recommendations trigger targeted auto-remediation when policy permits."""
    # Policy configured for autonomous low-risk healing
    policy = HealingPolicy(
        HealingPolicyConfig(
            auto_heal_enabled=True,
            allowed_auto_risk_tiers=[RemediationRiskTier.LOW],
        )
    )
    engine = RemediationEngine(policy=policy)

    rec = ReliabilityRecommendation(
        title="Prompt Schema Clarification",
        description="Instruction compliance failure: model occasionally omits keys",
        suggested_action="Append JSON format constraint",
        rationale="Recurring format syntax errors detected across test runs",
        affected_components=["order_processing_agent"],
        confidence=IntelligenceConfidence(score=0.95, level=ConfidenceLevel.VERY_HIGH),
    )

    proposal = engine.diagnose_and_plan(
        rec, context={"target_component": "order_processing_agent"}
    )
    assert proposal.repair_type == RepairType.PROMPT
    assert proposal.risk_tier == RemediationRiskTier.LOW

    # Simulate
    engine.simulate(proposal)

    # HealingPolicy auto-approved because it's low risk and auto_heal_enabled
    assert proposal.state == RemediationLifecycleState.APPROVED
    assert proposal.approval is not None
    assert proposal.approval.approver == "policy_engine:auto_heal"

    # Auto-apply direct in staging
    engine.apply(proposal, strategy=RolloutStrategy.DIRECT)
    assert proposal.state == RemediationLifecycleState.ACTIVE
    assert proposal.rollout_state.active_percentage == 100.0
