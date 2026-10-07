"""Context quality evaluators for RAG systems."""

from __future__ import annotations

import re
from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    StepType,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.semantic.base import SemanticJudge


class ContextEvaluator(BaseExpectation):
    """Evaluates context precision, recall, relevance, coverage, sufficiency, and utilization."""

    def __init__(
        self,
        *,
        min_relevance: float = 0.25,
        min_sufficiency: float = 0.25,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "ContextEvaluator",
            min_relevance=min_relevance,
            min_sufficiency=min_sufficiency,
            **metadata,
        )
        self.min_relevance = min_relevance
        self.min_sufficiency = min_sufficiency
        self.judge = judge

    def _extract_contexts(
        self, trace: ExecutionTrace, test_case: TestCase | None
    ) -> list[str]:
        chunks: list[str] = []
        for step in trace.steps:
            if step.type == StepType.RETRIEVAL:
                if isinstance(step.output, list):
                    for item in step.output:
                        if isinstance(item, dict):
                            content = (
                                item.get("text")
                                or item.get("content")
                                or item.get("chunk")
                            )
                            if content:
                                chunks.append(str(content))
                        elif isinstance(item, str) and not item.startswith("{"):
                            chunks.append(item)
                elif step.output is not None:
                    chunks.append(str(step.output))
        if test_case:
            ctx = test_case.metadata.get("context_docs") or test_case.metadata.get(
                "context"
            )
            if isinstance(ctx, dict):
                chunks.extend(str(v) for v in ctx.values())
            elif isinstance(ctx, list):
                chunks.extend(str(v) for v in ctx)
            elif ctx:
                chunks.append(str(ctx))
        return chunks

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        query = str(trace.input or (test_case.input if test_case else ""))
        output = str(trace.output or "")
        chunks = self._extract_contexts(trace, test_case)

        if not chunks:
            return EvaluationResult(
                evaluator=self.name,
                passed=False,
                score=0.0,
                metric="context_sufficiency",
                threshold=self.min_sufficiency,
                message="No context found in trace retrieval steps or test case.",
                evidence={"chunks_count": 0},
                metadata={
                    **self.metadata,
                    "failure_category": "retrieval",
                    "failure_type": "missing_context",
                },
            )

        query_words = set(re.findall(r"\w+", query.lower()))
        output_words = set(re.findall(r"\w+", output.lower()))

        # 1. Context precision: chunks containing query terms
        relevant_chunks = 0
        utilized_chunks = 0
        chunk_relevances: list[float] = []

        for ch in chunks:
            ch_words = set(re.findall(r"\w+", ch.lower()))
            overlap_q = (
                len(query_words.intersection(ch_words)) / len(query_words)
                if query_words
                else 0.5
            )
            overlap_out = (
                len(output_words.intersection(ch_words)) / len(output_words)
                if output_words
                else 0.0
            )
            chunk_relevances.append(overlap_q)
            if overlap_q >= 0.25:
                relevant_chunks += 1
            if overlap_out >= 0.20:
                utilized_chunks += 1

        context_precision = relevant_chunks / len(chunks)
        context_relevance = sum(chunk_relevances) / len(chunk_relevances)
        context_utilization = utilized_chunks / len(chunks)
        context_sufficiency = min(1.0, (context_precision + context_relevance) / 1.5)
        context_coverage = min(1.0, len(chunks) / 3.0)

        passed = (
            context_relevance >= self.min_relevance
            and context_sufficiency >= self.min_sufficiency
        )
        composite_score = round(
            (context_precision + context_relevance + context_sufficiency) / 3.0, 4
        )

        msg = (
            f"Context evaluated: precision={context_precision:.2f}, "
            f"relevance={context_relevance:.2f}, sufficiency={context_sufficiency:.2f}, "
            f"utilization={context_utilization:.2f}."
        )

        evidence = {
            "chunks_count": len(chunks),
            "context_precision": round(context_precision, 4),
            "context_relevance": round(context_relevance, 4),
            "context_coverage": round(context_coverage, 4),
            "context_sufficiency": round(context_sufficiency, 4),
            "context_utilization": round(context_utilization, 4),
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=composite_score,
            metric="context_relevance",
            threshold=self.min_relevance,
            confidence=0.95,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "retrieval",
                "failure_type": "irrelevant_context" if not passed else "none",
                **evidence,
            },
        )
