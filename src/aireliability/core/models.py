"""Core data models for AI Reliability Engine."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StepType(StrEnum):
    """Supported step types within an execution trace."""

    LLM = "llm"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    AGENT = "agent"
    SYSTEM = "system"
    CUSTOM = "custom"


class ExecutionStatus(StrEnum):
    """Status of an execution trace."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FailureSeverity(StrEnum):
    """Severity levels for failure reports."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _generate_id(prefix: str = "") -> str:
    """Generate a unique identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class TestCase(BaseModel):
    """Test case specification representing an input and expected behavior."""

    __test__ = False
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _generate_id("tc"))
    name: str
    input: Any
    expected_output: Any = None
    expectations: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceStep(BaseModel):
    """Represents a discrete step or event within an AI execution trace."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _generate_id("step"))
    type: StepType = Field(default=StepType.CUSTOM)
    name: str
    input: Any = None
    output: Any = None
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _remap_step_type_alias(cls, data: Any) -> Any:
        """Allow 'step_type' as an alias for 'type' when constructing TraceStep."""
        if isinstance(data, dict) and "step_type" in data and "type" not in data:
            data = dict(data)
            data["type"] = data.pop("step_type")
        return data

    @model_validator(mode="after")
    def validate_duration_and_times(self) -> "TraceStep":
        """Compute duration_ms if missing and validate timestamps."""
        if self.completed_at is not None:
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot be earlier than started_at")
            if self.duration_ms is None:
                calculated = (
                    self.completed_at - self.started_at
                ).total_seconds() * 1000.0
                object.__setattr__(self, "duration_ms", max(0.0, calculated))
        return self


class ExecutionTrace(BaseModel):
    """Represents a captured execution trace from an AI task or agent."""

    model_config = ConfigDict(frozen=True)

    trace_id: str = Field(default_factory=lambda: _generate_id("trace"))
    test_id: str | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    input: Any = None
    output: Any = None
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    steps: list[TraceStep] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: float | None = None
    cost: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_trace_duration_and_times(self) -> "ExecutionTrace":
        """Compute latency_ms if missing and validate timestamps."""
        if self.completed_at is not None:
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot be earlier than started_at")
            if self.latency_ms is None:
                calculated = (
                    self.completed_at - self.started_at
                ).total_seconds() * 1000.0
                object.__setattr__(self, "latency_ms", max(0.0, calculated))
        return self


class EvaluationResult(BaseModel):
    """Result of an evaluation assertion or evaluator against a trace."""

    model_config = ConfigDict(frozen=True)

    evaluator: str
    passed: bool
    score: float | None = None
    message: str = ""
    evidence: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    metric: str | None = None
    threshold: float | None = None
    confidence: float | None = None
    reasoning: str | None = None
    evaluator_type: str | None = None
    provider: str | None = None
    model: str | None = None
    dataset: str | None = None
    test_case: str | None = None
    execution_id: str | None = None
    timestamp: datetime = Field(default_factory=_utc_now)
    latency: float | None = None
    cost: float | None = None

    @model_validator(mode="after")
    def validate_score(self) -> "EvaluationResult":
        """Ensure score is within [0.0, 1.0] if provided as a normalized value."""
        if self.score is not None and not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be between 0.0 and 1.0, got {self.score}")
        return self


class FailureReport(BaseModel):
    """Detailed report for an identified failure or regression."""

    model_config = ConfigDict(frozen=True)

    failure_id: str = Field(default_factory=lambda: _generate_id("fail"))
    trace_id: str
    test_id: str | None = None
    category: str
    type: str = "general_failure"
    severity: FailureSeverity = FailureSeverity.MEDIUM
    message: str
    evidence: Any = None
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _default_type(cls, data: Any) -> Any:
        if isinstance(data, dict) and ("type" not in data or data["type"] is None):
            data = dict(data)
            data["type"] = data.get("category", "general_failure")
        return data

    @model_validator(mode="after")
    def validate_confidence(self) -> "FailureReport":
        """Ensure confidence is between 0.0 and 1.0."""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        return self


class RegressionTest(BaseModel):
    """A regression test synthesized or captured from an identified failure."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _generate_id("reg"))
    name: str
    source_failure_id: str
    test_case: TestCase
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    """Represents the complete result of executing a test."""

    model_config = ConfigDict(frozen=True)

    test: TestCase
    trace: ExecutionTrace
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    failures: list[FailureReport] = Field(default_factory=list)
    passed: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _remap_test_alias(cls, data: Any) -> Any:
        """Allow 'test_case' as an alias for 'test' when constructing RunResult."""
        if isinstance(data, dict) and "test_case" in data and "test" not in data:
            data = dict(data)
            data["test"] = data.pop("test_case")
        return data

    @model_validator(mode="after")
    def determine_passed_status(self) -> "RunResult":
        """Compute passed boolean if not explicitly set."""
        if self.passed is None:
            # Passed if no failures and all evaluations passed
            all_evals_passed = all(ev.passed for ev in self.evaluations)
            has_no_failures = len(self.failures) == 0
            is_trace_failed = self.trace.status == ExecutionStatus.FAILED
            computed = all_evals_passed and has_no_failures and not is_trace_failed
            object.__setattr__(self, "passed", computed)
        return self
