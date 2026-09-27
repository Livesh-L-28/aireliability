"""Deterministic MockSemanticJudge for testing and reproducible evaluation."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aireliability.evaluation.semantic.base import JudgeResult


class MockSemanticJudge:
    """Deterministic mock semantic judge for testing, benchmarking, and CI.

    Does NOT invoke external LLM APIs.
    Explicitly designed to allow reproducible testing of semantic evaluation workflows,
    criteria assessment, threshold triggering, and failure reporting.
    """

    def __init__(
        self,
        *,
        default_score: float | None = None,
        default_passed: bool | None = None,
        default_reasoning: str = "Mock evaluation completed successfully.",
        threshold: float = 0.7,
        confidence: float = 0.95,
        model_name: str = "mock-judge-v1",
        provider_name: str = "mock",
        custom_rule: Callable[
            [str, str, str | None, list[str] | None], tuple[float, str]
        ]
        | None = None,
    ) -> None:
        """Initialize MockSemanticJudge.

        Args:
            default_score: Optional explicit score to return (0.0 to 1.0). If None and
                reference is provided, computes reference word overlap. If None and no
                reference, defaults to 1.0.
            default_passed: If None, computed as (score >= threshold).
            default_reasoning: Human-readable explanation string.
            threshold: Default passing threshold.
            confidence: Judge confidence (defaults to 0.95).
            model_name: Identifier for audit trail.
            provider_name: Provider identifier for audit trail.
            custom_rule: Optional hook (prompt, output, reference, criteria) ->
                (score, reasoning).
        """
        self.name = "MockSemanticJudge"
        self._explicit_default_score = default_score
        self.threshold = float(threshold)
        self.default_passed = default_passed
        self.default_reasoning = default_reasoning
        self.confidence = float(confidence)
        self.model_name = model_name
        self.provider_name = provider_name
        self.custom_rule = custom_rule

    def judge(
        self,
        prompt: str,
        output: str,
        reference: str | None = None,
        criteria: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> JudgeResult:
        """Execute mock evaluation deterministically."""
        criteria_results: dict[str, bool] = {}

        if self.custom_rule is not None:
            score, reasoning = self.custom_rule(prompt, output, reference, criteria)
        elif self._explicit_default_score is not None:
            score = self._explicit_default_score
            reasoning = self.default_reasoning
        elif reference is not None:
            # Deterministic string similarity / keyword heuristic as mock fallback
            ref_words = set(reference.lower().split())
            out_words = set(output.lower().split())
            if ref_words:
                overlap = len(ref_words.intersection(out_words)) / len(ref_words)
                score = round(overlap, 3)
                reasoning = (
                    f"Mock evaluation word overlap: {overlap:.2f} with reference."
                )
            else:
                score = 1.0
                reasoning = self.default_reasoning
        else:
            score = 1.0
            reasoning = self.default_reasoning

        # Check explicit criteria
        if criteria:
            for crit in criteria:
                crit_lower = crit.lower()
                # Basic mock check: if crit mentions 'not contradict' or 'factual'
                crit_passed = True
                if (
                    "timeframe" in crit_lower
                    and "day" not in output.lower()
                    and "hour" not in output.lower()
                ) or (
                    "order" in crit_lower
                    and "123" not in output
                    and "order" not in output.lower()
                ):
                    crit_passed = False
                criteria_results[crit] = crit_passed

            # If any criterion failed, penalize score if at 1.0
            if any(not p for p in criteria_results.values()) and score == 1.0:
                score = 0.5
                reasoning += " (One or more criteria were not satisfied.)"

        passed = score >= self.threshold

        return JudgeResult(
            passed=passed,
            score=score,
            reasoning=reasoning,
            evidence={
                "judge_explanation": reasoning,
                "evaluated_prompt": prompt,
                "evaluated_output": output,
                "reference_provided": reference is not None,
                "criteria_evaluated": criteria or [],
                "context_keys": list((context or {}).keys()),
            },
            criteria_results=criteria_results,
            confidence=self.confidence,
            provider=self.provider_name,
            model=self.model_name,
            timestamp=datetime.now(UTC),
            metadata={"mock": True},
        )
