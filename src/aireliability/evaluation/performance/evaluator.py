"""Suite-level performance, throughput, and token velocity evaluation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.metrics.statistics import compute_statistical_summary


class PerformanceSummary(BaseModel):
    """Statistical performance summary across execution traces."""

    model_config = ConfigDict(frozen=True)

    total_requests: int
    throughput_req_per_sec: float
    avg_tokens_per_sec: float
    avg_ttft_ms: float
    timeout_rate: float
    retry_rate: float
    p50_latency_ms: float
    p90_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    mean_latency_ms: float


class PerformanceEvaluator(BaseExpectation):
    """Evaluates latency percentiles, throughput, and token generation speed."""

    def __init__(
        self,
        *,
        max_p95_latency_ms: float = 2500.0,
        min_tokens_per_sec: float = 10.0,
        max_timeout_rate: float = 0.02,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(name=name or "PerformanceEvaluator", **metadata)
        self.max_p95_latency_ms = max_p95_latency_ms
        self.min_tokens_per_sec = min_tokens_per_sec
        self.max_timeout_rate = max_timeout_rate

    def evaluate_suite_performance(
        self,
        traces: list[ExecutionTrace],
    ) -> PerformanceSummary:
        """Compute aggregated statistical summary over traces."""
        if not traces:
            return PerformanceSummary(
                total_requests=0,
                throughput_req_per_sec=0.0,
                avg_tokens_per_sec=0.0,
                avg_ttft_ms=0.0,
                timeout_rate=0.0,
                retry_rate=0.0,
                p50_latency_ms=0.0,
                p90_latency_ms=0.0,
                p95_latency_ms=0.0,
                p99_latency_ms=0.0,
                mean_latency_ms=0.0,
            )

        latencies = [t.latency_ms or 0.0 for t in traces]
        stats = compute_statistical_summary(latencies)

        total_tokens = sum(
            t.token_usage.get("total_tokens", t.token_usage.get("completion_tokens", 0))
            for t in traces
        )
        total_time_sec = (sum(latencies) / 1000.0) if sum(latencies) > 0 else 1.0
        tokens_per_sec = total_tokens / total_time_sec

        # TTFT from metadata
        ttft_vals = [
            float(t.metadata["ttft_ms"]) for t in traces if "ttft_ms" in t.metadata
        ]
        avg_ttft = (sum(ttft_vals) / len(ttft_vals)) if ttft_vals else 0.0

        timeouts = sum(
            1
            for t in traces
            if t.metadata.get("timeout") or t.status.value == "timeout"
        )
        timeout_rate = timeouts / len(traces)

        retries = sum(int(t.metadata.get("retries", 0)) for t in traces)
        retry_rate = retries / len(traces)

        throughput = len(traces) / total_time_sec

        return PerformanceSummary(
            total_requests=len(traces),
            throughput_req_per_sec=round(throughput, 2),
            avg_tokens_per_sec=round(tokens_per_sec, 2),
            avg_ttft_ms=round(avg_ttft, 2),
            timeout_rate=round(timeout_rate, 4),
            retry_rate=round(retry_rate, 4),
            p50_latency_ms=stats.p50,
            p90_latency_ms=stats.p90,
            p95_latency_ms=stats.p95,
            p99_latency_ms=stats.p99,
            mean_latency_ms=stats.mean,
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        """Trace-level evaluation."""
        latency = trace.latency_ms or 0.0
        passed = latency <= self.max_p95_latency_ms
        score = max(0.0, min(1.0, 1.0 - (latency / (self.max_p95_latency_ms * 1.5))))

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=round(score, 4),
            metric="latency_p95_ms",
            threshold=self.max_p95_latency_ms,
            latency=latency,
            message=(
                f"Latency {latency:.1f}ms within threshold {self.max_p95_latency_ms:.1f}ms."
                if passed
                else f"Latency {latency:.1f}ms exceeded threshold {self.max_p95_latency_ms:.1f}ms."
            ),
            evidence={"latency_ms": latency},
            metadata={
                **self.metadata,
                "failure_category": "performance",
                "failure_type": "latency",
            },
        )
