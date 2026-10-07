"""Evaluator registry and discovery engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aireliability.core.protocols import Evaluator


class EvaluatorRegistry:
    """Thread-safe registry for discovering, registering, and instantiating evaluators."""

    _registry: dict[str, type[Evaluator] | Callable[..., Evaluator]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        evaluator_cls: type[Evaluator] | Callable[..., Evaluator],
    ) -> None:
        """Register an evaluator under a specific name."""
        cls._registry[name.lower()] = evaluator_cls

    @classmethod
    def get(cls, name: str, **kwargs: Any) -> Evaluator:
        """Instantiate an evaluator by name with supplied kwargs."""
        key = name.lower()
        if key not in cls._registry:
            # Check prefix/substring matching or strip parens
            clean_key = key.split("(")[0].strip()
            if clean_key in cls._registry:
                factory = cls._registry[clean_key]
                return factory(**kwargs)
            if f"{clean_key}evaluator" in cls._registry:
                factory = cls._registry[f"{clean_key}evaluator"]
                return factory(**kwargs)
            if clean_key.endswith("evaluator"):
                short = clean_key[:-9]
                if short in cls._registry:
                    factory = cls._registry[short]
                    return factory(**kwargs)
            raise KeyError(
                f"Evaluator '{name}' is not registered. Available: {cls.list_evaluators()}"
            )
        factory = cls._registry[key]
        return factory(**kwargs)

    @classmethod
    def list_evaluators(cls) -> list[str]:
        """Return sorted list of all registered evaluator names."""
        return sorted(cls._registry.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check whether an evaluator name is registered."""
        clean_key = name.lower().split("(")[0].strip()
        return clean_key in cls._registry


def register_evaluator(name: str) -> Callable[[Any], Any]:
    """Decorator to register a custom evaluator in the global EvaluatorRegistry."""

    def decorator(cls_or_fn: Any) -> Any:
        EvaluatorRegistry.register(name, cls_or_fn)
        return cls_or_fn

    return decorator


# Auto-register all standard built-in evaluators
def _initialize_builtins() -> None:
    # 1. Deterministic expectations
    from aireliability.evaluation.agents import (
        AgentEvaluator,
        ToolUsageEvaluator,
        TrajectoryEvaluator,
    )
    from aireliability.evaluation.claim.hallucination import (
        FaithfulnessEvaluator,
        GroundednessEvaluator,
        HallucinationEvaluator,
    )
    from aireliability.evaluation.consistency import ConsistencyEvaluator
    from aireliability.evaluation.cost import CostEvaluator
    from aireliability.evaluation.expectations import (
        MaxCost,
        MaxLatency,
        OutputContains,
        OutputEquals,
        SchemaMatch,
        ToolArguments,
        ToolCalled,
        ToolNotCalled,
        ToolOrder,
    )
    from aireliability.evaluation.generation.checks import (
        CitationPresence,
        CitationValidation,
        FormatValidation,
        JsonValid,
        RegexMatch,
        RequiredFields,
        TypeValidation,
    )
    from aireliability.evaluation.generation.evaluators import (
        CoherenceEvaluator,
        CompletenessEvaluator,
        CorrectnessEvaluator,
        HelpfulnessEvaluator,
        InstructionFollowingEvaluator,
        RelevanceEvaluator,
    )
    from aireliability.evaluation.performance import (
        LatencyAttributionEvaluator,
        PerformanceEvaluator,
    )
    from aireliability.evaluation.privacy import PrivacyEvaluator
    from aireliability.evaluation.rag import (
        ContextEvaluator,
        RAGEvaluator,
        RerankingEvaluator,
        RetrievalEvaluator,
    )
    from aireliability.evaluation.robustness import RobustnessEvaluator
    from aireliability.evaluation.safety import SafetyEvaluator
    from aireliability.evaluation.security import SecurityEvaluator
    from aireliability.evaluation.semantic.expectations import (
        SemanticExpectation,
        SemanticRelevance,
        SemanticSimilarity,
    )

    builtins: list[tuple[str, Any]] = [
        ("toolcalled", ToolCalled),
        ("toolnotcalled", ToolNotCalled),
        ("toolorder", ToolOrder),
        ("toolarguments", ToolArguments),
        ("outputequals", OutputEquals),
        ("outputcontains", OutputContains),
        ("schemamatch", SchemaMatch),
        ("maxlatency", MaxLatency),
        ("maxcost", MaxCost),
        ("regexmatch", RegexMatch),
        ("jsonvalid", JsonValid),
        ("requiredfields", RequiredFields),
        ("typevalidation", TypeValidation),
        ("formatvalidation", FormatValidation),
        ("citationpresence", CitationPresence),
        ("citationvalidation", CitationValidation),
        ("semanticexpectation", SemanticExpectation),
        ("semanticrelevance", SemanticRelevance),
        ("semanticsimilarity", SemanticSimilarity),
        ("correctnessevaluator", CorrectnessEvaluator),
        ("relevanceevaluator", RelevanceEvaluator),
        ("completenessevaluator", CompletenessEvaluator),
        ("coherenceevaluator", CoherenceEvaluator),
        ("helpfulnessevaluator", HelpfulnessEvaluator),
        ("instructionfollowingevaluator", InstructionFollowingEvaluator),
        ("hallucinationevaluator", HallucinationEvaluator),
        ("groundednessevaluator", GroundednessEvaluator),
        ("faithfulnessevaluator", FaithfulnessEvaluator),
        ("retrievalevaluator", RetrievalEvaluator),
        ("rerankingevaluator", RerankingEvaluator),
        ("contextevaluator", ContextEvaluator),
        ("ragevaluator", RAGEvaluator),
        ("trajectoryevaluator", TrajectoryEvaluator),
        ("toolusageevaluator", ToolUsageEvaluator),
        ("agentevaluator", AgentEvaluator),
        ("safetyevaluator", SafetyEvaluator),
        ("securityevaluator", SecurityEvaluator),
        ("privacyevaluator", PrivacyEvaluator),
        ("robustnessevaluator", RobustnessEvaluator),
        ("consistencyevaluator", ConsistencyEvaluator),
        ("latencyattributionevaluator", LatencyAttributionEvaluator),
        ("performanceevaluator", PerformanceEvaluator),
        ("costevaluator", CostEvaluator),
    ]

    for name, cls in builtins:
        EvaluatorRegistry.register(name, cls)


_initialize_builtins()
