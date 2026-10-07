"""Phase 37 Self-Healing AI Reliability Engine.

Closed-loop autonomous and human-in-the-loop remediation for LLMs and AI Agents.
"""

from __future__ import annotations

from aireliability.remediation.approval import ApprovalManager
from aireliability.remediation.engine import RemediationEngine
from aireliability.remediation.gates import RemediationGateChecker
from aireliability.remediation.integrations import (
    RemediationGraphBridge,
    RemediationObservabilityBridge,
)
from aireliability.remediation.models import (
    ApprovalRecord,
    GateEvaluationResult,
    HealingPolicyConfig,
    RemediationAuditRecord,
    RemediationLifecycleState,
    RemediationPatch,
    RemediationProposal,
    RemediationProvenance,
    RemediationRiskTier,
    RepairType,
    RolloutConfig,
    RolloutHealthStatus,
    RolloutState,
    RolloutStrategy,
    SimulationResult,
)
from aireliability.remediation.policy import HealingPolicy
from aireliability.remediation.promoter import PromotionManager
from aireliability.remediation.repairs import (
    AgentRepairer,
    BaseRepairGenerator,
    ConfigRepairer,
    PromptRepairer,
    RetrievalRepairer,
    SafetyRepairer,
    ToolRepairer,
)
from aireliability.remediation.rollback import RollbackManager
from aireliability.remediation.rollout import RolloutController
from aireliability.remediation.serialization import RemediationSerializer
from aireliability.remediation.simulator import RemediationSimulator
from aireliability.remediation.test_bridge import RemediationTestBridge
from aireliability.remediation.verifier import RemediationVerifier

__all__ = [
    "AgentRepairer",
    "ApprovalManager",
    "ApprovalRecord",
    "BaseRepairGenerator",
    "ConfigRepairer",
    "GateEvaluationResult",
    "HealingPolicy",
    "HealingPolicyConfig",
    "PromotionManager",
    "PromptRepairer",
    "RemediationAuditRecord",
    "RemediationEngine",
    "RemediationGateChecker",
    "RemediationGraphBridge",
    "RemediationLifecycleState",
    "RemediationObservabilityBridge",
    "RemediationPatch",
    "RemediationProposal",
    "RemediationProvenance",
    "RemediationRiskTier",
    "RemediationSerializer",
    "RemediationSimulator",
    "RemediationTestBridge",
    "RemediationVerifier",
    "RepairType",
    "RetrievalRepairer",
    "RollbackManager",
    "RolloutConfig",
    "RolloutController",
    "RolloutHealthStatus",
    "RolloutState",
    "RolloutStrategy",
    "SafetyRepairer",
    "SimulationResult",
    "ToolRepairer",
]
