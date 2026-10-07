"""Data models for multidimensional regression detection and provenance."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aireliability.core.models import FailureReport, RegressionTest
from aireliability.diagnosis.models import RootCauseReport


class RegressionDimension(StrEnum):
    """Dimensions along which AI regressions are detected."""

    QUALITY = "quality"
    RETRIEVAL = "retrieval"
    SAFETY = "safety"
    LATENCY = "latency"
    COST = "cost"
    TOOL = "tool"
    HALLUCINATION = "hallucination"
    GROUNDEDNESS = "groundedness"
    FAITHFULNESS = "faithfulness"


class DimensionalRegression(BaseModel):
    """Detailed record of an identified regression along a specific dimension."""

    model_config = ConfigDict(frozen=True)

    test_id: str
    test_name: str
    dimension: RegressionDimension
    baseline_score: float
    current_score: float
    delta: float
    message: str
    failure_report: FailureReport | None = None
    root_cause: RootCauseReport | None = None
    regression_test: RegressionTest | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComprehensiveRegressionSummary(BaseModel):
    """Aggregate regression report spanning all evaluation dimensions."""

    model_config = ConfigDict(frozen=True)

    total_tests: int
    passing_tests: int
    regressed_tests: int
    fixed_tests: int
    regressions: list[DimensionalRegression] = Field(default_factory=list)
    dimension_breakdown: dict[str, int] = Field(default_factory=dict)

    @property
    def has_regressions(self) -> bool:
        """True if any regressions were detected across any dimension."""
        return len(self.regressions) > 0

    @property
    def total_regressions(self) -> int:
        """Total number of individual dimensional regressions found."""
        return len(self.regressions)

    @property
    def regressions_by_dimension(self) -> dict[str, int]:
        """Alias for dimension_breakdown."""
        return self.dimension_breakdown

    @property
    def generated_regression_tests(self) -> list[RegressionTest]:
        """All synthesized regression tests linked to identified regressions."""
        return [
            r.regression_test for r in self.regressions if r.regression_test is not None
        ]

    @property
    def root_cause_reports(self) -> list[RootCauseReport]:
        """All root cause reports diagnosed for regressions."""
        return [r.root_cause for r in self.regressions if r.root_cause is not None]
