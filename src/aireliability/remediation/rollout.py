"""Rollout controller executing direct, shadow, and canary deployment strategies."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationProposal,
    RolloutHealthStatus,
    RolloutState,
    RolloutStrategy,
)

logger = logging.getLogger(__name__)


class RolloutController:
    """Manages progressive deployment and traffic routing for approved remediations."""

    def should_route_to_canary(self, request_id: str, percentage: float) -> bool:
        """Deterministic consistent hashing to route requests to the canary deployment."""
        if percentage <= 0.0:
            return False
        if percentage >= 100.0:
            return True
        hash_val = int(hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:8], 16)
        bucket = hash_val % 100
        return bucket < percentage

    def apply(
        self,
        proposal: RemediationProposal,
        strategy: RolloutStrategy | None = None,
        percentage: float | None = None,
    ) -> RolloutState:
        """Apply the approved remediation proposal using the specified rollout strategy."""
        if proposal.state not in (
            RemediationLifecycleState.APPROVED,
            RemediationLifecycleState.ACTIVE,
            RemediationLifecycleState.CANARY,
            RemediationLifecycleState.SHADOW,
        ):
            raise ValueError(
                f"Cannot apply proposal {proposal.proposal_id} in state {proposal.state.value}. Proposal must be APPROVED."
            )

        chosen_strategy = strategy or proposal.rollout_config.strategy
        initial_pct = (
            percentage
            if percentage is not None
            else (
                100.0
                if chosen_strategy == RolloutStrategy.DIRECT
                else proposal.rollout_config.initial_percentage
            )
        )

        proposal.record_transition(
            to_state=RemediationLifecycleState.APPLYING,
            action="apply_rollout",
            reason=f"Applying rollout using {chosen_strategy.value} strategy at {initial_pct}%",
        )

        target_state = (
            RemediationLifecycleState.ACTIVE
            if chosen_strategy == RolloutStrategy.DIRECT
            else RemediationLifecycleState.SHADOW
            if chosen_strategy == RolloutStrategy.SHADOW
            else RemediationLifecycleState.CANARY
        )

        rollout_state = RolloutState(
            strategy=chosen_strategy,
            active_percentage=initial_pct,
            health_status=RolloutHealthStatus.HEALTHY,
            baseline_error_rate=0.0,
            remediation_error_rate=0.0,
            applied_at=datetime.now(UTC),
            notes=f"Active rollout on {chosen_strategy.value}",
        )
        proposal.rollout_state = rollout_state

        proposal.record_transition(
            to_state=target_state,
            action="rollout_active",
            reason=f"Rollout active in {target_state.value} mode at {initial_pct}% traffic",
        )
        return rollout_state
