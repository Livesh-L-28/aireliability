"""Promotion manager safely establishing verified remediation patches as permanent baselines."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationProposal,
    RolloutHealthStatus,
)

logger = logging.getLogger(__name__)


class PromotionManager:
    """Promotes verified remediation proposals to 100% active production baselines."""

    def promote(
        self,
        proposal: RemediationProposal,
        actor: str = "system",
        notes: str = "Remediation verified and promoted to permanent baseline",
    ) -> bool:
        """Promote a verified proposal to the final PROMOTED state."""
        if proposal.state != RemediationLifecycleState.VERIFIED:
            raise ValueError(
                f"Cannot promote proposal {proposal.proposal_id} in state {proposal.state.value}. Proposal must be in VERIFIED state."
            )

        now = datetime.now(UTC)
        proposal.rollout_state.active_percentage = 100.0
        proposal.rollout_state.health_status = RolloutHealthStatus.HEALTHY
        proposal.rollout_state.promoted_at = now
        proposal.rollout_state.notes = notes

        proposal.record_transition(
            to_state=RemediationLifecycleState.PROMOTED,
            actor=actor,
            action="promote",
            reason=notes,
            metadata={"promoted_at": now.isoformat()},
        )
        return True
