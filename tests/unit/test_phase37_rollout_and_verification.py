"""Unit tests for Phase 37 rollout controller, telemetry verifier, promoter, and rollback."""

from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationProposal,
    RolloutHealthStatus,
    RolloutStrategy,
)
from aireliability.remediation.promoter import PromotionManager
from aireliability.remediation.rollback import RollbackManager
from aireliability.remediation.rollout import RolloutController
from aireliability.remediation.verifier import RemediationVerifier


def test_rollout_controller_direct_and_canary() -> None:
    """RolloutController applies DIRECT and CANARY deployments appropriately."""
    controller = RolloutController()
    proposal = RemediationProposal(
        title="Approved Proposal",
        repair_type="prompt_repair",
        state=RemediationLifecycleState.APPROVED,
    )

    # 1. Canary application
    rstate = controller.apply(
        proposal, strategy=RolloutStrategy.CANARY, percentage=15.0
    )
    assert proposal.state == RemediationLifecycleState.CANARY
    assert rstate.active_percentage == 15.0
    assert rstate.strategy == RolloutStrategy.CANARY

    # 2. Test consistent routing hash
    assert controller.should_route_to_canary("req_1", 100.0) is True
    assert controller.should_route_to_canary("req_1", 0.0) is False


def test_verifier_marks_healthy_and_updates_lifecycle() -> None:
    """Verifier transitions CANARY proposal to VERIFIED when telemetry is sound."""
    verifier = RemediationVerifier(max_allowed_error_rate=0.05, min_samples=10)
    proposal = RemediationProposal(
        title="Canary Proposal",
        repair_type="prompt_repair",
        state=RemediationLifecycleState.CANARY,
    )

    # First attempt: Insufficient samples
    healthy_low_samples = verifier.verify(
        proposal, sample_count=5, remediation_error_rate=0.01
    )
    assert healthy_low_samples is False
    assert proposal.state == RemediationLifecycleState.CANARY

    # Second attempt: Sufficient samples and low error rate
    healthy_verified = verifier.verify(
        proposal, sample_count=20, remediation_error_rate=0.01
    )
    assert healthy_verified is True
    assert proposal.state == RemediationLifecycleState.VERIFIED
    assert proposal.rollout_state.health_status == RolloutHealthStatus.HEALTHY


def test_verifier_flags_degradation() -> None:
    """Verifier flags CRITICAL health when error rate exceeds safety threshold."""
    verifier = RemediationVerifier(max_allowed_error_rate=0.05)
    proposal = RemediationProposal(
        title="Canary Proposal",
        repair_type="prompt_repair",
        state=RemediationLifecycleState.CANARY,
    )

    healthy = verifier.verify(proposal, sample_count=25, remediation_error_rate=0.12)
    assert healthy is False
    assert proposal.rollout_state.health_status == RolloutHealthStatus.CRITICAL


def test_promotion_manager() -> None:
    """PromotionManager promotes VERIFIED proposal to 100% active PROMOTED baseline."""
    promoter = PromotionManager()
    proposal = RemediationProposal(
        title="Verified Proposal",
        repair_type="prompt_repair",
        state=RemediationLifecycleState.VERIFIED,
    )

    promoter.promote(proposal, actor="operator:bob", notes="Live verification complete")
    assert proposal.state == RemediationLifecycleState.PROMOTED
    assert proposal.rollout_state.active_percentage == 100.0
    assert proposal.rollout_state.promoted_at is not None


def test_rollback_manager() -> None:
    """RollbackManager reverts active proposal to ROLLED_BACK."""
    rollback_mgr = RollbackManager()
    proposal = RemediationProposal(
        title="Active Proposal",
        repair_type="prompt_repair",
        state=RemediationLifecycleState.CANARY,
    )

    success = rollback_mgr.rollback(
        proposal, reason="Degradation spike detected", actor="watchdog"
    )
    assert success is True
    assert proposal.state == RemediationLifecycleState.ROLLED_BACK
    assert proposal.rollout_state.active_percentage == 0.0
    assert proposal.rollout_state.health_status == RolloutHealthStatus.CRITICAL
