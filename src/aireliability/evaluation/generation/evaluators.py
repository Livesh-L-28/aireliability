"""Evaluators for generative output quality, instruction adherence, and semantic properties."""

from __future__ import annotations

from typing import Any

from aireliability.evaluation.semantic.base import SemanticJudge
from aireliability.evaluation.semantic.expectations import SemanticExpectation


class CorrectnessEvaluator(SemanticExpectation):
    """Evaluates whether agent output is factually and logically correct relative to reference."""

    def __init__(
        self,
        *,
        reference: str | None = None,
        threshold: float = 0.80,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        criteria = [
            "factual correctness",
            "logical validity",
            "agreement with reference answer",
        ]
        super().__init__(
            criteria=criteria,
            reference=reference,
            threshold=threshold,
            judge=judge,
            name=name or "CorrectnessEvaluator",
            failure_type="factual_incorrectness",
            **metadata,
        )


class RelevanceEvaluator(SemanticExpectation):
    """Evaluates whether agent output directly answers and aligns with the user prompt."""

    def __init__(
        self,
        *,
        threshold: float = 0.75,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        criteria = [
            "relevance to prompt",
            "direct response without evasion",
            "conciseness and focus",
        ]
        super().__init__(
            criteria=criteria,
            threshold=threshold,
            judge=judge,
            name=name or "RelevanceEvaluator",
            failure_type="semantic_relevance",
            **metadata,
        )


class CompletenessEvaluator(SemanticExpectation):
    """Evaluates whether agent output thoroughly addresses all parts of the user request."""

    def __init__(
        self,
        *,
        required_topics: list[str] | None = None,
        threshold: float = 0.75,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        criteria = ["thoroughness", "answers all prompt sub-questions"]
        if required_topics:
            criteria.extend([f"covers topic: {t}" for t in required_topics])
        super().__init__(
            criteria=criteria,
            threshold=threshold,
            judge=judge,
            name=name or "CompletenessEvaluator",
            failure_type="incomplete_response",
            required_topics=required_topics or [],
            **metadata,
        )


class CoherenceEvaluator(SemanticExpectation):
    """Evaluates clarity, logical structure, grammatical fluency, and coherence of output."""

    def __init__(
        self,
        *,
        threshold: float = 0.80,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        criteria = [
            "logical flow and transitions",
            "grammatical clarity",
            "absence of contradictory statements",
        ]
        super().__init__(
            criteria=criteria,
            threshold=threshold,
            judge=judge,
            name=name or "CoherenceEvaluator",
            failure_type="incoherent_output",
            **metadata,
        )


class HelpfulnessEvaluator(SemanticExpectation):
    """Evaluates whether agent output provides actionable, constructive, and useful guidance."""

    def __init__(
        self,
        *,
        threshold: float = 0.75,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        criteria = [
            "actionability and practical utility",
            "clarity of advice",
            "constructive and supportive tone",
        ]
        super().__init__(
            criteria=criteria,
            threshold=threshold,
            judge=judge,
            name=name or "HelpfulnessEvaluator",
            failure_type="unhelpful_output",
            **metadata,
        )


class InstructionFollowingEvaluator(SemanticExpectation):
    """Evaluates strict adherence to specified instructions, constraints, and negative criteria."""

    def __init__(
        self,
        instructions: list[str] | None = None,
        *,
        threshold: float = 0.85,
        judge: SemanticJudge | None = None,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        criteria = ["adherence to user instructions and constraints"]
        if instructions:
            criteria.extend([f"must follow: {inst}" for inst in instructions])
        super().__init__(
            criteria=criteria,
            threshold=threshold,
            judge=judge,
            name=name or "InstructionFollowingEvaluator",
            failure_type="instruction_violation",
            instructions=instructions or [],
            **metadata,
        )
