"""Unified Remediation Engine orchestrating the complete self-healing reliability lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from aireliability.graph.graph import KnowledgeGraph
from aireliability.remediation.approval import ApprovalManager
from aireliability.remediation.gates import RemediationGateChecker
from aireliability.remediation.integrations import (
    RemediationGraphBridge,
    RemediationObservabilityBridge,
)
from aireliability.remediation.models import (
    ApprovalRecord,
    RemediationLifecycleState,
    RemediationProposal,
    RepairType,
    RolloutState,
    RolloutStrategy,
    SimulationResult,
)
from aireliability.remediation.policy import HealingPolicy
from aireliability.remediation.promoter import PromotionManager
from aireliability.remediation.repairs.agent import AgentRepairer
from aireliability.remediation.repairs.base import BaseRepairGenerator
from aireliability.remediation.repairs.config import ConfigRepairer
from aireliability.remediation.repairs.prompt import PromptRepairer
from aireliability.remediation.repairs.retrieval import RetrievalRepairer
from aireliability.remediation.repairs.safety import SafetyRepairer
from aireliability.remediation.repairs.tool import ToolRepairer
from aireliability.remediation.rollback import RollbackManager
from aireliability.remediation.rollout import RolloutController
from aireliability.remediation.simulator import RemediationSimulator
from aireliability.remediation.test_bridge import RemediationTestBridge
from aireliability.remediation.verifier import RemediationVerifier

logger = logging.getLogger(__name__)


class RemediationEngine:
    """Production-grade Self-Healing AI Reliability Engine.

    Coordinates:
    Evidence Detection -> Diagnosis & Repair -> Test Generation (Phase 36) ->
    Simulation -> Evaluation Gates -> Healing Policy -> Approval ->
    Rollout (Direct/Shadow/Canary) -> Verification -> Promote/Rollback ->
    Knowledge Graph & Audit Loop.
    """

    def __init__(
        self,
        repairers: list[BaseRepairGenerator] | None = None,
        test_bridge: RemediationTestBridge | None = None,
        simulator: RemediationSimulator | None = None,
        gate_checker: RemediationGateChecker | None = None,
        policy: HealingPolicy | None = None,
        approval_manager: ApprovalManager | None = None,
        rollout_controller: RolloutController | None = None,
        verifier: RemediationVerifier | None = None,
        rollback_manager: RollbackManager | None = None,
        promoter: PromotionManager | None = None,
        graph_bridge: RemediationGraphBridge | None = None,
        obs_bridge: RemediationObservabilityBridge | None = None,
    ) -> None:
        self.repairers = repairers or [
            PromptRepairer(),
            RetrievalRepairer(),
            ToolRepairer(),
            AgentRepairer(),
            ConfigRepairer(),
            SafetyRepairer(),
        ]
        self.test_bridge = test_bridge or RemediationTestBridge()
        self.simulator = simulator or RemediationSimulator()
        self.gate_checker = gate_checker or RemediationGateChecker()
        self.policy = policy or HealingPolicy()
        self.approval_manager = approval_manager or ApprovalManager()
        self.rollout_controller = rollout_controller or RolloutController()
        self.verifier = verifier or RemediationVerifier()
        self.rollback_manager = rollback_manager or RollbackManager()
        self.promoter = promoter or PromotionManager()
        self.graph_bridge = graph_bridge or RemediationGraphBridge()
        self.obs_bridge = obs_bridge or RemediationObservabilityBridge()

        self._proposals: dict[str, RemediationProposal] = {}

    def _resolve_proposal(
        self, target: str | RemediationProposal
    ) -> RemediationProposal:
        """Resolve a proposal ID string or return the proposal instance directly."""
        if isinstance(target, RemediationProposal):
            self._proposals[target.proposal_id] = target
            return target
        if target in self._proposals:
            return self._proposals[target]
        raise KeyError(f"Proposal '{target}' not found in remediation engine registry.")

    def select_repairer(
        self, evidence: Any, explicit_type: RepairType | str | None = None
    ) -> BaseRepairGenerator:
        """Select the most appropriate repair generator for the given failure evidence."""
        if explicit_type:
            type_str = str(explicit_type)
            for r in self.repairers:
                if (
                    r.repair_type.value == type_str
                    or r.repair_type.name.lower() == type_str.lower()
                ):
                    return r

        for r in self.repairers:
            if r.can_handle(evidence):
                return r

        # Default fallback is PromptRepairer
        return self.repairers[0]

    def diagnose_and_plan(
        self,
        evidence: Any,
        context: dict[str, Any] | None = None,
        explicit_type: RepairType | str | None = None,
        generate_tests: bool = True,
    ) -> RemediationProposal:
        """Diagnose failure evidence, generate repair patches, and synthesize verification tests."""
        context = dict(context or {})
        repairer = self.select_repairer(evidence, explicit_type=explicit_type)
        proposal = repairer.generate_proposal(evidence, context=context)

        # Generate Phase 36 verification tests
        if generate_tests:
            self.test_bridge.generate_verification_tests(proposal, evidence=evidence)

        self._proposals[proposal.proposal_id] = proposal
        self.obs_bridge.record_proposal_created(proposal)
        return proposal

    def simulate(
        self,
        target: str | RemediationProposal,
        baseline_test_cases: list[Any] | None = None,
    ) -> SimulationResult:
        """Run candidate patches in simulation sandbox, evaluate gates, and check policy."""
        proposal = self._resolve_proposal(target)
        from aireliability.remediation.simulator import RemediationSimulator

        simulator = self.simulator or RemediationSimulator()
        sim_result = simulator.simulate(
            proposal,
            baseline_test_cases=baseline_test_cases,
        )

        # Evaluate quality & safety gates
        self.gate_checker.evaluate_gates(proposal, simulation_result=sim_result)

        # Check organizational healing policy
        self.policy.evaluate_policy(proposal)

        self.obs_bridge.record_simulation(proposal)
        return sim_result

    def approve(
        self,
        target: str | RemediationProposal,
        approver: str = "operator",
        rationale: str = "Approved by operator",
    ) -> ApprovalRecord:
        """Explicitly approve a remediation proposal."""
        proposal = self._resolve_proposal(target)
        record = self.approval_manager.approve(
            proposal, approver=approver, rationale=rationale
        )
        self.obs_bridge.record_approval(proposal)
        return record

    def reject(
        self,
        target: str | RemediationProposal,
        approver: str = "operator",
        reason: str = "Rejected by operator",
    ) -> ApprovalRecord:
        """Explicitly reject a remediation proposal."""
        proposal = self._resolve_proposal(target)
        return self.approval_manager.reject(proposal, approver=approver, reason=reason)

    def apply(
        self,
        target: str | RemediationProposal,
        strategy: RolloutStrategy | None = None,
        percentage: float | None = None,
    ) -> RolloutState:
        """Deploy an approved remediation patch."""
        proposal = self._resolve_proposal(target)
        state = self.rollout_controller.apply(
            proposal, strategy=strategy, percentage=percentage
        )
        self.policy.record_rollout()
        self.obs_bridge.record_rollout(proposal)
        return state

    def verify(
        self,
        target: str | RemediationProposal,
        sample_count: int,
        remediation_error_rate: float,
        baseline_error_rate: float = 0.0,
    ) -> bool:
        """Verify the operational health of an active deployment."""
        proposal = self._resolve_proposal(target)
        is_healthy = self.verifier.verify(
            proposal,
            sample_count=sample_count,
            remediation_error_rate=remediation_error_rate,
            baseline_error_rate=baseline_error_rate,
        )

        if is_healthy:
            self.obs_bridge.record_verification(proposal)
        elif proposal.rollout_config.auto_rollback_on_failure:
            # Trigger automatic rollback if degraded
            self.rollback(
                proposal,
                reason=proposal.rollout_state.notes
                or "Degradation detected during verification",
                actor="system:auto_rollback",
            )

        return is_healthy

    def promote(
        self,
        target: str | RemediationProposal,
        actor: str = "operator",
        notes: str = "Promoted to permanent baseline",
    ) -> bool:
        """Promote a verified remediation to 100% active production baseline."""
        proposal = self._resolve_proposal(target)
        result = self.promoter.promote(proposal, actor=actor, notes=notes)
        self.obs_bridge.record_promotion(proposal)
        return result

    def rollback(
        self,
        target: str | RemediationProposal,
        reason: str = "Rollback triggered due to error rate increase or regression",
        actor: str = "operator",
    ) -> bool:
        """Revert an active or canary remediation to its previous configuration."""
        proposal = self._resolve_proposal(target)
        result = self.rollback_manager.rollback(proposal, reason=reason, actor=actor)
        self.obs_bridge.record_rollback(proposal)
        return result

    def sync_to_graph(
        self,
        target: str | RemediationProposal,
        graph: KnowledgeGraph,
    ) -> Any:
        """Synchronize the remediation proposal into the AI Reliability Knowledge Graph."""
        proposal = self._resolve_proposal(target)
        return self.graph_bridge.record_remediation(graph, proposal)

    def get_proposal(self, proposal_id: str) -> RemediationProposal | None:
        """Retrieve proposal by ID."""
        return self._proposals.get(proposal_id)

    def list_proposals(
        self,
        state: RemediationLifecycleState | None = None,
    ) -> list[RemediationProposal]:
        """List registered proposals, optionally filtered by lifecycle state."""
        if state is None:
            return list(self._proposals.values())
        return [p for p in self._proposals.values() if p.state == state]
