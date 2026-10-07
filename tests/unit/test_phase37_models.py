"""Unit tests for Phase 37 Self-Healing models, lifecycle states, and audit trails."""

from aireliability.remediation.models import (
    GateEvaluationResult,
    HealingPolicyConfig,
    RemediationLifecycleState,
    RemediationPatch,
    RemediationProposal,
    RemediationRiskTier,
    RepairType,
    RolloutStrategy,
    SimulationResult,
)


def test_repair_types_taxonomy() -> None:
    """Verify all 6 repair domain types are defined."""
    assert RepairType.PROMPT == "prompt_repair"
    assert RepairType.RETRIEVAL == "retrieval_repair"
    assert RepairType.TOOL == "tool_repair"
    assert RepairType.AGENT == "agent_repair"
    assert RepairType.CONFIG == "config_repair"
    assert RepairType.SAFETY == "safety_repair"
    assert len(RepairType) == 6


def test_remediation_lifecycle_states() -> None:
    """Verify lifecycle state taxonomy."""
    expected_states = {
        "PROPOSED",
        "SIMULATING",
        "SIMULATED",
        "NEEDS_APPROVAL",
        "APPROVED",
        "REJECTED",
        "APPLYING",
        "CANARY",
        "SHADOW",
        "ACTIVE",
        "VERIFIED",
        "PROMOTED",
        "ROLLED_BACK",
    }
    actual_states = {s.value for s in RemediationLifecycleState}
    assert actual_states == expected_states


def test_rollout_strategy_and_risk_tiers() -> None:
    """Verify rollout strategies and risk tier taxonomies."""
    assert RolloutStrategy.DIRECT == "DIRECT"
    assert RolloutStrategy.SHADOW == "SHADOW"
    assert RolloutStrategy.CANARY == "CANARY"

    assert RemediationRiskTier.LOW == "LOW"
    assert RemediationRiskTier.MEDIUM == "MEDIUM"
    assert RemediationRiskTier.HIGH == "HIGH"
    assert RemediationRiskTier.CRITICAL == "CRITICAL"


def test_remediation_patch_creation() -> None:
    """Verify patch creation with original and patched values."""
    patch = RemediationPatch(
        repair_type=RepairType.CONFIG,
        target_component_id="llm_runtime",
        target_component_type="config",
        description="Lower temperature for determinism",
        original_value={"temperature": 0.8},
        patched_value={"temperature": 0.1},
        diff_summary="temperature: 0.8 -> 0.1",
        parameters={"temperature": 0.1},
    )
    assert patch.patch_id.startswith("patch_")
    assert patch.repair_type == RepairType.CONFIG
    assert patch.original_value["temperature"] == 0.8
    assert patch.patched_value["temperature"] == 0.1


def test_proposal_lifecycle_and_audit_trail() -> None:
    """Verify proposal transitions maintain an immutable audit trail."""
    proposal = RemediationProposal(
        title="Prompt Formatting Fix",
        description="Enforces JSON output schema",
        repair_type=RepairType.PROMPT,
        risk_tier=RemediationRiskTier.LOW,
        confidence=0.98,
    )
    assert proposal.proposal_id.startswith("rem_")
    assert proposal.state == RemediationLifecycleState.PROPOSED
    assert len(proposal.audit_trail) == 0

    # 1. Transition to SIMULATING
    audit1 = proposal.record_transition(
        to_state=RemediationLifecycleState.SIMULATING,
        actor="simulator",
        action="start_sim",
        reason="Sandbox test execution",
    )
    assert proposal.state == RemediationLifecycleState.SIMULATING
    assert audit1.from_state == RemediationLifecycleState.PROPOSED
    assert audit1.to_state == RemediationLifecycleState.SIMULATING
    assert len(proposal.audit_trail) == 1

    # 2. Transition to APPROVED
    audit2 = proposal.record_transition(
        to_state=RemediationLifecycleState.APPROVED,
        actor="operator:alice",
        action="approve",
        reason="Manual sign-off",
    )
    assert proposal.state == RemediationLifecycleState.APPROVED
    assert len(proposal.audit_trail) == 2
    assert audit2.from_state == RemediationLifecycleState.SIMULATING


def test_simulation_and_gate_results() -> None:
    """Verify simulation result and gate evaluation data models."""
    sim = SimulationResult(
        passed=True,
        total_tests_run=10,
        tests_passed=10,
        tests_failed=0,
        regressions_count=0,
        failure_recovery_rate=1.0,
        summary="All tests passed",
    )
    assert sim.simulation_id.startswith("sim_")
    assert sim.passed is True
    assert sim.tests_passed == 10

    gates = GateEvaluationResult(
        gates_passed=True,
        zero_regression_passed=True,
        recovery_rate_passed=True,
        safety_passed=True,
        latency_passed=True,
    )
    assert gates.gates_passed is True
    assert len(gates.failed_gate_reasons) == 0


def test_healing_policy_config_defaults() -> None:
    """Verify default healing policy parameters are conservative."""
    cfg = HealingPolicyConfig()
    assert cfg.auto_heal_enabled is False
    assert cfg.require_approval_for_high_risk is True
    assert cfg.max_rollouts_per_hour == 5
    assert cfg.default_rollout_strategy == RolloutStrategy.CANARY
    assert cfg.default_canary_percentage == 10.0
