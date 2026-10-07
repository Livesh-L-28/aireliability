"""Healing policy engine governing autonomous remediation execution boundaries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from aireliability.remediation.models import (
    ApprovalRecord,
    HealingPolicyConfig,
    RemediationLifecycleState,
    RemediationProposal,
    RemediationRiskTier,
)

logger = logging.getLogger(__name__)


class HealingPolicy:
    """Enforces organizational safety, risk tiers, and auto-healing constraints."""

    def __init__(self, config: HealingPolicyConfig | None = None) -> None:
        self.config = config or HealingPolicyConfig()
        self._recent_rollout_timestamps: list[datetime] = []

    def check_rate_limit(self) -> bool:
        """Verify that rollout frequency does not exceed max_rollouts_per_hour."""
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        self._recent_rollout_timestamps = [
            t for t in self._recent_rollout_timestamps if t > cutoff
        ]
        return len(self._recent_rollout_timestamps) < self.config.max_rollouts_per_hour

    def record_rollout(self) -> None:
        """Record a rollout event timestamp for rate limiting."""
        self._recent_rollout_timestamps.append(datetime.now(UTC))

    def evaluate_policy(self, proposal: RemediationProposal) -> bool:
        """Determine whether the proposal can be auto-approved or requires human sign-off.

        Returns:
            True if approved (either auto or already signed), False if requires approval or rejected.
        """
        # If gates didn't pass, reject
        if proposal.gate_evaluation and not proposal.gate_evaluation.gates_passed:
            proposal.record_transition(
                to_state=RemediationLifecycleState.REJECTED,
                action="reject_by_gates",
                reason=f"Evaluation gates failed: {'; '.join(proposal.gate_evaluation.failed_gate_reasons)}",
            )
            return False

        # If rate limit exceeded, require approval/hold
        if not self.check_rate_limit():
            proposal.record_transition(
                to_state=RemediationLifecycleState.NEEDS_APPROVAL,
                action="hold_rate_limit",
                reason=f"Max rollouts per hour ({self.config.max_rollouts_per_hour}) reached.",
            )
            return False

        # Check high-risk requirements
        is_high_risk = proposal.risk_tier in (
            RemediationRiskTier.HIGH,
            RemediationRiskTier.CRITICAL,
        )
        if self.config.require_approval_for_high_risk and is_high_risk:
            proposal.record_transition(
                to_state=RemediationLifecycleState.NEEDS_APPROVAL,
                action="require_high_risk_approval",
                reason=f"Risk tier {proposal.risk_tier.value} mandates human reviewer approval.",
            )
            return False

        # Check auto-heal toggle and allowed tiers
        can_auto_heal = (
            self.config.auto_heal_enabled
            and proposal.risk_tier in self.config.allowed_auto_risk_tiers
        )

        if can_auto_heal:
            # Policy auto-approves
            approval = ApprovalRecord(
                approver="policy_engine:auto_heal",
                approved=True,
                approval_token="auto_policy_token",
                rationale="Auto-heal policy granted approval for low-risk remediation with passing gates.",
            )
            proposal.approval = approval
            proposal.record_transition(
                to_state=RemediationLifecycleState.APPROVED,
                actor="policy_engine",
                action="auto_approve",
                reason=approval.rationale,
            )
            return True

        # Default fallback: requires human approval
        proposal.record_transition(
            to_state=RemediationLifecycleState.NEEDS_APPROVAL,
            action="require_operator_approval",
            reason="Standard healing policy requires human operator sign-off.",
        )
        return False
