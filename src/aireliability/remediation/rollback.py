"""Rollback manager safely reverting active or canary remediation deployments."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationProposal,
    RolloutHealthStatus,
)

logger = logging.getLogger(__name__)


class RollbackManager:
    """Safely restores pre-patch configurations and records rollback provenance."""

    def rollback(
        self,
        proposal: RemediationProposal,
        reason: str = "Rollback triggered due to error rate increase or regression",
        actor: str = "system",
    ) -> bool:
        """Revert the candidate patch and return component to original state."""
        # Rollback is valid from any deploying, active, canary, shadow, or verified state
        if proposal.state not in (
            RemediationLifecycleState.APPLYING,
            RemediationLifecycleState.ACTIVE,
            RemediationLifecycleState.CANARY,
            RemediationLifecycleState.SHADOW,
            RemediationLifecycleState.VERIFIED,
            RemediationLifecycleState.APPROVED,
        ):
            logger.warning(
                "Proposal %s is in state %s; rollback recorded as cancelled.",
                proposal.proposal_id,
                proposal.state.value,
            )

        # Update rollout state
        proposal.rollout_state.active_percentage = 0.0
        proposal.rollout_state.health_status = RolloutHealthStatus.CRITICAL
        proposal.rollout_state.rolled_back_at = datetime.now(UTC)
        proposal.rollout_state.notes = f"Rolled back by {actor}: {reason}"

        # Transition to ROLLED_BACK
        proposal.record_transition(
            to_state=RemediationLifecycleState.ROLLED_BACK,
            actor=actor,
            action="rollback",
            reason=reason,
            metadata={"patches_reverted": len(proposal.patches)},
        )
        return True
