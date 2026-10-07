"""Cost tracking, economic bounds, and suite-level cost calculations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    TestCase,
)
from aireliability.evaluation.cost.pricing import PricingModel
from aireliability.evaluation.expectations import BaseExpectation


class CostSuiteSummary(BaseModel):
    """Aggregated economic and cost summary across an evaluation suite."""

    model_config = ConfigDict(frozen=True)

    total_cost: float
    cost_per_request: float
    cost_per_successful_task: float
    cost_per_1000_requests: float
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_tokens: int
    cost_by_model: dict[str, float] = Field(default_factory=dict)
    cost_by_user: dict[str, float] = Field(default_factory=dict)


class CostEvaluator(BaseExpectation):
    """Evaluates execution cost against maximum limits using a configurable pricing model."""

    def __init__(
        self,
        *,
        max_cost: float = 0.05,
        model_name: str = "gpt-4o-mini",
        pricing_model: PricingModel | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"CostEvaluator(max=${max_cost:.4f})",
            max_cost=max_cost,
            **metadata,
        )
        self.max_cost = max_cost
        self.model_name = model_name
        self.pricing_model = pricing_model or PricingModel()

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        in_tokens = trace.token_usage.get(
            "prompt_tokens", trace.token_usage.get("input_tokens", 0)
        )
        out_tokens = trace.token_usage.get(
            "completion_tokens", trace.token_usage.get("output_tokens", 0)
        )
        cached_tokens = trace.token_usage.get("cached_tokens", 0)

        # If trace has cost already recorded, use it; else compute
        if trace.cost is not None:
            total_cost = trace.cost
            cost_details = {"total_cost": total_cost}
        else:
            model = trace.metadata.get("model", self.model_name)
            cost_details = self.pricing_model.compute_cost(
                model_name=model,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                cached_tokens=cached_tokens,
            )
            total_cost = cost_details["total_cost"]

        passed = total_cost <= self.max_cost
        score = max(0.0, min(1.0, 1.0 - (total_cost / (self.max_cost * 1.5))))

        msg = (
            f"Cost ${total_cost:.5f} is within limit ${self.max_cost:.5f}."
            if passed
            else f"Cost ${total_cost:.5f} exceeded threshold ${self.max_cost:.5f}."
        )

        evidence = {
            "cost": total_cost,
            "total_cost": total_cost,
            "max_cost": self.max_cost,
            "cost_details": cost_details,
            "in_tokens": in_tokens,
            "out_tokens": out_tokens,
            "cached_tokens": cached_tokens,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=round(score, 4),
            metric="cost_usd",
            threshold=self.max_cost,
            cost=total_cost,
            confidence=1.0,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "performance",
                "failure_type": "cost",
                **evidence,
            },
        )

    def evaluate_suite_cost(
        self,
        traces: list[ExecutionTrace],
        successful_count: int | None = None,
    ) -> CostSuiteSummary:
        """Compute aggregated suite-level economic metrics."""
        if not traces:
            return CostSuiteSummary(
                total_cost=0.0,
                cost_per_request=0.0,
                cost_per_successful_task=0.0,
                cost_per_1000_requests=0.0,
                total_input_tokens=0,
                total_output_tokens=0,
                total_cached_tokens=0,
                total_tokens=0,
            )

        total_cost = 0.0
        in_tokens = 0
        out_tokens = 0
        cached_tokens = 0
        by_model: dict[str, float] = {}
        by_user: dict[str, float] = {}

        for t in traces:
            t_in = t.token_usage.get(
                "prompt_tokens", t.token_usage.get("input_tokens", 0)
            )
            t_out = t.token_usage.get(
                "completion_tokens", t.token_usage.get("output_tokens", 0)
            )
            t_cached = t.token_usage.get("cached_tokens", 0)

            in_tokens += t_in
            out_tokens += t_out
            cached_tokens += t_cached

            model = t.metadata.get("model", self.model_name)
            cost_dict = self.pricing_model.compute_cost(model, t_in, t_out, t_cached)
            cost = t.cost if t.cost is not None else cost_dict["total_cost"]
            total_cost += cost

            by_model[model] = by_model.get(model, 0.0) + cost
            user_id = t.metadata.get("user_id") or t.metadata.get(
                "tenant_id", "default"
            )
            by_user[user_id] = by_user.get(user_id, 0.0) + cost

        n = len(traces)
        succ = (
            successful_count
            if successful_count is not None and successful_count > 0
            else n
        )
        cost_per_req = total_cost / n
        cost_per_succ = total_cost / succ
        cost_per_1k = cost_per_req * 1000.0

        return CostSuiteSummary(
            total_cost=round(total_cost, 5),
            cost_per_request=round(cost_per_req, 6),
            cost_per_successful_task=round(cost_per_succ, 6),
            cost_per_1000_requests=round(cost_per_1k, 4),
            total_input_tokens=in_tokens,
            total_output_tokens=out_tokens,
            total_cached_tokens=cached_tokens,
            total_tokens=in_tokens + out_tokens,
            cost_by_model={k: round(v, 5) for k, v in by_model.items()},
            cost_by_user={k: round(v, 5) for k, v in by_user.items()},
        )
