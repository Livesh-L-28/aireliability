"""Data models for Root Cause Analysis and diagnosis reporting."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aireliability.core.models import FailureSeverity
from aireliability.diagnosis.evidence import Evidence


def _generate_id(prefix: str = "") -> str:
    """Generate a unique identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


class RootCauseCategory(StrEnum):
    """Broad categories for diagnosed root causes."""

    TOOL = "tool"
    OUTPUT = "output"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    PROMPT = "prompt"
    PERFORMANCE = "performance"
    EXECUTION = "execution"
    UNKNOWN = "unknown"


class RootCauseType(StrEnum):
    """Specific types for diagnosed root causes."""

    WRONG_TOOL = "wrong_tool"
    WRONG_ARGUMENT = "wrong_argument"
    WRONG_ORDER = "wrong_order"
    MISSING_TOOL = "missing_tool"
    UNEXPECTED_OUTPUT = "unexpected_output"
    SEMANTIC_MISMATCH = "semantic_mismatch"
    LATENCY_REGRESSION = "latency_regression"
    EXCEPTION = "exception"
    MISSING_CONTEXT = "missing_context"
    CONTEXT_CONFLICT = "context_conflict"
    UNKNOWN = "unknown"


class CausalLink(BaseModel):
    """Represents an observable link connecting sequential events or failure steps.

    Attributes:
        source: Identifier of the source step or trigger.
        target: Identifier of the resulting step or effect.
        reason: Factual description of why the target was influenced by the source.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    reason: str


class RootCause(BaseModel):
    """Structured diagnosis of an AI execution failure based on empirical evidence."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _generate_id("rc"))
    category: RootCauseCategory = RootCauseCategory.UNKNOWN
    type: RootCauseType = RootCauseType.UNKNOWN
    description: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    affected_step: str | None = None
    severity: FailureSeverity = FailureSeverity.MEDIUM
    causal_links: list[CausalLink] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_enums(cls, data: Any) -> Any:
        if isinstance(data, dict):
            cat = data.get("category")
            if isinstance(cat, str):
                try:
                    data["category"] = RootCauseCategory(cat.lower())
                except ValueError:
                    data["category"] = RootCauseCategory.UNKNOWN
            t = data.get("type")
            if isinstance(t, str):
                try:
                    data["type"] = RootCauseType(t.lower())
                except ValueError:
                    data["type"] = RootCauseType.UNKNOWN
        return data


class RootCauseReport(BaseModel):
    """Comprehensive diagnosis report compiling primary and secondary root causes."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _generate_id("diag"))
    test_id: str | None = None
    trace_id: str | None = None
    status: str = "FAIL"

    @model_validator(mode="before")
    @classmethod
    def _remap_report_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and "report_id" in data and "id" not in data:
            data = dict(data)
            data["id"] = data.pop("report_id")
        return data

    @property
    def report_id(self) -> str:
        """Alias for id for backward and external compatibility."""
        return self.id

    primary_cause: RootCause | None = None
    secondary_causes: list[RootCause] = Field(default_factory=list)
    causal_chain: list[CausalLink] = Field(default_factory=list)
    summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def format_terminal(self) -> str:
        """Format diagnosis report as a readable terminal string."""
        lines = [
            "AI Reliability Root Cause Analysis",
            "─" * 34,
            f"Test:    {self.test_id or 'unknown'}",
            f"Status:  {self.status}",
        ]
        if self.primary_cause:
            pc = self.primary_cause
            cause_code = f"{pc.category.value.upper()}.{pc.type.value.upper()}"
            lines.extend(
                [
                    "",
                    f"Primary Detected Cause: {cause_code}",
                    f"Confidence:             {pc.confidence:.2f}",
                    f"Description:            {pc.description}",
                ]
            )
            if pc.affected_step:
                lines.append(f"Affected Step:          {pc.affected_step}")
            if pc.evidence:
                lines.append("\nEvidence:")
                for ev in pc.evidence:
                    if ev.expected is not None or ev.actual is not None:
                        lines.append(f"  Expected: {ev.expected}")
                        lines.append(f"  Actual:   {ev.actual}")
                    if ev.explanation:
                        lines.append(f"  Note:     {ev.explanation}")

        if self.secondary_causes:
            lines.append("\nSecondary Causes:")
            for sc in self.secondary_causes:
                sc_code = f"{sc.category.value.upper()}.{sc.type.value.upper()}"
                lines.append(f"  - {sc_code}: {sc.description}")

        if self.causal_chain:
            lines.append("\nCausal Links:")
            for link in self.causal_chain:
                lines.append(f"  {link.source} ──▶ {link.target} ({link.reason})")

        return "\n".join(lines)
