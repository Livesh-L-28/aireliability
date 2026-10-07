"""Unit tests for Phase 37 HealingPolicy and ApprovalManager."""

from aireliability.remediation.approval import ApprovalManager
from aireliability.remediation.models import (
    GateEvaluationResult,
    HealingPolicyConfig,
    RemediationLifecycleState,
    RemediationProposal,
    RemediationRiskTier,
    RepairType,
)
from aireliability.remediation.policy import HealingPolicy


def test_healing_policy_rejects_failed_gates() -> None:
    """Healing policy transitions proposal to REJECTED if gates failed."""
    policy = HealingPolicy()
    gates = GateEvaluationResult(
        gates_passed=False,
        failed_gate_reasons=["Regressions detected"],
    )
    proposal = RemediationProposal(
        title="Failed Proposal",
        repair_type=RepairType.CONFIG,
        gate_evaluation=gates,
    )

    allowed = policy.evaluate_policy(proposal)
    assert allowed is False
    assert proposal.state == RemediationLifecycleState.REJECTED


def test_healing_policy_mandates_approval_for_high_risk() -> None:
    """Healing policy requires operator approval for HIGH and CRITICAL risk patches."""
    policy = HealingPolicy(HealingPolicyConfig(auto_heal_enabled=True))
    gates = GateEvaluationResult(gates_passed=True)
    proposal = RemediationProposal(
        title="High Risk Safety Patch",
        repair_type=RepairType.SAFETY,
        risk_tier=RemediationRiskTier.HIGH,
        gate_evaluation=gates,
    )

    allowed = policy.evaluate_policy(proposal)
    assert allowed is False
    assert proposal.state == RemediationLifecycleState.NEEDS_APPROVAL


def test_healing_policy_auto_approves_low_risk_when_enabled() -> None:
    """Healing policy automatically approves low-risk proposals when auto-heal is enabled."""
    config = HealingPolicyConfig(
        auto_heal_enabled=True,
        allowed_auto_risk_tiers=[RemediationRiskTier.LOW],
    )
    policy = HealingPolicy(config)
    gates = GateEvaluationResult(gates_passed=True)
    proposal = RemediationProposal(
        title="Low Risk Prompt Fix",
        repair_type=RepairType.PROMPT,
        risk_tier=RemediationRiskTier.LOW,
        gate_evaluation=gates,
    )

    allowed = policy.evaluate_policy(proposal)
    assert allowed is True
    assert proposal.state == RemediationLifecycleState.APPROVED
    assert proposal.approval is not None
    assert proposal.approval.approver == "policy_engine:auto_heal"


def test_approval_manager_approves_and_generates_token() -> None:
    """ApprovalManager transitions proposal to APPROVED with a valid HMAC token."""
    manager = ApprovalManager()
    proposal = RemediationProposal(
        title="Pending Proposal",
        repair_type=RepairType.TOOL,
        state=RemediationLifecycleState.NEEDS_APPROVAL,
    )

    record = manager.approve(proposal, approver="alice", rationale="Sign-off verified")
    assert proposal.state == RemediationLifecycleState.APPROVED
    assert record.approved is True
    assert record.approver == "alice"
    assert len(record.approval_token) == 24


def test_approval_manager_rejects() -> None:
    """ApprovalManager transitions proposal to REJECTED."""
    manager = ApprovalManager()
    proposal = RemediationProposal(
        title="Rejected Proposal",
        repair_type=RepairType.TOOL,
        state=RemediationLifecycleState.NEEDS_APPROVAL,
    )

    record = manager.reject(proposal, approver="bob", reason="Too risky for production")
    assert proposal.state == RemediationLifecycleState.REJECTED
    assert record.approved is False
    assert record.approver == "bob"
