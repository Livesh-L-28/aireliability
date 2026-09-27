"""Data models for intelligent regression synthesis, validation, and minimization."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.core.models import RegressionTest, TestCase


def _generate_id(prefix: str = "") -> str:
    """Generate a unique identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


class GenerationMethod(StrEnum):
    """Method used to synthesize a regression test."""

    DETERMINISTIC_TRACE_SYNTHESIS = "deterministic_trace_synthesis"
    SEMANTIC_FAILURE_CAPTURE = "semantic_failure_capture"
    MANUAL = "manual"
    FUTURE_AI_ASSISTED = "future_ai_assisted"


class GenerationStatus(StrEnum):
    """Status outcome of a regression test synthesis attempt."""

    SUCCESS = "success"
    DUPLICATE = "duplicate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    VALIDATION_FAILED = "validation_failed"


class RegressionValidation(BaseModel):
    """Validation outcome for a synthesized or candidate regression test."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    minimal: bool = True
    reproducible: bool = True
    specific: bool = True
    traceable: bool = True
    duplicate: bool = False
    reasons: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if the candidate passed all quality criteria and is not a duplicate."""
        return self.valid and not self.duplicate


class RegressionCandidate(BaseModel):
    """A synthesized candidate regression test before or after validation."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: _generate_id("cand"))
    name: str
    source_failure_id: str
    root_cause_id: str | None = None
    trace_id: str | None = None
    generation_method: GenerationMethod = GenerationMethod.DETERMINISTIC_TRACE_SYNTHESIS
    status: GenerationStatus = GenerationStatus.SUCCESS
    test_case: TestCase
    validation: RegressionValidation | None = None
    minimized: bool = False
    evidence_summary: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_regression_test(self) -> RegressionTest:
        """Convert this candidate into a standard RegressionTest instance."""
        reg_metadata = dict(self.metadata)
        reg_metadata["generation_method"] = str(self.generation_method)
        reg_metadata["generation_status"] = str(self.status)
        reg_metadata["minimized"] = self.minimized
        if self.root_cause_id:
            reg_metadata["root_cause_id"] = self.root_cause_id
        if self.trace_id:
            reg_metadata["source_trace_id"] = self.trace_id
        if self.evidence_summary:
            reg_metadata["evidence_summary"] = self.evidence_summary
        if self.validation:
            reg_metadata["validation"] = self.validation.model_dump()

        reg_id = (
            self.id.replace("cand_", "reg_") if self.id.startswith("cand_") else self.id
        )
        return RegressionTest(
            id=reg_id,
            name=self.name,
            source_failure_id=self.source_failure_id,
            test_case=self.test_case,
            metadata=reg_metadata,
        )


__all__ = [
    "GenerationMethod",
    "GenerationStatus",
    "RegressionCandidate",
    "RegressionValidation",
]
