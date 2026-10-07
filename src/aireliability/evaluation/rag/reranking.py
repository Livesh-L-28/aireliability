"""Reranker evaluation and rank-shift analysis."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.metrics.ranking import (
    ndcg_from_ranking,
)


class RerankingEvaluator(BaseExpectation):
    """Evaluates reranker quality independently, measuring NDCG uplift and position improvements."""

    def __init__(
        self,
        *,
        k: int = 5,
        expected_docs: list[str] | None = None,
        min_ndcg_uplift: float = 0.0,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"RerankingEvaluator(k={k})",
            k=k,
            min_ndcg_uplift=min_ndcg_uplift,
            **metadata,
        )
        self.k = k
        self.expected_docs = expected_docs
        self.min_ndcg_uplift = min_ndcg_uplift

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        expected = list(self.expected_docs or [])
        if not expected and test_case:
            docs = test_case.metadata.get("expected_docs") or test_case.metadata.get(
                "relevant_docs"
            )
            if docs:
                expected = [str(d) for d in docs]

        # Locate pre-rerank and post-rerank items from trace steps
        pre_rerank: list[str] = []
        post_rerank: list[str] = []

        for step in trace.steps:
            if step.metadata.get("reranker") or "rerank" in step.name.lower():
                if isinstance(step.input, list):
                    pre_rerank = [
                        item.get("id", str(item))
                        if isinstance(item, dict)
                        else str(item)
                        for item in step.input
                    ]
                if isinstance(step.output, list):
                    post_rerank = [
                        item.get("id", str(item))
                        if isinstance(item, dict)
                        else str(item)
                        for item in step.output
                    ]

        if not pre_rerank or not post_rerank:
            return EvaluationResult(
                evaluator=self.name,
                passed=True,
                score=1.0,
                metric="reranking_uplift",
                message="No explicit reranker step captured in trace; passed by default.",
                evidence={
                    "pre_rerank_count": len(pre_rerank),
                    "post_rerank_count": len(post_rerank),
                },
                metadata=self.metadata,
            )

        ndcg_pre = ndcg_from_ranking(expected, pre_rerank, self.k) if expected else 0.5
        ndcg_post = (
            ndcg_from_ranking(expected, post_rerank, self.k) if expected else 0.5
        )
        uplift = ndcg_post - ndcg_pre

        passed = uplift >= self.min_ndcg_uplift
        score = max(0.0, min(1.0, 0.5 + uplift))

        msg = (
            f"Reranker achieved NDCG@{self.k} uplift of {uplift:+.3f} "
            f"({ndcg_pre:.3f} → {ndcg_post:.3f})."
            if passed
            else f"Reranker degraded ranking by {uplift:+.3f} "
            f"({ndcg_pre:.3f} → {ndcg_post:.3f}), below required {self.min_ndcg_uplift:+.3f}."
        )

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            metric="reranking_ndcg_uplift",
            threshold=self.min_ndcg_uplift,
            confidence=1.0,
            message=msg,
            evidence={
                "k": self.k,
                "pre_rerank_ndcg": round(ndcg_pre, 4),
                "post_rerank_ndcg": round(ndcg_post, 4),
                "uplift": round(uplift, 4),
                "pre_rerank": pre_rerank[: self.k],
                "post_rerank": post_rerank[: self.k],
            },
            metadata={
                **self.metadata,
                "failure_category": "retrieval",
                "failure_type": "irrelevant_context",
                "uplift": uplift,
            },
        )
