"""End-to-end RAG pipeline evaluator and failure attribution."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    TestCase,
)
from aireliability.diagnosis.models import (
    Evidence,
    RootCause,
    RootCauseCategory,
    RootCauseReport,
    RootCauseType,
)
from aireliability.evaluation.claim.hallucination import HallucinationEvaluator
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.rag.context import ContextEvaluator
from aireliability.evaluation.rag.retrieval import RetrievalEvaluator
from aireliability.evaluation.semantic.base import SemanticJudge


class RAGEvaluator(BaseExpectation):
    """End-to-end RAG evaluator attributing failures to retrieval vs generation."""

    def __init__(
        self,
        *,
        retrieval_k: int = 5,
        min_retrieval_score: float = 0.50,
        max_hallucination_rate: float = 0.05,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "RAGEvaluator",
            retrieval_k=retrieval_k,
            min_retrieval_score=min_retrieval_score,
            max_hallucination_rate=max_hallucination_rate,
            **metadata,
        )
        self.retrieval_k = retrieval_k
        self.min_retrieval_score = min_retrieval_score
        self.max_hallucination_rate = max_hallucination_rate
        self.retrieval_eval = RetrievalEvaluator(
            k=retrieval_k, min_recall=min_retrieval_score, **metadata
        )
        self.context_eval = ContextEvaluator(judge=judge, **metadata)
        self.generation_eval = HallucinationEvaluator(
            max_hallucination_rate=max_hallucination_rate, judge=judge, **metadata
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        # Run sub-evaluations
        res_retrieval = self.retrieval_eval.evaluate(trace, test_case)
        res_context = self.context_eval.evaluate(trace, test_case)
        res_generation = self.generation_eval.evaluate(trace, test_case)

        retrieval_ok = res_retrieval.passed and res_context.passed
        generation_ok = res_generation.passed

        passed = retrieval_ok and generation_ok

        # Determine attribution
        attribution = "NONE"
        failure_category = "none"
        failure_type = "none"
        root_cause_type = RootCauseType.UNKNOWN
        root_cause_cat = RootCauseCategory.UNKNOWN

        if not passed:
            if not retrieval_ok:
                attribution = "RETRIEVAL_FAILURE"
                failure_category = "retrieval"
                failure_type = (
                    "missing_context"
                    if not res_retrieval.passed
                    else "irrelevant_context"
                )
                root_cause_cat = RootCauseCategory.RETRIEVAL
                root_cause_type = RootCauseType.MISSING_CONTEXT
                msg = (
                    f"RAG Failure attributed to RETRIEVAL: {res_retrieval.message} | "
                    f"Context score: {res_context.score:.2f}."
                )
            else:
                attribution = "GENERATION_FAILURE"
                failure_category = "output"
                failure_type = "hallucination"
                root_cause_cat = RootCauseCategory.OUTPUT
                root_cause_type = RootCauseType.UNEXPECTED_OUTPUT
                msg = (
                    f"RAG Failure attributed to GENERATION (retrieval succeeded, but answer ungrounded): "
                    f"{res_generation.message}."
                )
        else:
            msg = (
                f"RAG Pipeline verified successfully: retrieval score {res_retrieval.score:.2f}, "
                f"context score {res_context.score:.2f}, generation score {res_generation.score:.2f}."
            )

        composite_score = round(
            (
                (res_retrieval.score or 0.0)
                + (res_context.score or 0.0)
                + (res_generation.score or 0.0)
            )
            / 3.0,
            4,
        )

        evidence = {
            "attribution": attribution,
            "failure_stage": failure_category,
            "retrieval_passed": res_retrieval.passed,
            "retrieval_score": res_retrieval.score,
            "context_passed": res_context.passed,
            "context_score": res_context.score,
            "generation_passed": res_generation.passed,
            "generation_score": res_generation.score,
            "retrieval_evidence": res_retrieval.evidence,
            "context_evidence": res_context.evidence,
            "generation_evidence": res_generation.evidence,
        }

        # Synthesize a RootCauseReport if failure occurs
        root_cause_report: RootCauseReport | None = None
        if not passed:
            rc = RootCause(
                category=root_cause_cat,
                type=root_cause_type,
                description=msg,
                confidence=0.95,
                evidence=[
                    Evidence(
                        source="rag_pipeline_evaluator",
                        trace_id=trace.trace_id,
                        field="attribution",
                        expected="SUCCESS",
                        actual=attribution,
                        explanation=msg,
                    )
                ],
            )
            root_cause_report = RootCauseReport(
                test_id=trace.test_id,
                trace_id=trace.trace_id,
                status="FAIL",
                primary_cause=rc,
                summary=f"RAG pipeline failure: {attribution}",
            )
            dumped_rc = root_cause_report.model_dump()
            evidence["root_cause_diagnosis"] = dumped_rc
            evidence["root_cause_report"] = dumped_rc

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=composite_score,
            metric="rag_pipeline_score",
            threshold=self.min_retrieval_score,
            confidence=0.95,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": failure_category,
                "failure_type": failure_type,
                "attribution": attribution,
            },
        )
