"""Strongly typed data models for Phase 37 Self-Healing AI Reliability Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "rem") -> str:
    """Generate a unique identifier with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return the current datetime in UTC timezone."""
    return datetime.now(UTC)


class RepairType(StrEnum):
    """Categorical classification of the repair domain."""

    PROMPT = "prompt_repair"
    RETRIEVAL = "retrieval_repair"
    TOOL = "tool_repair"
    AGENT = "agent_repair"
    CONFIG = "config_repair"
    SAFETY = "safety_repair"


class RemediationLifecycleState(StrEnum):
    """Formal state machine states for a remediation proposal."""

    PROPOSED = "PROPOSED"
    SIMULATING = "SIMULATING"
    SIMULATED = "SIMULATED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLYING = "APPLYING"
    CANARY = "CANARY"
    SHADOW = "SHADOW"
    ACTIVE = "ACTIVE"
    VERIFIED = "VERIFIED"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"


class RolloutStrategy(StrEnum):
    """Deployment routing strategy for applying a remediation patch."""

    DIRECT = "DIRECT"
    SHADOW = "SHADOW"
    CANARY = "CANARY"


class RemediationRiskTier(StrEnum):
    """Risk tier classification determining approval policy boundaries."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RolloutHealthStatus(StrEnum):
    """Health status during verification and canary monitoring."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class RemediationProvenance(BaseModel):
    """Evidential provenance linking remediation to failure sources and diagnoses."""

    model_config = ConfigDict(frozen=True)

    source_failure_id: str | None = None
    source_root_cause_id: str | None = None
    source_cluster_id: str | None = None
    source_incident_id: str | None = None
    source_trace_id: str | None = None
    source_graph_node_id: str | None = None
    source_pattern_id: str | None = None
    source_recommendation_id: str | None = None
    parent_proposal_id: str | None = None


class RemediationPatch(BaseModel):
    """Concrete configuration or instruction diff representing a single repair unit."""

    model_config = ConfigDict(frozen=True)

    patch_id: str = Field(default_factory=lambda: _generate_id("patch"))
    repair_type: RepairType
    target_component_id: str
    target_component_type: str = "config"
    description: str = ""
    original_value: Any = None
    patched_value: Any = None
    diff_summary: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationResult(BaseModel):
    """Outcomes from executing candidate patches in an isolated simulation sandbox."""

    model_config = ConfigDict(frozen=True)

    simulation_id: str = Field(default_factory=lambda: _generate_id("sim"))
    passed: bool = True
    total_tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    regressions_count: int = 0
    failure_recovery_rate: float = 1.0
    safety_violations_count: int = 0
    latency_overhead_percent: float = 0.0
    summary: str = ""
    test_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    simulated_at: datetime = Field(default_factory=_utc_now)


class GateEvaluationResult(BaseModel):
    """Quality and safety gate evaluation verdict."""

    model_config = ConfigDict(frozen=True)

    gates_passed: bool = True
    zero_regression_passed: bool = True
    recovery_rate_passed: bool = True
    safety_passed: bool = True
    latency_passed: bool = True
    failed_gate_reasons: list[str] = Field(default_factory=list)
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=_utc_now)


class ApprovalRecord(BaseModel):
    """Cryptographic/tokenized audit record of human or automated policy approval."""

    model_config = ConfigDict(frozen=True)

    approval_id: str = Field(default_factory=lambda: _generate_id("appr"))
    approver: str
    approved: bool = True
    approval_token: str = ""
    rationale: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RolloutConfig(BaseModel):
    """Configuration controlling patch rollout, traffic routing, and safety boundaries."""

    model_config = ConfigDict(frozen=True)

    strategy: RolloutStrategy = RolloutStrategy.CANARY
    initial_percentage: float = 10.0
    step_percentage: float = 20.0
    verification_window_seconds: int = 60
    max_allowed_error_rate: float = 0.05
    shadow_sample_rate: float = 1.0
    auto_rollback_on_failure: bool = True


class RolloutState(BaseModel):
    """Mutable runtime telemetry state tracking an active canary/shadow/direct rollout."""

    model_config = ConfigDict(frozen=False)

    strategy: RolloutStrategy = RolloutStrategy.CANARY
    active_percentage: float = 0.0
    health_status: RolloutHealthStatus = RolloutHealthStatus.UNKNOWN
    baseline_error_rate: float = 0.0
    remediation_error_rate: float = 0.0
    sample_count: int = 0
    applied_at: datetime | None = None
    verified_at: datetime | None = None
    rolled_back_at: datetime | None = None
    promoted_at: datetime | None = None
    notes: str = ""


class RemediationAuditRecord(BaseModel):
    """Immutable audit trail entry documenting a lifecycle state transition."""

    model_config = ConfigDict(frozen=True)

    record_id: str = Field(default_factory=lambda: _generate_id("audit"))
    proposal_id: str
    from_state: RemediationLifecycleState
    to_state: RemediationLifecycleState
    actor: str = "system"
    action: str = ""
    reason: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemediationProposal(BaseModel):
    """A self-healing remediation plan encompassing patches, tests, simulation, and rollout."""

    model_config = ConfigDict(frozen=False)

    proposal_id: str = Field(default_factory=lambda: _generate_id("rem"))
    title: str
    description: str = ""
    repair_type: RepairType
    state: RemediationLifecycleState = RemediationLifecycleState.PROPOSED
    risk_tier: RemediationRiskTier = RemediationRiskTier.LOW
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    patches: list[RemediationPatch] = Field(default_factory=list)
    provenance: RemediationProvenance = Field(
        default_factory=lambda: RemediationProvenance()
    )
    generated_test_ids: list[str] = Field(default_factory=list)
    simulation: SimulationResult | None = None
    gate_evaluation: GateEvaluationResult | None = None
    approval: ApprovalRecord | None = None
    rollout_config: RolloutConfig = Field(default_factory=RolloutConfig)
    rollout_state: RolloutState = Field(default_factory=RolloutState)
    audit_trail: list[RemediationAuditRecord] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    def record_transition(
        self,
        to_state: RemediationLifecycleState,
        actor: str = "system",
        action: str = "",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> RemediationAuditRecord:
        """Record an explicit validated lifecycle transition in the immutable audit trail."""
        record = RemediationAuditRecord(
            proposal_id=self.proposal_id,
            from_state=self.state,
            to_state=to_state,
            actor=actor,
            action=action,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        self.state = to_state
        self.updated_at = _utc_now()
        self.audit_trail.append(record)
        return record


class HealingPolicyConfig(BaseModel):
    """Autonomous healing boundaries and safety governor configuration."""

    model_config = ConfigDict(frozen=True)

    auto_heal_enabled: bool = False
    allowed_auto_risk_tiers: list[RemediationRiskTier] = Field(
        default_factory=lambda: [RemediationRiskTier.LOW]
    )
    require_approval_for_high_risk: bool = True
    max_rollouts_per_hour: int = 5
    default_rollout_strategy: RolloutStrategy = RolloutStrategy.CANARY
    default_canary_percentage: float = 10.0
    max_allowed_error_rate_delta: float = 0.02
    min_recovery_rate: float = 0.8
    allow_direct_for_dev: bool = True
