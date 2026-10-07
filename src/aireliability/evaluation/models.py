"""Unified evaluation request, target, and report models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
)
from aireliability.diagnosis.models import RootCauseReport
from aireliability.evaluation.datasets.models import EvaluationDataset


def _generate_eval_id(prefix: str = "eval") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class EvaluationTarget(BaseModel):
    """Target under evaluation: an agent callable, an API endpoint, or historical traces."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    agent: Any | None = None
    traces: list[ExecutionTrace] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _remap_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and "agent" not in data and "target_callable" in data:
            data = dict(data)
            data["agent"] = data.pop("target_callable")
        return data


class MetricResult(BaseModel):
    """Represents a computed statistical or quantitative metric value."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    dimension: str = "quality"
    sample_count: int = 1
    confidence_interval: tuple[float, float] | None = None
    p_value: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    """Specification of an evaluation run across test cases or datasets."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    request_id: str = Field(default_factory=lambda: _generate_eval_id("req"))
    dataset: EvaluationDataset | str
    target: EvaluationTarget
    evaluators: list[Any] = Field(default_factory=list)
    profile: str | Any | None = None
    metrics: list[str] = Field(default_factory=list)
    concurrency: int = 1
    sample_rate: float = 1.0
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _validate_evaluators(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("evaluators") is None:
            data = dict(data)
            data["evaluators"] = []
        return data


class EvaluationReport(BaseModel):
    """Comprehensive evaluation report summarizing a complete evaluation run."""

    model_config = ConfigDict(frozen=True)

    report_id: str = Field(default_factory=lambda: _generate_eval_id("rep"))
    request_id: str = Field(default_factory=lambda: _generate_eval_id("req"))
    target_name: str
    dataset_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_test_cases: int
    passed_test_cases: int
    failed_test_cases: int
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    metrics: dict[str, MetricResult] = Field(default_factory=dict)
    failures: list[FailureReport] = Field(default_factory=list)
    root_causes: list[RootCauseReport] = Field(default_factory=list)
    regressions: list[Any] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """True if all test cases passed and there are zero failures."""
        return self.failed_test_cases == 0 and len(self.failures) == 0

    @property
    def execution_id(self) -> str:
        """Alias for report_id."""
        return self.report_id
