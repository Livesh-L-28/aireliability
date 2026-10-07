"""Configurable pricing abstraction for LLMs, embeddings, and tool APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ModelPricing(BaseModel):
    """Pricing rates per million tokens for a specific model."""

    model_config = ConfigDict(frozen=True)

    input_cost_per_million: float = 0.15
    output_cost_per_million: float = 0.60
    cached_input_cost_per_million: float = 0.075
    embedding_cost_per_million: float = 0.02
    cost_per_tool_call: float = 0.0


class PricingModel:
    """Configurable pricing registry and calculator."""

    def __init__(
        self,
        default_pricing: ModelPricing | None = None,
        custom_rates: dict[str, ModelPricing] | None = None,
    ) -> None:
        self.default_pricing = default_pricing or ModelPricing()
        self._rates: dict[str, ModelPricing] = dict(custom_rates or {})

        # Standard known defaults (configurable and overridable)
        self._rates.setdefault(
            "gpt-4o-mini",
            ModelPricing(input_cost_per_million=0.15, output_cost_per_million=0.60),
        )
        self._rates.setdefault(
            "gpt-4o",
            ModelPricing(input_cost_per_million=2.50, output_cost_per_million=10.00),
        )
        self._rates.setdefault(
            "claude-3-5-sonnet",
            ModelPricing(input_cost_per_million=3.00, output_cost_per_million=15.00),
        )

    def register_model(
        self,
        model_name: str,
        pricing: ModelPricing | None = None,
        *,
        input_cost_per_million: float | None = None,
        output_cost_per_million: float | None = None,
        input_cost_per_m: float | None = None,
        output_cost_per_m: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Register or override pricing for a specific model."""
        if pricing is not None:
            self._rates[model_name] = pricing
        else:
            in_cost = (
                input_cost_per_m
                if input_cost_per_m is not None
                else (input_cost_per_million or 0.15)
            )
            out_cost = (
                output_cost_per_m
                if output_cost_per_m is not None
                else (output_cost_per_million or 0.60)
            )
            self._rates[model_name] = ModelPricing(
                input_cost_per_million=in_cost,
                output_cost_per_million=out_cost,
                **kwargs,
            )

    def get_pricing(self, model_name: str) -> ModelPricing:
        """Retrieve pricing for model or return default."""
        for name, p in self._rates.items():
            if name.lower() in model_name.lower():
                return p
        return self.default_pricing

    def compute_cost(
        self,
        model_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        embedding_tokens: int = 0,
        tool_calls: int = 0,
    ) -> dict[str, float]:
        """Compute detailed cost breakdown for an execution."""
        pricing = self.get_pricing(model_name)

        in_cost = (input_tokens / 1_000_000.0) * pricing.input_cost_per_million
        out_cost = (output_tokens / 1_000_000.0) * pricing.output_cost_per_million
        cached_cost = (
            cached_tokens / 1_000_000.0
        ) * pricing.cached_input_cost_per_million
        embed_cost = (
            embedding_tokens / 1_000_000.0
        ) * pricing.embedding_cost_per_million
        tool_cost = tool_calls * pricing.cost_per_tool_call

        total = in_cost + out_cost + cached_cost + embed_cost + tool_cost

        return {
            "input_cost": round(in_cost, 6),
            "output_cost": round(out_cost, 6),
            "cached_cost": round(cached_cost, 6),
            "embedding_cost": round(embed_cost, 6),
            "tool_cost": round(tool_cost, 6),
            "total_cost": round(total, 6),
        }
