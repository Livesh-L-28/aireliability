"""SLI/SLO tracking, error-budget calculations, and burn rates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from aireliability.observability.aggregation import TelemetryAggregator


class SLIEvaluation(BaseModel):
    """Result of evaluating an SLI."""

    sli_name: str
    observed_value: float
    total_samples: int
    good_samples: int


class SLOEvaluation(BaseModel):
    """Result of evaluating an SLO and error budget."""

    slo_id: str
    name: str
    target: float
    actual_value: float
    compliant: bool
    allowed_error_budget: float
    consumed_error_budget: float
    remaining_error_budget: float
    budget_percentage: float
    burn_rate: float
    details: dict[str, Any] = Field(default_factory=dict)


class SLI:
    """Service Level Indicator definition."""

    def __init__(
        self,
        name: str,
        description: str = "",
        evaluator: (
            Callable[[TelemetryAggregator, float, str | None], SLIEvaluation] | None
        ) = None,
    ) -> None:
        self.name = name
        self.description = description
        self.evaluator = evaluator

    def evaluate(
        self,
        aggregator: TelemetryAggregator,
        window_seconds: float = 300.0,
        tenant_id: str | None = None,
    ) -> SLIEvaluation:
        """Evaluate SLI against aggregated telemetry."""
        if self.evaluator:
            return self.evaluator(aggregator, window_seconds, tenant_id)

        # Standard built-in evaluators
        stats = aggregator.aggregate(window_seconds, tenant_id)
        if self.name in ("success_rate", "worker_success_rate"):
            completions = stats["job_completions"]
            failures = stats["job_failures"]
            total = completions + failures
            ratio = (completions / total) if total > 0 else 1.0
            return SLIEvaluation(
                sli_name=self.name,
                observed_value=ratio,
                total_samples=total,
                good_samples=completions,
            )

        if self.name == "availability":
            total = stats["total_events"]
            errors = stats["job_failures"] + stats["auth_failures"]
            good = max(0, total - errors)
            ratio = (good / total) if total > 0 else 1.0
            return SLIEvaluation(
                sli_name=self.name,
                observed_value=ratio,
                total_samples=total,
                good_samples=good,
            )

        if self.name == "latency":
            lat = stats["latency"]
            p95 = lat.get("p95", 0.0)
            return SLIEvaluation(
                sli_name=self.name,
                observed_value=p95,
                total_samples=int(lat.get("count", 0)),
                good_samples=int(lat.get("count", 0)),
            )

        return SLIEvaluation(
            sli_name=self.name,
            observed_value=1.0,
            total_samples=0,
            good_samples=0,
        )


class SLO:
    """Service Level Objective with target and error budget computation."""

    def __init__(
        self,
        name: str,
        sli: SLI,
        target: float,
        window_seconds: float = 300.0,
        slo_id: str | None = None,
        is_latency: bool = False,
        max_latency_seconds: float | None = None,
    ) -> None:
        self.slo_id = slo_id or str(uuid4())
        self.name = name
        self.sli = sli
        self.target = target
        self.window_seconds = window_seconds
        self.is_latency = is_latency
        self.max_latency_seconds = max_latency_seconds

    def evaluate(
        self,
        aggregator: TelemetryAggregator,
        tenant_id: str | None = None,
    ) -> SLOEvaluation:
        """Evaluate SLO compliance and calculate error budget."""
        sli_res = self.sli.evaluate(
            aggregator,
            window_seconds=self.window_seconds,
            tenant_id=tenant_id,
        )

        if self.is_latency and self.max_latency_seconds is not None:
            # Latency target: observed latency <= max_latency_seconds
            compliant = sli_res.observed_value <= self.max_latency_seconds
            allowed_budget = 1.0 - self.target
            consumed_budget = (
                0.0 if compliant else 1.0 - self.target
            )  # Binary indicator
            remaining_budget = max(0.0, allowed_budget - consumed_budget)
            budget_pct = (
                (remaining_budget / allowed_budget * 100.0)
                if allowed_budget > 0
                else 100.0
            )
            burn_rate = (
                (consumed_budget / allowed_budget) if allowed_budget > 0 else 0.0
            )

            return SLOEvaluation(
                slo_id=self.slo_id,
                name=self.name,
                target=self.target,
                actual_value=sli_res.observed_value,
                compliant=compliant,
                allowed_error_budget=allowed_budget,
                consumed_error_budget=consumed_budget,
                remaining_error_budget=remaining_budget,
                budget_percentage=budget_pct,
                burn_rate=burn_rate,
                details={
                    "total_samples": sli_res.total_samples,
                    "max_latency_seconds": self.max_latency_seconds,
                },
            )

        # Ratio target (e.g. 99.9% = 0.999)
        actual = sli_res.observed_value
        compliant = actual >= self.target

        # Error budget calculations:
        # If target = 0.999, allowed error rate = 0.001
        allowed_error_rate = max(1e-9, 1.0 - self.target)
        actual_error_rate = max(0.0, 1.0 - actual)

        consumed_fraction = actual_error_rate / allowed_error_rate
        burn_rate = consumed_fraction
        budget_pct = max(0.0, min(100.0, (1.0 - consumed_fraction) * 100.0))

        total_samples = sli_res.total_samples
        allowed_errors = allowed_error_rate * total_samples
        consumed_errors = actual_error_rate * total_samples
        remaining_errors = max(0.0, allowed_errors - consumed_errors)

        return SLOEvaluation(
            slo_id=self.slo_id,
            name=self.name,
            target=self.target,
            actual_value=actual,
            compliant=compliant,
            allowed_error_budget=allowed_errors,
            consumed_error_budget=consumed_errors,
            remaining_error_budget=remaining_errors,
            budget_percentage=budget_pct,
            burn_rate=burn_rate,
            details={
                "total_samples": total_samples,
                "good_samples": sli_res.good_samples,
            },
        )


class SLOManager:
    """Registry and evaluator for SLIs and SLOs."""

    def __init__(self, aggregator: TelemetryAggregator) -> None:
        self.aggregator = aggregator
        self.slis: dict[str, SLI] = {}
        self.slos: dict[str, SLO] = {}
        self._register_default_slis()

    def _register_default_slis(self) -> None:
        """Register out-of-the-box standard SLIs."""
        self.register_sli("success_rate", "Ratio of successful job executions")
        self.register_sli("availability", "Ratio of successful non-error events")
        self.register_sli("latency", "p95 job execution latency")
        self.register_sli("worker_success_rate", "Worker job completion success rate")

    def register_sli(
        self,
        name: str,
        description: str = "",
        evaluator: (
            Callable[[TelemetryAggregator, float, str | None], SLIEvaluation] | None
        ) = None,
    ) -> SLI:
        sli = SLI(name, description, evaluator)
        self.slis[name] = sli
        return sli

    def register_slo(
        self,
        name: str,
        sli_name: str,
        target: float,
        window_seconds: float = 300.0,
        is_latency: bool = False,
        max_latency_seconds: float | None = None,
    ) -> SLO:
        if sli_name not in self.slis:
            self.register_sli(sli_name)
        sli = self.slis[sli_name]
        slo = SLO(
            name=name,
            sli=sli,
            target=target,
            window_seconds=window_seconds,
            is_latency=is_latency,
            max_latency_seconds=max_latency_seconds,
        )
        self.slos[slo.slo_id] = slo
        return slo

    def evaluate_slo(
        self, slo_id: str, tenant_id: str | None = None
    ) -> SLOEvaluation | None:
        """Evaluate a specific SLO."""
        slo = self.slos.get(slo_id)
        if not slo:
            return None
        return slo.evaluate(self.aggregator, tenant_id=tenant_id)

    def evaluate_all(self, tenant_id: str | None = None) -> list[SLOEvaluation]:
        """Evaluate all registered SLOs."""
        return [
            slo.evaluate(self.aggregator, tenant_id=tenant_id)
            for slo in self.slos.values()
        ]

    def list_slos(self) -> list[SLO]:
        """List all configured SLOs."""
        return list(self.slos.values())
