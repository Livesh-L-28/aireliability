"""Semantic expectations for evaluating AI agent outputs."""

import json
from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    TestCase,
)
from aireliability.evaluation.expectations import BaseExpectation
from aireliability.evaluation.semantic.base import JudgeResult, SemanticJudge
from aireliability.evaluation.semantic.mock_judge import MockSemanticJudge


class SemanticExpectation(BaseExpectation):
    """Evaluates agent output semantics against criteria, reference, and context.

    Utilizes an injectable SemanticJudge (defaults to MockSemanticJudge).
    Preserves model confidence, provider metadata, and detailed evaluation evidence.
    """

    def __init__(
        self,
        *,
        criteria: list[str] | None = None,
        reference: str | None = None,
        context: dict[str, Any] | None = None,
        threshold: float = 0.70,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        failure_type: str = "semantic_violation",
        **metadata: Any,
    ) -> None:
        """Initialize SemanticExpectation.

        Args:
            criteria: Optional explicit criteria (e.g. ['relevance', 'factuality']).
            reference: Optional reference expected text.
            context: Optional grounding context dictionary.
            threshold: Minimum passing score (0.0 to 1.0).
            judge: Optional SemanticJudge provider. If None, uses MockSemanticJudge.
            name: Component name.
            failure_type: FailureType value to attach upon failure.
        """
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"threshold must be between 0.0 and 1.0, got {threshold}")

        super().__init__(
            name=name or "SemanticExpectation",
            threshold=threshold,
            criteria=criteria,
            reference=reference,
            **metadata,
        )
        self.criteria = list(criteria or [])
        self.reference = reference
        self.context = context or {}
        self.threshold = float(threshold)
        self.judge = judge or MockSemanticJudge(threshold=self.threshold)
        self.failure_type = failure_type

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        """Evaluate the execution trace's output semantically."""
        prompt = str(trace.input) if trace.input is not None else ""
        if not prompt and test_case and test_case.input is not None:
            prompt = str(test_case.input)

        # Normalize output to string
        raw_output = trace.output
        if isinstance(raw_output, dict):
            output_str = json.dumps(raw_output)
        elif raw_output is not None:
            output_str = str(raw_output)
        else:
            output_str = ""

        # Grounding reference resolution: explicit reference > test_case.expected_output
        effective_reference = self.reference
        if (
            effective_reference is None
            and test_case
            and test_case.expected_output is not None
        ):
            effective_reference = str(test_case.expected_output)

        # Execute judge
        judge_res: JudgeResult = self.judge.judge(
            prompt=prompt,
            output=output_str,
            reference=effective_reference,
            criteria=self.criteria,
            context=self.context,
        )

        passed = judge_res.score >= self.threshold

        score_f = f"{judge_res.score:.2f}"
        thresh_f = f"{self.threshold:.2f}"
        if passed:
            message = (
                f"Semantic evaluation passed (score {score_f} >= threshold {thresh_f})."
            )
        else:
            message = (
                f"Semantic evaluation failed (score {score_f} < threshold {thresh_f})."
            )
        if judge_res.reasoning:
            message += f" Reason: {judge_res.reasoning}"

        evidence = {
            "score": judge_res.score,
            "threshold": self.threshold,
            "reasoning": judge_res.reasoning,
            "judge_explanation": judge_res.reasoning,
            "evidence": judge_res.evidence,
            "criteria_results": judge_res.criteria_results,
            "provider": judge_res.provider,
            "model": judge_res.model,
            "evaluation_timestamp": judge_res.timestamp.isoformat(),
            "reference": effective_reference,
            "context": self.context,
        }

        # Keep metadata rich for FailureAnalyzer and audit trail
        eval_metadata = {
            **self.metadata,
            "failure_category": "output",
            "failure_type": self.failure_type,
            "confidence": judge_res.confidence,
            "evaluator_type": "semantic",
            "provider": judge_res.provider,
            "model": judge_res.model,
            "score": judge_res.score,
            "threshold": self.threshold,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=judge_res.score,
            message=message,
            evidence=evidence,
            metadata=eval_metadata,
        )


class SemanticRelevance(SemanticExpectation):
    """Evaluates whether agent output is relevant to the user prompt and context."""

    def __init__(
        self,
        *,
        threshold: float = 0.70,
        reference: str | None = None,
        context: dict[str, Any] | None = None,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        criteria = ["relevance to user prompt", "answers the core question"]
        super().__init__(
            criteria=criteria,
            reference=reference,
            context=context,
            threshold=threshold,
            judge=judge,
            name=name or "SemanticRelevance",
            failure_type="semantic_relevance",
            **metadata,
        )


class SemanticSimilarity(SemanticExpectation):
    """Evaluates whether agent output is semantically similar to a reference answer."""

    def __init__(
        self,
        reference: str,
        *,
        threshold: float = 0.75,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(
            reference=reference,
            criteria=["semantic similarity to reference answer"],
            threshold=threshold,
            judge=judge,
            name=name or "SemanticSimilarity",
            failure_type="semantic_similarity",
            **metadata,
        )
