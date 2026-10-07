"""Strongly typed data models for AI Safety Validation (Phase 41)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "safe") -> str:
    """Generate a unique ID with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


class SafetyCategory(StrEnum):
    """Taxonomy of safety and security boundary validation categories."""

    INSTRUCTION_BOUNDARY = "INSTRUCTION_BOUNDARY"
    INDIRECT_INSTRUCTION = "INDIRECT_INSTRUCTION"
    UNSAFE_REQUEST = "UNSAFE_REQUEST"
    SENSITIVE_INFORMATION = "SENSITIVE_INFORMATION"
    PRIVACY_PROTECTION = "PRIVACY_PROTECTION"
    SYNTHETIC_SECRET_PROTECTION = "SYNTHETIC_SECRET_PROTECTION"
    AUTHORIZATION_BEHAVIOR = "AUTHORIZATION_BEHAVIOR"
    TOOL_USE_BOUNDARY = "TOOL_USE_BOUNDARY"
    RETRIEVED_CONTENT_TRUST = "RETRIEVED_CONTENT_TRUST"
    DOCUMENT_TRUST = "DOCUMENT_TRUST"
    MEMORY_INTEGRITY = "MEMORY_INTEGRITY"
    MULTI_AGENT_BOUNDARY = "MULTI_AGENT_BOUNDARY"
    OUTPUT_SAFETY = "OUTPUT_SAFETY"
    POLICY_COMPLIANCE = "POLICY_COMPLIANCE"
    CONFIDENTIALITY = "CONFIDENTIALITY"
    INTEGRITY = "INTEGRITY"
    AVAILABILITY = "AVAILABILITY"
    BEHAVIOR_CONSISTENCY = "BEHAVIOR_CONSISTENCY"
    UNKNOWN = "UNKNOWN"


class SafetyStrategy(StrEnum):
    """Test scenario variation and mutation strategies."""

    TEMPLATE = "TEMPLATE"
    PARAMETER_VARIATION = "PARAMETER_VARIATION"
    CONTEXT_VARIATION = "CONTEXT_VARIATION"
    ROLE_VARIATION = "ROLE_VARIATION"
    MULTI_TURN = "MULTI_TURN"
    ENCODING_VARIATION = "ENCODING_VARIATION"
    DOCUMENT_VARIATION = "DOCUMENT_VARIATION"
    RETRIEVAL_VARIATION = "RETRIEVAL_VARIATION"
    TOOL_VARIATION = "TOOL_VARIATION"
    MEMORY_VARIATION = "MEMORY_VARIATION"
    AGENT_VARIATION = "AGENT_VARIATION"


class SafetyVerdict(StrEnum):
    """Evaluation verdict for a safety test or finding."""

    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    PARTIALLY_SAFE = "PARTIALLY_SAFE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class SafetySeverity(StrEnum):
    """Severity classification for safety risks and findings."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SafetyRisk(StrEnum):
    """Core dimensions of safety and security risk."""

    CONFIDENTIALITY = "CONFIDENTIALITY"
    INTEGRITY = "INTEGRITY"
    AVAILABILITY = "AVAILABILITY"
    SAFETY = "SAFETY"
    PRIVACY = "PRIVACY"
    AUTHORIZATION = "AUTHORIZATION"
    SECURITY = "SECURITY"
    RELIABILITY = "RELIABILITY"


class SafetyExecutionMode(StrEnum):
    """Permitted controlled execution sandbox modes."""

    OFFLINE = "OFFLINE"
    SIMULATION = "SIMULATION"
    SANDBOX = "SANDBOX"


class SafetyTarget(BaseModel):
    """Target component under validation."""

    model_config = ConfigDict(frozen=True)

    target_id: str
    target_type: str = "llm"  # llm, agent, rag, tool, memory, multiagent
    name: str = ""
    version: str | None = None
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyScenario(BaseModel):
    """Contextual setup and constraints for a safety validation scenario."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(default_factory=lambda: _generate_id("scen"))
    name: str = ""
    system_prompt: str = ""
    user_context: dict[str, Any] = Field(default_factory=dict)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    retrieved_documents: list[str] = Field(default_factory=list)
    environment: str = "test"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyInput(BaseModel):
    """Adversarial or boundary test input delivered to the target."""

    model_config = ConfigDict(frozen=True)

    input_id: str = Field(default_factory=lambda: _generate_id("inp"))
    content: str
    category: SafetyCategory
    strategy: SafetyStrategy
    encoding: str = "plain"  # plain, base64, rot13, leetspeak, url
    mutation_round: int = 0
    parameters: dict[str, Any] = Field(default_factory=dict)

    def fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint of the input content."""
        data = f"{self.category.value}:{self.strategy.value}:{self.encoding}:{self.content}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


class SafetyTest(BaseModel):
    """Self-contained test case representing a controlled safety validation probe."""

    model_config = ConfigDict(frozen=True)

    test_id: str = Field(default_factory=lambda: _generate_id("stest"))
    category: SafetyCategory
    strategy: SafetyStrategy
    target: SafetyTarget
    safety_input: SafetyInput
    scenario: SafetyScenario = Field(default_factory=SafetyScenario)
    expected_property: str = (
        "Should respect safety boundary and reject unsafe instructions"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    def fingerprint(self) -> str:
        """Deterministic fingerprint of this safety test."""
        data = f"{self.category.value}:{self.strategy.value}:{self.target.target_id}:{self.safety_input.fingerprint()}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


class SafetyExecution(BaseModel):
    """Result of running a safety test in an offline/simulated sandbox."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(default_factory=lambda: _generate_id("exec"))
    test_id: str
    mode: SafetyExecutionMode
    output_text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    state_mutation: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    blocked: bool = False
    error: str | None = None
    executed_at: datetime = Field(default_factory=_utc_now)


class SafetyEvidence(BaseModel):
    """Verifiable observable evidence supporting a safety finding."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(default_factory=lambda: _generate_id("evid"))
    evidence_type: (
        str  # pattern_match, secret_exposure, unauthorized_tool, policy_violation
    )
    description: str
    matched_content: str = ""
    offset: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyObservation(BaseModel):
    """Direct observable facts extracted from an execution."""

    model_config = ConfigDict(frozen=True)

    observation_id: str = Field(default_factory=lambda: _generate_id("obs"))
    execution_id: str
    has_leakage: bool = False
    has_boundary_violation: bool = False
    has_unsafe_tool_call: bool = False
    has_harmful_content: bool = False
    evidence: list[SafetyEvidence] = Field(default_factory=list)


class SafetyFinding(BaseModel):
    """Diagnosed safety finding or boundary issue identified during validation."""

    model_config = ConfigDict(frozen=True)

    finding_id: str = Field(default_factory=lambda: _generate_id("find"))
    test_id: str
    category: SafetyCategory
    risk_dimension: SafetyRisk
    severity: SafetySeverity
    verdict: SafetyVerdict
    message: str
    evidence: list[SafetyEvidence] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utc_now)


class SafetyCoverage(BaseModel):
    """Validation coverage across safety taxonomy categories."""

    total_categories: int = 0
    covered_categories: int = 0
    category_distribution: dict[str, int] = Field(default_factory=dict)
    coverage_ratio: float = 0.0


class SafetyScore(BaseModel):
    """Composite safety validation score enforcing hard non-compensatory caps."""

    safety_score: float = Field(
        ge=0.0, le=1.0
    )  # 1.0 = fully safe, 0.0 = completely compromised
    risk_score: float = Field(ge=0.0, le=1.0)  # 0.0 = no risk, 1.0 = extreme risk
    severity_max: SafetySeverity = SafetySeverity.INFO
    detection_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    false_positive_indicators: int = 0
    critical_violations_count: int = 0
    high_violations_count: int = 0
    hard_veto_applied: bool = False
    reliability_cap: float = (
        1.0  # Caps overall system reliability at <= 0.30 if hard veto
    )

    @property
    def overall_score(self) -> float:
        """Alias for safety_score for cross-subsystem scoring consistency."""
        return self.safety_score


class SafetyRecommendation(BaseModel):
    """Actionable remediation recommendation for diagnosed safety findings."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str = Field(default_factory=lambda: _generate_id("rec"))
    finding_id: str
    action_type: str  # prompt_hardening, input_guardrail, output_filter, tool_quarantine, memory_sanitization
    title: str
    description: str
    priority: SafetySeverity = SafetySeverity.HIGH
    suggested_fix: str = ""


class SafetyVerification(BaseModel):
    """Verification result confirming whether a safety remediation healed the issue."""

    model_config = ConfigDict(frozen=True)

    verification_id: str = Field(default_factory=lambda: _generate_id("verif"))
    remediation_id: str
    verified: bool
    retest_verdict: SafetyVerdict
    retest_finding: SafetyFinding | None = None
    verified_at: datetime = Field(default_factory=_utc_now)


class SafetyRegression(BaseModel):
    """Historical safety failure promoted to permanent regression test (Phase 36)."""

    model_config = ConfigDict(frozen=True)

    regression_id: str = Field(default_factory=lambda: _generate_id("sreg"))
    safety_test: SafetyTest
    initial_finding: SafetyFinding
    promoted_at: datetime = Field(default_factory=_utc_now)
    passed_on_baseline: bool = False


class SafetyBaseline(BaseModel):
    """Established safety baseline performance for drift tracking."""

    baseline_id: str = Field(default_factory=lambda: _generate_id("sbase"))
    target_id: str
    score: SafetyScore
    coverage: SafetyCoverage
    total_tests: int = 0
    passed_tests: int = 0
    recorded_at: datetime = Field(default_factory=_utc_now)


class SafetyCampaign(BaseModel):
    """Plan for an automated safety validation campaign."""

    model_config = ConfigDict(frozen=True)

    campaign_id: str = Field(default_factory=lambda: _generate_id("camp"))
    name: str = "Automated Safety Validation Campaign"
    target: SafetyTarget
    categories: list[SafetyCategory] = Field(default_factory=list)
    strategies: list[SafetyStrategy] = Field(default_factory=list)
    max_tests: int = 100
    mutation_budget: int = 3
    deterministic_seed: int = 42
    mode: SafetyExecutionMode = SafetyExecutionMode.SIMULATION
    created_at: datetime = Field(default_factory=_utc_now)


class SafetyCampaignResult(BaseModel):
    """Aggregated outcome of an automated safety validation campaign."""

    campaign_id: str
    target: SafetyTarget
    total_tests: int = 0
    total_findings: int = 0
    score: SafetyScore
    coverage: SafetyCoverage
    verdicts_summary: dict[str, int] = Field(default_factory=dict)
    findings: list[SafetyFinding] = Field(default_factory=list)
    regressions_promoted: list[SafetyRegression] = Field(default_factory=list)
    recommendations: list[SafetyRecommendation] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=_utc_now)


class SafetyReport(BaseModel):
    """Comprehensive safety report for human audit and automated governance."""

    report_id: str = Field(default_factory=lambda: _generate_id("srep"))
    generated_at: datetime = Field(default_factory=_utc_now)
    target: SafetyTarget
    campaign_result: SafetyCampaignResult
    system_reliability_capped: bool = False
    effective_reliability_ceiling: float = 1.0
    summary: str = ""
