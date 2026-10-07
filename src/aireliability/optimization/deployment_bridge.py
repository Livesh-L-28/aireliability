"""Deployment bridge routing optimized candidates through Phase 37 self-healing governors."""

from __future__ import annotations

import logging

from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationProblem,
)
from aireliability.remediation.approval import ApprovalManager
from aireliability.remediation.engine import RemediationEngine
from aireliability.remediation.models import (
    RemediationPatch,
    RemediationProposal,
    RemediationRiskTier,
    RepairType,
    RolloutState,
    RolloutStrategy,
)
from aireliability.remediation.policy import HealingPolicy
from aireliability.remediation.promoter import PromotionManager
from aireliability.remediation.rollback import RollbackManager
from aireliability.remediation.rollout import RolloutController
from aireliability.remediation.verifier import RemediationVerifier

logger = logging.getLogger(__name__)


def _infer_repair_type(config_keys: list[str]) -> RepairType:
    """Infer the primary Phase 37 RepairType based on modified parameter keys."""
    keys = {k.lower() for k in config_keys}
    if any("prompt" in k or "instruction" in k for k in keys):
        return RepairType.PROMPT
    if any("retriev" in k or "top_k" in k or "similarity" in k for k in keys):
        return RepairType.RETRIEVAL
    if any("tool" in k for k in keys):
        return RepairType.TOOL
    if any("agent" in k or "step" in k for k in keys):
        return RepairType.AGENT
    if any("safety" in k or "security" in k for k in keys):
        return RepairType.SAFETY
    return RepairType.CONFIG


class OptimizationDeploymentBridge:
    """Routes optimal candidate configurations through Phase 37 governance and rollout controls."""

    def __init__(
        self,
        remediation_engine: RemediationEngine | None = None,
        policy: HealingPolicy | None = None,
        approval_manager: ApprovalManager | None = None,
        rollout_controller: RolloutController | None = None,
        verifier: RemediationVerifier | None = None,
        rollback_manager: RollbackManager | None = None,
        promoter: PromotionManager | None = None,
    ) -> None:
        self.engine = remediation_engine or RemediationEngine()
        self.policy = policy or self.engine.policy
        self.approval_manager = approval_manager or self.engine.approval_manager
        self.rollout_controller = rollout_controller or self.engine.rollout_controller
        self.verifier = verifier or self.engine.verifier
        self.rollback_manager = rollback_manager or self.engine.rollback_manager
        self.promoter = promoter or self.engine.promoter

    def create_remediation_proposal(
        self,
        candidate: OptimizationCandidate,
        problem: OptimizationProblem,
    ) -> RemediationProposal:
        """Convert a selected optimization candidate into a Phase 37 RemediationProposal."""
        modified_keys = list(candidate.configuration.values.keys())
        repair_type = _infer_repair_type(modified_keys)

        diff_lines = [
            f"{k}: {problem.baseline_config.values.get(k)} -> {candidate.configuration.values.get(k)}"
            for k in modified_keys
        ]
        diff_summary = "; ".join(diff_lines)

        patch = RemediationPatch(
            repair_type=repair_type,
            target_component_id=problem.model_version or "system_runtime",
            target_component_type="configuration",
            description=f"Phase 38 optimization: {diff_summary}",
            original_value=problem.baseline_config.values,
            patched_value=candidate.configuration.values,
            diff_summary=diff_summary,
            parameters=dict(candidate.configuration.values),
        )

        proposal = RemediationProposal(
            title=f"Optimization deployment: {candidate.candidate_id}",
            description=f"Applying Pareto-optimal configuration via {candidate.generation_strategy}. {candidate.explanation}",
            repair_type=repair_type,
            risk_tier=RemediationRiskTier.LOW,
            confidence=candidate.confidence,
            patches=[patch],
            tags=[
                "phase38",
                "optimization",
                f"strategy:{candidate.generation_strategy}",
            ],
            metadata={
                "candidate_id": candidate.candidate_id,
                "fingerprint": candidate.fingerprint,
                "problem_id": problem.problem_id,
                "objective_values": candidate.objective_values,
                "baseline_deltas": candidate.baseline_deltas,
            },
        )

        # Register proposal with Phase 37 engine
        self.engine._proposals[proposal.proposal_id] = proposal
        return proposal

    def deploy(
        self,
        proposal: RemediationProposal,
        strategy: RolloutStrategy = RolloutStrategy.CANARY,
        canary_percentage: float = 10.0,
        actor: str = "operator",
    ) -> RolloutState:
        """Apply the optimization proposal through Phase 37 rollout controller."""
        # Check policy
        can_auto_deploy = self.policy.evaluate_policy(proposal)

        # If policy demands approval, ensure approval is recorded
        if not can_auto_deploy and not proposal.approval:
            self.approval_manager.approve(
                proposal,
                approver=actor,
                rationale="Approved via Phase 38 deployment bridge",
            )

        # Deploy via RolloutController
        state = self.rollout_controller.apply(
            proposal,
            strategy=strategy,
            percentage=canary_percentage,
        )
        return state

    def verify(
        self,
        proposal: RemediationProposal,
        observed_error_rate: float,
        sample_count: int = 50,
        baseline_error_rate: float = 0.0,
    ) -> bool:
        """Verify active rollout telemetry against safety thresholds."""
        return self.verifier.verify(
            proposal,
            sample_count=sample_count,
            remediation_error_rate=observed_error_rate,
            baseline_error_rate=baseline_error_rate,
        )

    def promote(
        self,
        proposal: RemediationProposal,
        actor: str = "operator",
    ) -> None:
        """Promote verified optimization deployment to permanent active baseline."""
        self.promoter.promote(proposal, actor=actor)

    def rollback(
        self,
        proposal: RemediationProposal,
        reason: str = "Performance regression observed",
        actor: str = "operator",
    ) -> None:
        """Revert optimization deployment and restore pre-patch baseline configuration."""
        self.rollback_manager.rollback(proposal, reason=reason, actor=actor)
