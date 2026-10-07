"""Data models for A/B testing and multi-variant evaluation experiments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_exp_id() -> str:
    return f"exp_{uuid4().hex[:12]}"


class VariantConfig(BaseModel):
    """Specification of an experimental variant (model, prompt, retriever, config)."""

    model_config = ConfigDict(frozen=True)

    name: str
    model_version: str | None = None
    prompt_version: str | None = None
    retriever_version: str | None = None
    embedding_version: str | None = None
    judge_version: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VariantResult(BaseModel):
    """Evaluation summary for a specific variant."""

    model_config = ConfigDict(frozen=True)

    variant: VariantConfig
    total_samples: int
    metric_scores: dict[str, float]
    mean_latency_ms: float
    total_cost: float
    pass_rate: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ABComparisonResult(BaseModel):
    """Statistical comparison between two experimental variants (Variant A vs Variant B)."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    variant_a: VariantConfig
    variant_b: VariantConfig
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metric_deltas: dict[str, float]
    p_values: dict[str, float] = Field(default_factory=dict)
    effect_sizes: dict[str, float] = Field(default_factory=dict)
    statistically_significant: dict[str, bool] = Field(default_factory=dict)
    overall_winner: str | None = None
    summary: str = ""

    @property
    def deltas(self) -> dict[str, float]:
        """Alias for metric_deltas."""
        return self.metric_deltas

    @property
    def winner(self) -> str | None:
        """Alias for overall_winner."""
        return self.overall_winner
