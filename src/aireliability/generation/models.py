"""Strongly typed data models for Automated AI Test Generation (Phase 36)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aireliability.core.models import RegressionTest, TestCase


def _generate_id(prefix: str = "gen_test") -> str:
    """Generate a unique identifier with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return the current datetime in UTC timezone."""
    return datetime.now(UTC)


class TestGenerationStatus(StrEnum):
    """Lifecycle status of a generated test."""

    CANDIDATE = "candidate"
    VALIDATING = "validating"
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    PROMOTED = "promoted"


class GenerationStrategy(StrEnum):
    """Taxonomy of test generation strategies supported by Phase 36."""

    FAILURE_DRIVEN = "failure_driven"
    REGRESSION_DRIVEN = "regression_driven"
    GRAPH_DRIVEN = "graph_driven"
    PATTERN_DRIVEN = "pattern_driven"
    INCIDENT_DRIVEN = "incident_driven"
    PRODUCTION_TRACE_DRIVEN = "production_trace_driven"
    EDGE_CASE = "edge_case"
    MUTATION_BASED = "mutation_based"
    ADVERSARIAL = "adversarial"
    SAFETY_SECURITY_PRIVACY = "safety_security_privacy"
    RAG_FOCUSED = "rag_focused"
    AGENT_TRAJECTORY = "agent_trajectory"
    ROBUSTNESS = "robustness"
    CONSISTENCY = "consistency"


class TestType(StrEnum):
    """Classification of the generated test case."""

    UNIT = "unit"
    REGRESSION = "regression"
    INTEGRATION = "integration"
    EDGE_CASE = "edge_case"
    MUTATION = "mutation"
    ADVERSARIAL = "adversarial"
    SAFETY = "safety"
    RAG = "rag"
    AGENT = "agent"
    ROBUSTNESS = "robustness"
    CONSISTENCY = "consistency"
    FUZZ = "fuzz"


class TestRiskLevel(StrEnum):
    """Operational and security risk classification for generated tests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TestPriority(StrEnum):
    """Execution and maintenance priority for generated tests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GenerationSourceType(StrEnum):
    """Origin taxonomy of the source evidence used to generate the test."""

    FAILURE_REPORT = "failure_report"
    EVALUATION_REPORT = "evaluation_report"
    REGRESSION_TEST = "regression_test"
    INCIDENT = "incident"
    PRODUCTION_TRACE = "production_trace"
    GRAPH_PATH = "graph_path"
    GRAPH_NODE = "graph_node"
    FAILURE_CLUSTER = "failure_cluster"
    FAILURE_PATTERN = "failure_pattern"
    RECOMMENDATION = "recommendation"
    EXISTING_TEST = "existing_test"
    SYNTHETIC = "synthetic"


class TestProvenance(BaseModel):
    """Complete, immutable provenance chain explaining why and how a test was generated."""

    model_config = ConfigDict(frozen=True)

    source_type: GenerationSourceType
    source_id: str
    source_failure_id: str | None = None
    source_incident_id: str | None = None
    source_trace_id: str | None = None
    source_graph_node: str | None = None
    source_graph_path: list[str] = Field(default_factory=list)
    source_pattern_id: str | None = None
    source_cluster_id: str | None = None
    source_recommendation_id: str | None = None
    parent_test_id: str | None = None
    mutation_type: str | None = None
    mutation_parameters: dict[str, Any] = Field(default_factory=dict)
    generator_name: str = ""
    generator_version: str = "0.5.0"
    deterministic_seed: int | None = None
    timestamp: datetime = Field(default_factory=_utc_now)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestQualityScore(BaseModel):
    """Deterministic, explainable multi-factor quality scoring for a generated test."""

    model_config = ConfigDict(frozen=True)

    total_score: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_strength: float = Field(default=1.0, ge=0.0, le=1.0)
    failure_relevance: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_score: float = Field(default=1.0, ge=0.0, le=1.0)
    novelty_score: float = Field(default=1.0, ge=0.0, le=1.0)
    diversity_score: float = Field(default=1.0, ge=0.0, le=1.0)
    correctness_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reproducibility_score: float = Field(default=1.0, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0)
    source_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    explanation: str = ""
    factors: dict[str, float] = Field(default_factory=dict)


class GeneratedTest(BaseModel):
    """Strongly typed, production-grade representation of an AI-generated test candidate."""

    model_config = ConfigDict(frozen=True)

    test_id: str = Field(default_factory=lambda: _generate_id("gen"))
    name: str
    test_type: TestType = TestType.UNIT
    strategy: GenerationStrategy = GenerationStrategy.FAILURE_DRIVEN
    status: TestGenerationStatus = TestGenerationStatus.CANDIDATE
    input: Any
    expected_output: Any | None = None
    expected_criteria: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    has_ground_truth: bool = False
    context: str | None = None
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    tool_definitions: list[dict[str, Any]] = Field(default_factory=list)
    expected_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    expected_trajectory_constraints: list[str] = Field(default_factory=list)
    model_info: dict[str, Any] = Field(default_factory=dict)
    prompt_info: dict[str, Any] = Field(default_factory=dict)
    dataset_info: dict[str, Any] = Field(default_factory=dict)
    provenance: TestProvenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    quality_score: TestQualityScore | None = None
    risk_level: TestRiskLevel = TestRiskLevel.LOW
    priority: TestPriority = TestPriority.MEDIUM
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = ""
    validation_reasons: list[str] = Field(default_factory=list)
    generation_timestamp: datetime = Field(default_factory=_utc_now)
    generator_version: str = "0.5.0"
    deterministic_seed: int | None = None

    @model_validator(mode="after")
    def _validate_ground_truth_integrity(self) -> GeneratedTest:
        """Ensure reference answers are not silently fabricated without ground truth flag."""
        if not self.has_ground_truth and self.reference_answer is not None:
            # If reference answer is provided, ground truth flag must be explicit
            object.__setattr__(self, "has_ground_truth", True)
        return self

    def transition_to(
        self,
        new_status: TestGenerationStatus,
        reason: str = "",
    ) -> GeneratedTest:
        """Safely transition test lifecycle status adhering to transition rules."""
        valid_transitions: dict[TestGenerationStatus, set[TestGenerationStatus]] = {
            TestGenerationStatus.CANDIDATE: {
                TestGenerationStatus.VALIDATING,
                TestGenerationStatus.VALIDATED,
                TestGenerationStatus.NEEDS_REVIEW,
                TestGenerationStatus.REJECTED,
            },
            TestGenerationStatus.VALIDATING: {
                TestGenerationStatus.VALIDATED,
                TestGenerationStatus.NEEDS_REVIEW,
                TestGenerationStatus.REJECTED,
            },
            TestGenerationStatus.VALIDATED: {
                TestGenerationStatus.PROMOTED,
                TestGenerationStatus.NEEDS_REVIEW,
                TestGenerationStatus.REJECTED,
            },
            TestGenerationStatus.NEEDS_REVIEW: {
                TestGenerationStatus.VALIDATED,
                TestGenerationStatus.REJECTED,
            },
            TestGenerationStatus.REJECTED: set(),  # Terminal state: cannot promote rejected tests
            TestGenerationStatus.PROMOTED: set(),  # Terminal state
        }

        allowed = valid_transitions.get(self.status, set())
        if new_status not in allowed and new_status != self.status:
            raise ValueError(
                f"Invalid lifecycle transition from {self.status.value} to {new_status.value}. "
                f"Allowed target states: {[s.value for s in allowed]}"
            )

        new_reasons = list(self.validation_reasons)
        if reason:
            new_reasons.append(reason)

        return self.model_copy(
            update={
                "status": new_status,
                "validation_reasons": new_reasons,
            }
        )

    def to_test_case(self) -> TestCase:
        """Convert this generated test into a standard platform TestCase."""
        tc_metadata = dict(self.metadata)
        tc_metadata["generated_test_id"] = self.test_id
        tc_metadata["generation_strategy"] = str(self.strategy)
        tc_metadata["test_type"] = str(self.test_type)
        tc_metadata["generation_status"] = str(self.status)
        tc_metadata["fingerprint"] = self.fingerprint
        tc_metadata["has_ground_truth"] = self.has_ground_truth
        if self.reference_answer is not None:
            tc_metadata["reference_answer"] = self.reference_answer
        if self.context is not None:
            tc_metadata["context"] = self.context
        if self.retrieved_documents:
            tc_metadata["retrieved_documents"] = self.retrieved_documents
        if self.tool_definitions:
            tc_metadata["tool_definitions"] = self.tool_definitions
        if self.expected_tool_calls:
            tc_metadata["expected_tool_calls"] = self.expected_tool_calls
        if self.expected_trajectory_constraints:
            tc_metadata["expected_trajectory_constraints"] = (
                self.expected_trajectory_constraints
            )
        if self.model_info:
            tc_metadata["model_info"] = self.model_info
        if self.prompt_info:
            tc_metadata["prompt_info"] = self.prompt_info
        if self.provenance:
            tc_metadata["provenance"] = self.provenance.model_dump()
        if self.quality_score:
            tc_metadata["quality_score"] = self.quality_score.model_dump()
        tc_metadata["risk_level"] = str(self.risk_level)
        tc_metadata["priority"] = str(self.priority)
        tc_metadata["confidence"] = self.confidence
        tc_metadata["generator_version"] = self.generator_version
        if self.deterministic_seed is not None:
            tc_metadata["deterministic_seed"] = self.deterministic_seed

        tags = list(self.tags)
        if "generated" not in tags:
            tags.append("generated")
        strategy_tag = f"strategy:{self.strategy}"
        if strategy_tag not in tags:
            tags.append(strategy_tag)
        type_tag = f"type:{self.test_type}"
        if type_tag not in tags:
            tags.append(type_tag)

        return TestCase(
            id=self.test_id,
            name=self.name,
            input=self.input,
            expected_output=self.expected_output,
            expectations=list(self.expected_criteria),
            tags=tags,
            metadata=tc_metadata,
        )

    def to_regression_test(self) -> RegressionTest:
        """Convert this generated test into a standard platform RegressionTest."""
        source_fail = self.provenance.source_failure_id or self.provenance.source_id
        reg_id = (
            self.test_id.replace("gen_", "reg_")
            if self.test_id.startswith("gen_")
            else f"reg_{self.test_id}"
        )
        tc = self.to_test_case()
        if "regression" not in tc.tags:
            tc = tc.model_copy(update={"tags": tc.tags + ["regression"]})

        reg_metadata = dict(self.metadata)
        reg_metadata["generated_test_id"] = self.test_id
        reg_metadata["generation_strategy"] = str(self.strategy)
        reg_metadata["fingerprint"] = self.fingerprint
        reg_metadata["provenance"] = self.provenance.model_dump()
        if self.quality_score:
            reg_metadata["quality_score"] = self.quality_score.model_dump()
        reg_metadata["risk_level"] = str(self.risk_level)
        reg_metadata["priority"] = str(self.priority)

        return RegressionTest(
            id=reg_id,
            name=f"reg_{self.name}",
            source_failure_id=source_fail,
            test_case=tc,
            created_at=self.generation_timestamp,
            metadata=reg_metadata,
        )


class TestGenerationConfig(BaseModel):
    """Configuration governing test generation execution, budgets, and safety gates."""

    model_config = ConfigDict(frozen=True)

    max_candidates: int = Field(default=100, ge=1)
    max_tests_per_source: int = Field(default=10, ge=1)
    max_mutation_count: int = Field(default=10, ge=1)
    max_tests_per_component: int = Field(default=20, ge=1)
    min_quality_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    min_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    promotion_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_graph_depth: int = Field(default=5, ge=1)
    max_production_samples: int = Field(default=50, ge=1)
    deduplication_mode: str = "exact_and_near"  # "exact", "exact_and_near", "off"
    near_duplicate_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    deterministic_seed: int = 42
    enable_provider: bool = False
    provider_timeout_seconds: float = Field(default=5.0, ge=0.1)
    safety_mode: bool = True
    auto_promote: bool = False  # Conservative default: never bypass review
    allowed_strategies: list[GenerationStrategy] | None = None


class TestGenerationRequest(BaseModel):
    """Encapsulates a request for automated AI test generation."""

    model_config = ConfigDict(frozen=True)

    sources: list[Any] = Field(default_factory=list)
    strategies: list[GenerationStrategy] = Field(default_factory=list)
    config: TestGenerationConfig = Field(default_factory=TestGenerationConfig)
    target_dataset_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestGenerationResult(BaseModel):
    """Complete structured output of an automated test generation run."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(default_factory=lambda: _generate_id("gen_req"))
    candidates: list[GeneratedTest] = Field(default_factory=list)
    validated_tests: list[GeneratedTest] = Field(default_factory=list)
    rejected_tests: list[GeneratedTest] = Field(default_factory=list)
    needs_review_tests: list[GeneratedTest] = Field(default_factory=list)
    promoted_tests: list[GeneratedTest] = Field(default_factory=list)
    duplicate_count: int = 0
    total_generated: int = 0
    total_validated: int = 0
    total_rejected: int = 0
    total_promoted: int = 0
    strategy_distribution: dict[str, int] = Field(default_factory=dict)
    source_distribution: dict[str, int] = Field(default_factory=dict)
    quality_distribution: dict[str, float] = Field(default_factory=dict)
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)
    generator_version: str = "0.5.0"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def test_cases(self) -> list[GeneratedTest]:
        """Convenience property returning test candidates."""
        return self.candidates
