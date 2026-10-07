"""Reusable evaluation profiles for different AI modalities and operational tiers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aireliability.core.protocols import Evaluator
from aireliability.evaluation.registry import EvaluatorRegistry


class EvaluationProfile(BaseModel):
    """Specification of an evaluation profile bundling evaluators and default thresholds."""

    name: str
    description: str
    evaluators: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    default_thresholds: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def resolve_evaluators(self) -> list[Evaluator]:
        """Instantiate and return all evaluators specified in this profile."""
        instances: list[Evaluator] = []
        for name in self.evaluators:
            try:
                instances.append(EvaluatorRegistry.get(name))
            except KeyError:
                # If exact name not found, try clean alias
                clean = name.lower().replace("evaluator", "").strip()
                instances.append(EvaluatorRegistry.get(clean))
        return instances


class EvaluationProfileRegistry:
    """Registry of built-in and user-defined evaluation profiles."""

    _profiles: dict[str, EvaluationProfile] = {}

    @classmethod
    def register(cls, profile: EvaluationProfile) -> None:
        """Register an evaluation profile."""
        cls._profiles[profile.name.lower()] = profile

    @classmethod
    def get(cls, name: str) -> EvaluationProfile:
        """Retrieve a registered evaluation profile by name."""
        key = name.lower()
        if key not in cls._profiles:
            raise KeyError(
                f"Evaluation profile '{name}' is not registered. Available: {cls.list_profiles()}"
            )
        return cls._profiles[key]

    @classmethod
    def list_profiles(cls) -> list[str]:
        """List all registered evaluation profile names."""
        return sorted(cls._profiles.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check whether a profile name is registered."""
        return name.lower() in cls._profiles


# Initialize standard built-in profiles
def _initialize_default_profiles() -> None:
    defaults: list[EvaluationProfile] = [
        EvaluationProfile(
            name="rag",
            description="End-to-end RAG evaluation: retrieval, context quality, and generation faithfulness",
            evaluators=[
                "retrievalevaluator",
                "contextevaluator",
                "ragevaluator",
                "faithfulnessevaluator",
            ],
            metrics=[
                "precision_at_k",
                "recall_at_k",
                "mrr",
                "ndcg_at_k",
                "context_relevance",
                "faithfulness",
            ],
            default_thresholds={"faithfulness": 0.85, "context_relevance": 0.80},
            tags=["rag", "retrieval", "search"],
        ),
        EvaluationProfile(
            name="agent",
            description="Agent trajectory, tool execution, planning, and task completion evaluation",
            evaluators=[
                "agentevaluator",
                "trajectoryevaluator",
                "toolusageevaluator",
            ],
            metrics=[
                "task_success",
                "tool_selection",
                "tool_arguments",
                "trajectory_correctness",
                "loop_detection",
            ],
            default_thresholds={"task_success": 1.0, "trajectory_correctness": 0.90},
            tags=["agent", "tools", "trajectory"],
        ),
        EvaluationProfile(
            name="classification",
            description="Traditional ML and LLM classification metrics",
            evaluators=[
                "correctnessevaluator",
            ],
            metrics=[
                "accuracy",
                "precision",
                "recall",
                "f1",
                "specificity",
                "balanced_accuracy",
                "mcc",
            ],
            default_thresholds={"accuracy": 0.90, "f1": 0.85},
            tags=["classification", "ml"],
        ),
        EvaluationProfile(
            name="generation",
            description="LLM generation quality: correctness, relevance, completeness, and coherence",
            evaluators=[
                "correctnessevaluator",
                "relevanceevaluator",
                "completenessevaluator",
                "coherenceevaluator",
                "instructionfollowingevaluator",
            ],
            metrics=[
                "correctness",
                "relevance",
                "completeness",
                "coherence",
                "instruction_following",
            ],
            default_thresholds={"correctness": 0.85, "relevance": 0.80},
            tags=["generation", "nlg", "quality"],
        ),
        EvaluationProfile(
            name="safety",
            description="Comprehensive safety, security, and privacy evaluation",
            evaluators=[
                "safetyevaluator",
                "securityevaluator",
                "privacyevaluator",
            ],
            metrics=[
                "safety",
                "toxicity",
                "prompt_injection",
                "jailbreak",
                "pii_leakage",
                "secrets_leakage",
            ],
            default_thresholds={"safety": 1.0, "security": 1.0, "privacy": 1.0},
            tags=["safety", "security", "privacy", "governance"],
        ),
        EvaluationProfile(
            name="performance",
            description="Latency distribution, throughput, and performance attribution",
            evaluators=[
                "performanceevaluator",
                "latencyattributionevaluator",
            ],
            metrics=[
                "latency",
                "p50_latency",
                "p95_latency",
                "p99_latency",
                "throughput",
            ],
            default_thresholds={"p95_latency": 2000.0},
            tags=["performance", "latency", "benchmarking"],
        ),
        EvaluationProfile(
            name="cost",
            description="Token accounting and monetary cost evaluation",
            evaluators=[
                "costevaluator",
            ],
            metrics=[
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "total_cost",
            ],
            default_thresholds={"total_cost": 0.10},
            tags=["cost", "finops", "tokens"],
        ),
        EvaluationProfile(
            name="production",
            description="Production monitoring tier combining safety, latency, cost, and groundedness",
            evaluators=[
                "safetyevaluator",
                "performanceevaluator",
                "costevaluator",
                "groundednessevaluator",
            ],
            metrics=[
                "safety",
                "p95_latency",
                "total_cost",
                "groundedness",
            ],
            default_thresholds={"safety": 1.0, "groundedness": 0.85},
            tags=["production", "monitoring", "tier-1"],
        ),
        EvaluationProfile(
            name="full",
            description="Exhaustive evaluation running all primary evaluation dimensions",
            evaluators=[
                "correctnessevaluator",
                "relevanceevaluator",
                "groundednessevaluator",
                "safetyevaluator",
                "securityevaluator",
                "privacyevaluator",
                "performanceevaluator",
                "costevaluator",
                "agentevaluator",
                "ragevaluator",
            ],
            metrics=[
                "correctness",
                "relevance",
                "groundedness",
                "safety",
                "security",
                "privacy",
                "latency",
                "cost",
                "task_success",
            ],
            default_thresholds={
                "safety": 1.0,
                "security": 1.0,
                "privacy": 1.0,
                "correctness": 0.85,
            },
            tags=["full", "exhaustive", "audit"],
        ),
    ]

    for p in defaults:
        EvaluationProfileRegistry.register(p)


_initialize_default_profiles()
