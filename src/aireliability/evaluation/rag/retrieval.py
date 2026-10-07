"""Retrieval quality and ranking evaluators."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    StepType,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.metrics.ranking import (
    hit_at_k,
    ndcg_from_ranking,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def _extract_retrieved_items(trace: ExecutionTrace) -> list[str]:
    """Extract list of retrieved document IDs or text identifiers from trace steps."""
    retrieved: list[str] = []
    for step in trace.steps:
        if step.type == StepType.RETRIEVAL:
            if isinstance(step.output, list):
                for item in step.output:
                    if isinstance(item, dict) and "id" in item:
                        retrieved.append(str(item["id"]))
                    elif isinstance(item, str):
                        retrieved.append(item)
                    else:
                        retrieved.append(str(item))
            elif isinstance(step.output, dict) and "id" in step.output:
                retrieved.append(str(step.output["id"]))
            elif step.metadata.get("doc_id"):
                retrieved.append(str(step.metadata["doc_id"]))
            elif step.output is not None:
                retrieved.append(str(step.output))
    return retrieved


class RetrievalEvaluator(BaseExpectation):
    """Evaluates retriever performance against ground-truth relevant documents."""

    def __init__(
        self,
        *,
        k: int = 5,
        expected_docs: list[str] | None = None,
        min_recall: float = 0.50,
        min_ndcg: float = 0.50,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or f"RetrievalEvaluator(k={k})",
            k=k,
            min_recall=min_recall,
            min_ndcg=min_ndcg,
            **metadata,
        )
        self.k = k
        self.expected_docs = expected_docs
        self.min_recall = min_recall
        self.min_ndcg = min_ndcg

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        # Determine expected documents
        expected: list[str] = list(self.expected_docs or [])
        if not expected and test_case:
            if isinstance(test_case.metadata.get("expected_docs"), list):
                expected = [str(d) for d in test_case.metadata["expected_docs"]]
            elif isinstance(test_case.metadata.get("relevant_docs"), list):
                expected = [str(d) for d in test_case.metadata["relevant_docs"]]
            elif isinstance(test_case.metadata.get("context_ids"), list):
                expected = [str(d) for d in test_case.metadata["context_ids"]]

        retrieved = _extract_retrieved_items(trace)

        if not expected:
            return EvaluationResult(
                evaluator=self.name,
                passed=len(retrieved) > 0,
                score=1.0 if retrieved else 0.0,
                metric="retrieval_success",
                message=f"Retrieved {len(retrieved)} item(s); no ground-truth reference provided.",
                evidence={
                    "retrieved_count": len(retrieved),
                    "retrieved": retrieved[: self.k],
                },
                metadata={
                    **self.metadata,
                    "failure_category": "retrieval",
                    "failure_type": "missing_context",
                },
            )

        p_at_k = precision_at_k(expected, retrieved, self.k)
        r_at_k = recall_at_k(expected, retrieved, self.k)
        h_at_k = hit_at_k(expected, retrieved, self.k)
        rr = reciprocal_rank(expected, retrieved)
        ndcg = ndcg_from_ranking(expected, retrieved, self.k)

        passed = (r_at_k >= self.min_recall) and (ndcg >= self.min_ndcg)

        msg = (
            f"Retrieval PASSED: Recall@{self.k}={r_at_k:.2f}, NDCG@{self.k}={ndcg:.2f}, "
            f"Precision@{self.k}={p_at_k:.2f}, MRR={rr:.2f}."
            if passed
            else f"Retrieval FAILED: Recall@{self.k}={r_at_k:.2f} (min {self.min_recall:.2f}), "
            f"NDCG@{self.k}={ndcg:.2f} (min {self.min_ndcg:.2f})."
        )

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=round(ndcg, 4),
            metric=f"ndcg@{self.k}",
            threshold=self.min_ndcg,
            confidence=1.0,
            message=msg,
            evidence={
                "k": self.k,
                "precision_at_k": round(p_at_k, 4),
                "recall_at_k": round(r_at_k, 4),
                "hit_at_k": h_at_k,
                "reciprocal_rank": round(rr, 4),
                "ndcg_at_k": round(ndcg, 4),
                "expected": expected,
                "retrieved": retrieved[: self.k],
            },
            metadata={
                **self.metadata,
                "failure_category": "retrieval",
                "failure_type": "irrelevant_context"
                if h_at_k == 0
                else "missing_context",
                "recall_at_k": r_at_k,
                "ndcg": ndcg,
            },
        )
