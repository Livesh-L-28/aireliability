"""Verification monitor evaluating live health and telemetry during remediation rollouts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationProposal,
    RolloutHealthStatus,
)

logger = logging.getLogger(__name__)


class RemediationVerifier:
    """Evaluates telemetry of active canary or shadow deployments to verify reliability."""

    def __init__(
        self,
        max_allowed_error_rate: float = 0.05,
        max_error_rate_delta: float = 0.02,
        min_samples: int = 10,
    ) -> None:
        self.max_allowed_error_rate = max_allowed_error_rate
        self.max_error_rate_delta = max_error_rate_delta
        self.min_samples = min_samples

    def verify(
        self,
        proposal: RemediationProposal,
        sample_count: int,
        remediation_error_rate: float,
        baseline_error_rate: float = 0.0,
    ) -> bool:
        """Evaluate real-time rollout telemetry and update lifecycle state.

        Returns:
            True if rollout is verified healthy; False if degraded or insufficient data.
        """
        state = proposal.rollout_state
        state.sample_count = sample_count
        state.remediation_error_rate = remediation_error_rate
        state.baseline_error_rate = baseline_error_rate

        # Check for critical degradation
        error_delta = remediation_error_rate - baseline_error_rate
        is_failing = (
            remediation_error_rate > self.max_allowed_error_rate
            or error_delta > self.max_error_rate_delta
        )

        if is_failing:
            state.health_status = RolloutHealthStatus.CRITICAL
            state.notes = (
                f"Degradation detected: error rate {remediation_error_rate:.2%} "
                f"exceeds allowed limit ({self.max_allowed_error_rate:.2%})."
            )
            return False

        if sample_count < self.min_samples:
            state.health_status = RolloutHealthStatus.HEALTHY
            state.notes = f"Observation in progress ({sample_count}/{self.min_samples} samples collected)."
            return False

        # Sufficient samples and healthy error rate
        state.health_status = RolloutHealthStatus.HEALTHY
        state.verified_at = datetime.now(UTC)
        state.notes = f"Verification successful with {sample_count} samples (error rate: {remediation_error_rate:.2%})."

        if proposal.state in (
            RemediationLifecycleState.CANARY,
            RemediationLifecycleState.SHADOW,
            RemediationLifecycleState.ACTIVE,
        ):
            proposal.record_transition(
                to_state=RemediationLifecycleState.VERIFIED,
                action="verify_rollout",
                reason=state.notes,
                metadata={
                    "sample_count": sample_count,
                    "remediation_error_rate": remediation_error_rate,
                    "baseline_error_rate": baseline_error_rate,
                },
            )
        return True
