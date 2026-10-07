"""Extensible strategy registry for AI test generation."""

from __future__ import annotations

from aireliability.generation.models import GenerationStrategy
from aireliability.generation.strategies.adversarial import AdversarialTestGenerator
from aireliability.generation.strategies.agent import AgentTestGenerator
from aireliability.generation.strategies.base import BaseTestGenerator
from aireliability.generation.strategies.consistency import ConsistencyTestGenerator
from aireliability.generation.strategies.edge_cases import EdgeCaseGenerator
from aireliability.generation.strategies.failure import FailureTestGenerator
from aireliability.generation.strategies.graph import GraphTestGenerator
from aireliability.generation.strategies.incident import IncidentTestGenerator
from aireliability.generation.strategies.mutation import MutationGenerator
from aireliability.generation.strategies.pattern import PatternTestGenerator
from aireliability.generation.strategies.rag import RAGTestGenerator
from aireliability.generation.strategies.regression import RegressionTestGenerator
from aireliability.generation.strategies.robustness import RobustnessTestGenerator
from aireliability.generation.strategies.safety import SafetyTestGenerator
from aireliability.generation.strategies.trace import TraceTestGenerator


class GenerationRegistry:
    """Registry managing available test generation strategies and their generator implementations."""

    def __init__(self) -> None:
        self._generators: dict[GenerationStrategy, BaseTestGenerator] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the 14 standard Phase 36 test generators."""
        self.register(GenerationStrategy.FAILURE_DRIVEN, FailureTestGenerator())
        self.register(GenerationStrategy.REGRESSION_DRIVEN, RegressionTestGenerator())
        self.register(GenerationStrategy.GRAPH_DRIVEN, GraphTestGenerator())
        self.register(GenerationStrategy.PATTERN_DRIVEN, PatternTestGenerator())
        self.register(GenerationStrategy.INCIDENT_DRIVEN, IncidentTestGenerator())
        self.register(GenerationStrategy.PRODUCTION_TRACE_DRIVEN, TraceTestGenerator())
        self.register(GenerationStrategy.EDGE_CASE, EdgeCaseGenerator())
        self.register(GenerationStrategy.MUTATION_BASED, MutationGenerator())
        self.register(GenerationStrategy.ADVERSARIAL, AdversarialTestGenerator())
        self.register(GenerationStrategy.SAFETY_SECURITY_PRIVACY, SafetyTestGenerator())
        self.register(GenerationStrategy.RAG_FOCUSED, RAGTestGenerator())
        self.register(GenerationStrategy.AGENT_TRAJECTORY, AgentTestGenerator())
        self.register(GenerationStrategy.ROBUSTNESS, RobustnessTestGenerator())
        self.register(GenerationStrategy.CONSISTENCY, ConsistencyTestGenerator())

    def register(
        self, strategy: GenerationStrategy, generator: BaseTestGenerator
    ) -> None:
        """Register or override a generator for a strategy."""
        self._generators[strategy] = generator

    def get(self, strategy: GenerationStrategy) -> BaseTestGenerator:
        """Retrieve the generator for a given strategy."""
        if strategy not in self._generators:
            raise KeyError(
                f"No test generator registered for strategy '{strategy.value}'"
            )
        return self._generators[strategy]

    def has_strategy(self, strategy: GenerationStrategy) -> bool:
        """Check whether a strategy is registered."""
        return strategy in self._generators

    def list_strategies(self) -> list[GenerationStrategy]:
        """List all registered generation strategies."""
        return list(self._generators.keys())


_GLOBAL_REGISTRY: GenerationRegistry | None = None


def get_default_registry() -> GenerationRegistry:
    """Return the global default GenerationRegistry singleton."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = GenerationRegistry()
    return _GLOBAL_REGISTRY
