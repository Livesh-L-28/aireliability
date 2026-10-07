"""Hallucination, groundedness, and faithfulness evaluators."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    StepType,
    TestCase,
)
from aireliability.evaluation.claim.classifier import ClaimClassifier
from aireliability.evaluation.claim.extractor import ClaimExtractor
from aireliability.evaluation.claim.models import (
    ClaimClassification,
    ClaimEvaluationSummary,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.semantic.base import SemanticJudge


def _extract_context_from_trace(
    trace: ExecutionTrace, test_case: TestCase | None = None
) -> dict[str, str]:
    """Gather all context text from trace steps, test case metadata, or input."""
    docs: dict[str, str] = {}

    # Check test_case context
    if test_case:
        if isinstance(test_case.metadata.get("context"), dict):
            for k, v in test_case.metadata["context"].items():
                docs[str(k)] = str(v)
        elif isinstance(test_case.metadata.get("context"), list):
            for idx, item in enumerate(test_case.metadata["context"]):
                docs[f"tc_doc_{idx}"] = str(item)
        elif isinstance(test_case.metadata.get("context"), str):
            docs["test_case_context"] = test_case.metadata["context"]

        if isinstance(test_case.metadata.get("context_docs"), list):
            for idx, item in enumerate(test_case.metadata["context_docs"]):
                docs[f"tc_doc_{idx}"] = str(item)
        elif isinstance(test_case.metadata.get("context_docs"), dict):
            for k, v in test_case.metadata["context_docs"].items():
                docs[str(k)] = str(v)
        elif isinstance(test_case.metadata.get("context_docs"), str):
            docs["test_case_context_docs"] = test_case.metadata["context_docs"]

    # Check retrieval steps in trace
    for idx, step in enumerate(trace.steps):
        if step.type == StepType.RETRIEVAL:
            doc_id = step.metadata.get("doc_id", f"retrieval_step_{idx}")
            if isinstance(step.output, str):
                docs[str(doc_id)] = step.output
            elif isinstance(step.output, list):
                for sub_idx, item in enumerate(step.output):
                    if isinstance(item, dict):
                        sub_id = item.get("id", f"{doc_id}_{sub_idx}")
                        content = item.get("content") or item.get("text") or str(item)
                        docs[str(sub_id)] = str(content)
                    else:
                        docs[f"{doc_id}_{sub_idx}"] = str(item)

    # Check trace metadata
    if isinstance(trace.metadata.get("context"), dict):
        for k, v in trace.metadata["context"].items():
            docs[str(k)] = str(v)
    elif isinstance(trace.metadata.get("context"), str):
        docs["trace_context"] = trace.metadata["context"]

    return docs


class HallucinationEvaluator(BaseExpectation):
    """Evaluates hallucination rate by extracting atomic claims and verifying against context."""

    def __init__(
        self,
        *,
        max_hallucination_rate: float = 0.0,
        judge: SemanticJudge | None = None,
        extractor: ClaimExtractor | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name
            or f"HallucinationEvaluator(max_rate={max_hallucination_rate:.2f})",
            max_hallucination_rate=max_hallucination_rate,
            **metadata,
        )
        self.max_hallucination_rate = max_hallucination_rate
        self.extractor = extractor or ClaimExtractor()
        self.classifier = ClaimClassifier(judge=judge)

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        output_str = str(trace.output) if trace.output is not None else ""
        claims = self.extractor.extract(output_str)

        if not claims:
            return EvaluationResult(
                evaluator=self.name,
                passed=True,
                score=1.0,
                metric="hallucination_rate",
                threshold=self.max_hallucination_rate,
                message="No claims extracted from output to evaluate.",
                evidence={"total_claims": 0, "hallucination_rate": 0.0},
                metadata={
                    **self.metadata,
                    "failure_category": "output",
                    "failure_type": "hallucination",
                },
            )

        context_docs = _extract_context_from_trace(trace, test_case)
        verifications = self.classifier.classify_all(claims, context_docs)

        total = len(verifications)
        supported = sum(
            1 for v in verifications if v.status == ClaimClassification.SUPPORTED
        )
        unsupported = sum(
            1 for v in verifications if v.status == ClaimClassification.UNSUPPORTED
        )
        contradicted = sum(
            1 for v in verifications if v.status == ClaimClassification.CONTRADICTED
        )

        hallucination_count = unsupported + contradicted
        hallucination_rate = hallucination_count / total
        grounded_rate = supported / total
        contradiction_rate = contradicted / total
        unsupported_rate = unsupported / total

        passed = hallucination_rate <= self.max_hallucination_rate
        # Score is groundedness proportion (1.0 - hallucination_rate)
        score = round(1.0 - hallucination_rate, 4)

        summary = ClaimEvaluationSummary(
            total_claims=total,
            supported_claims=supported,
            unsupported_claims=unsupported,
            contradicted_claims=contradicted,
            hallucination_rate=round(hallucination_rate, 4),
            grounded_claim_rate=round(grounded_rate, 4),
            contradiction_rate=round(contradiction_rate, 4),
            unsupported_claim_rate=round(unsupported_rate, 4),
            verifications=verifications,
        )

        msg = (
            f"Hallucination rate {hallucination_rate:.2%} is within maximum "
            f"allowed {self.max_hallucination_rate:.2%} ({supported}/{total} claims grounded)."
            if passed
            else f"Hallucination rate {hallucination_rate:.2%} exceeded threshold "
            f"{self.max_hallucination_rate:.2%} ({hallucination_count}/{total} ungrounded/contradicted claims)."
        )

        evidence = {
            "hallucination_rate": round(hallucination_rate, 4),
            "grounded_rate": round(grounded_rate, 4),
            "summary": summary.model_dump(),
            "unsupported_claims": [
                v.claim.text
                for v in verifications
                if v.status == ClaimClassification.UNSUPPORTED
            ],
            "contradicted_claims": [
                v.claim.text
                for v in verifications
                if v.status == ClaimClassification.CONTRADICTED
            ],
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            metric="hallucination_rate",
            threshold=self.max_hallucination_rate,
            confidence=0.95,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "output",
                "failure_type": "hallucination",
                "hallucination_rate": hallucination_rate,
                "grounded_claim_rate": grounded_rate,
            },
        )


class GroundednessEvaluator(BaseExpectation):
    """Asserts that the proportion of context-grounded claims meets the minimum threshold."""

    def __init__(
        self,
        *,
        min_grounded_rate: float = 0.90,
        min_grounded_score: float | None = None,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        effective_rate = (
            min_grounded_score if min_grounded_score is not None else min_grounded_rate
        )
        super().__init__(
            name=name or f"GroundednessEvaluator(min_rate={effective_rate:.2f})",
            min_grounded_rate=effective_rate,
            **metadata,
        )
        self.min_grounded_rate = effective_rate
        # Delegates to HallucinationEvaluator with complementary threshold
        self._hallucination_eval = HallucinationEvaluator(
            max_hallucination_rate=round(1.0 - effective_rate, 4),
            judge=judge,
            name=self.name,
            **metadata,
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        res = self._hallucination_eval.evaluate(trace, test_case)
        grounded_rate = res.metadata.get("grounded_claim_rate", res.score or 1.0)
        passed = grounded_rate >= self.min_grounded_rate

        msg = (
            f"Groundedness rate {grounded_rate:.2%} satisfies threshold {self.min_grounded_rate:.2%}."
            if passed
            else f"Groundedness rate {grounded_rate:.2%} below threshold {self.min_grounded_rate:.2%}."
        )

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=round(grounded_rate, 4),
            metric="grounded_claim_rate",
            threshold=self.min_grounded_rate,
            confidence=res.confidence,
            message=msg,
            evidence=res.evidence,
            metadata={
                **self.metadata,
                "failure_category": "output",
                "failure_type": "unsupported_claim",
                "grounded_rate": grounded_rate,
            },
        )


class FaithfulnessEvaluator(BaseExpectation):
    """Asserts that output is strictly faithful to context without any contradictions."""

    def __init__(
        self,
        *,
        allow_unsupported: bool = False,
        min_faithfulness_score: float | None = None,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            name=name or "FaithfulnessEvaluator",
            allow_unsupported=allow_unsupported,
            min_faithfulness_score=min_faithfulness_score,
            **metadata,
        )
        self.allow_unsupported = allow_unsupported
        self.min_faithfulness_score = min_faithfulness_score
        max_rate = (
            1.0
            if allow_unsupported
            else (
                round(1.0 - min_faithfulness_score, 4)
                if min_faithfulness_score is not None
                else 0.05
            )
        )
        self._hallucination_eval = HallucinationEvaluator(
            max_hallucination_rate=max_rate,
            judge=judge,
            name=self.name,
            **metadata,
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        res = self._hallucination_eval.evaluate(trace, test_case)
        contradicted_count = len(res.evidence.get("contradicted_claims", []))
        has_contradictions = contradicted_count > 0

        passed = not has_contradictions and (res.passed or self.allow_unsupported)
        score = 0.0 if has_contradictions else (res.score or 1.0)

        msg = (
            "Output is faithful to context with zero detected contradictions."
            if passed
            else f"Output failed faithfulness evaluation: {contradicted_count} contradiction(s) found."
        )

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            metric="faithfulness",
            threshold=1.0,
            message=msg,
            evidence=res.evidence,
            metadata={
                **self.metadata,
                "failure_category": "output",
                "failure_type": "hallucination",
                "contradicted_count": contradicted_count,
            },
        )
