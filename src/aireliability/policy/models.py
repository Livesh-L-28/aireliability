"""Strongly typed data models for Reliability Policy Engine (Phase 44)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "pol") -> str:
    """Generate a unique ID with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


class PolicyDecision(StrEnum):
    """Enforceable decision emitted by policy engine."""

    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    QUARANTINE = "QUARANTINE"


class PolicyPriority(StrEnum):
    """Strict precedence order for policy rules."""

    SECURITY = "SECURITY"
    SAFETY = "SAFETY"
    TENANT_ISOLATION = "TENANT_ISOLATION"
    AUTHORIZATION = "AUTHORIZATION"
    COMPLIANCE = "COMPLIANCE"
    RELIABILITY = "RELIABILITY"
    PERFORMANCE = "PERFORMANCE"
    COST = "COST"


class PolicyScope(StrEnum):
    """Target scope where the policy is enforced."""

    GLOBAL = "GLOBAL"
    ORGANIZATION = "ORGANIZATION"
    TENANT = "TENANT"
    PROJECT = "PROJECT"
    ENVIRONMENT = "ENVIRONMENT"


class PolicyOperator(StrEnum):
    """Supported comparison operators for condition evaluation."""

    EQ = "EQ"
    NEQ = "NEQ"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    IN = "IN"
    CONTAINS = "CONTAINS"


class PolicyCondition(BaseModel):
    """A single boolean condition evaluated against input metrics/state."""

    model_config = ConfigDict(frozen=True)

    field: str
    operator: PolicyOperator
    target_value: Any


class PolicyAction(BaseModel):
    """Action taken when rule conditions trigger."""

    model_config = ConfigDict(frozen=True)

    decision: PolicyDecision
    message: str = ""
    remediation_hint: str = ""


class PolicyRule(BaseModel):
    """An individual rule within a policy."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(default_factory=lambda: _generate_id("rule"))
    name: str
    description: str = ""
    priority: PolicyPriority
    conditions: list[PolicyCondition] = Field(default_factory=list)
    action: PolicyAction
    is_hard_constraint: bool = False


class ReliabilityPolicy(BaseModel):
    """A versioned collection of policy rules governing reliability."""

    model_config = ConfigDict(frozen=True)

    policy_id: str = Field(default_factory=lambda: _generate_id("pol"))
    name: str
    version: str = "1.0.0"
    scope: PolicyScope = PolicyScope.GLOBAL
    rules: list[PolicyRule] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utc_now)


class PolicyViolation(BaseModel):
    """An observed violation of a policy rule."""

    model_config = ConfigDict(frozen=True)

    violation_id: str = Field(default_factory=lambda: _generate_id("viol"))
    rule_id: str
    rule_name: str
    priority: PolicyPriority
    field: str
    threshold: Any
    observed_value: Any
    message: str


class PolicyException(BaseModel):
    """A time-bounded approved exception to a policy rule."""

    model_config = ConfigDict(frozen=True)

    exception_id: str = Field(default_factory=lambda: _generate_id("exc"))
    rule_id: str
    actor: str
    reason: str
    expires_at: datetime


class PolicyEvaluation(BaseModel):
    """Detailed result of evaluating a policy against an input context."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(default_factory=lambda: _generate_id("peval"))
    policy_id: str
    policy_version: str
    decision: PolicyDecision
    effective_priority: PolicyPriority
    triggered_rules: list[str] = Field(default_factory=list)
    violations: list[PolicyViolation] = Field(default_factory=list)
    explanation: str = ""
    actor: str = "system"
    tenant_id: str | None = None
    evaluated_at: datetime = Field(default_factory=_utc_now)

    def fingerprint(self) -> str:
        """Deterministic fingerprint of this policy decision."""
        data = f"{self.policy_id}:{self.decision.value}:{len(self.violations)}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


class PolicyAudit(BaseModel):
    """Immutable audit trail entry for a policy decision or override."""

    model_config = ConfigDict(frozen=True)

    audit_id: str = Field(default_factory=lambda: _generate_id("paudit"))
    policy_id: str
    policy_version: str
    decision: PolicyDecision
    actor: str
    tenant_id: str | None = None
    project_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    override_reason: str | None = None
    timestamp: datetime = Field(default_factory=_utc_now)


class PolicyVersion(BaseModel):
    """Version metadata tracking semantic revisions and rollbacks."""

    model_config = ConfigDict(frozen=True)

    version_id: str = Field(default_factory=lambda: _generate_id("pver"))
    policy_id: str
    version_tag: str = "1.0.0"
    description: str = ""
    author: str = "system"
    created_at: datetime = Field(default_factory=_utc_now)


class PolicyBundle(BaseModel):
    """Hierarchical bundle of policies aggregated for evaluation."""

    model_config = ConfigDict(frozen=True)

    bundle_id: str = Field(default_factory=lambda: _generate_id("pbundle"))
    name: str = "Default Enterprise Policy Bundle"
    policies: list[ReliabilityPolicy] = Field(default_factory=list)
