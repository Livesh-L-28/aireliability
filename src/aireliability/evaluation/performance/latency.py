"""Component-level latency attribution and breakdown."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    StepType,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation


class LatencyAttributionEvaluator(BaseExpectation):
    """Attributes and asserts latency across retrieval, reranking, LLM, and tools."""

    def __init__(
        self,
        *,
        max_total_latency_ms: float = 3000.0,
        max_retrieval_latency_ms: float | None = None,
        max_llm_latency_ms: float | None = None,
        max_tool_latency_ms: float | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"LatencyAttributionEvaluator(max={max_total_latency_ms}ms)",
            max_total_latency_ms=max_total_latency_ms,
            **metadata,
        )
        self.max_total_latency_ms = max_total_latency_ms
        self.max_retrieval_latency_ms = max_retrieval_latency_ms
        self.max_llm_latency_ms = max_llm_latency_ms
        self.max_tool_latency_ms = max_tool_latency_ms

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        total_latency = trace.latency_ms or 0.0
        retrieval_latency = 0.0
        llm_latency = 0.0
        tool_latency = 0.0
        rerank_latency = 0.0

        for step in trace.steps:
            d = step.duration_ms or 0.0
            if step.type == StepType.RETRIEVAL:
                if "rerank" in step.name.lower():
                    rerank_latency += d
                else:
                    retrieval_latency += d
            elif step.type == StepType.LLM:
                llm_latency += d
            elif step.type == StepType.TOOL:
                tool_latency += d

        # Check bounds
        total_ok = total_latency <= self.max_total_latency_ms
        retrieval_ok = (
            self.max_retrieval_latency_ms is None
            or retrieval_latency <= self.max_retrieval_latency_ms
        )
        llm_ok = (
            self.max_llm_latency_ms is None or llm_latency <= self.max_llm_latency_ms
        )
        tool_ok = (
            self.max_tool_latency_ms is None or tool_latency <= self.max_tool_latency_ms
        )

        passed = total_ok and retrieval_ok and llm_ok and tool_ok

        # Normalized latency score
        score = max(
            0.0, min(1.0, 1.0 - (total_latency / (self.max_total_latency_ms * 1.5)))
        )

        msg = (
            f"Latency breakdown: Total={total_latency:.1f}ms, LLM={llm_latency:.1f}ms, "
            f"Retrieval={retrieval_latency:.1f}ms, Tools={tool_latency:.1f}ms."
            if passed
            else f"Latency constraint violated (Total {total_latency:.1f}ms > max {self.max_total_latency_ms}ms)."
        )

        evidence = {
            "total_latency_ms": round(total_latency, 2),
            "llm_latency_ms": round(llm_latency, 2),
            "retrieval_latency_ms": round(retrieval_latency, 2),
            "tool_latency_ms": round(tool_latency, 2),
            "rerank_latency_ms": round(rerank_latency, 2),
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=round(score, 4),
            metric="latency_ms",
            threshold=self.max_total_latency_ms,
            latency=total_latency,
            confidence=1.0,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "performance",
                "failure_type": "latency",
                **evidence,
            },
        )
