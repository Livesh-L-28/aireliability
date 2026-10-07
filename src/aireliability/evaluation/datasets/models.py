"""Data models for versioned evaluation datasets and test case collections."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.core.models import TestCase


class DatasetSplit(StrEnum):
    """Standard split categories for evaluation datasets."""

    DEV = "dev"
    VAL = "validation"
    TEST = "test"
    REGRESSION = "regression"
    PRODUCTION = "production"
    ADVERSARIAL = "adversarial"


def _generate_dataset_id() -> str:
    return f"ds_{uuid4().hex[:12]}"


class EvaluationDataset(BaseModel):
    """First-class versioned evaluation dataset."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_generate_dataset_id)
    name: str
    version: str = "1.0.0"
    description: str = ""
    split: DatasetSplit = DatasetSplit.TEST
    test_cases: list[TestCase] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def filter_by_tag(self, tag: str) -> EvaluationDataset:
        """Return a filtered copy containing only test cases matching tag."""
        filtered_cases = [tc for tc in self.test_cases if tag in tc.tags]
        return self.model_copy(update={"test_cases": filtered_cases})

    def filter_by_criteria(self, criteria_name: str) -> EvaluationDataset:
        """Return a copy with test cases containing specific expectation or criterion."""
        filtered = [
            tc
            for tc in self.test_cases
            if any(criteria_name.lower() in exp.lower() for exp in tc.expectations)
        ]
        return self.model_copy(update={"test_cases": filtered})

    def add_test_case(self, tc: TestCase) -> EvaluationDataset:
        """Return an updated copy with added test case."""
        return self.model_copy(update={"test_cases": list(self.test_cases) + [tc]})
