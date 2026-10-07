"""Pluggable registry for AI reliability intelligence analyzers and components."""

from __future__ import annotations

from typing import Any

from aireliability.intelligence.clustering import FailureClusterer
from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.correlation import CorrelationAnalyzer
from aireliability.intelligence.explain import IntelligenceExplainer
from aireliability.intelligence.impact import ImpactAnalyzer
from aireliability.intelligence.patterns import PatternDetector
from aireliability.intelligence.recommendations import RecommendationEngine
from aireliability.intelligence.similarity import FailureNormalizer
from aireliability.intelligence.trends import TrendAnalyzer


class IntelligenceRegistry:
    """Registry maintaining decoupled, pluggable intelligence analyzers and components."""

    def __init__(self) -> None:
        self._analyzers: dict[str, Any] = {}

    def register(self, name: str, analyzer: Any) -> None:
        """Register an intelligence analyzer or component under a unique identifier."""
        if not name or not isinstance(name, str):
            raise ValueError("Analyzer name must be a non-empty string.")
        self._analyzers[name] = analyzer

    def get(self, name: str) -> Any:
        """Retrieve a registered analyzer by name. Raises KeyError if not found."""
        if name not in self._analyzers:
            raise KeyError(
                f"Intelligence analyzer '{name}' is not registered. "
                f"Available analyzers: {self.list()}"
            )
        return self._analyzers[name]

    def has(self, name: str) -> bool:
        """Check if an analyzer is registered under the given name."""
        return name in self._analyzers

    def list(self) -> list[str]:
        """List all registered analyzer names."""
        return sorted(self._analyzers.keys())

    def unregister(self, name: str) -> None:
        """Remove a registered analyzer."""
        self._analyzers.pop(name, None)

    def clear(self) -> None:
        """Clear all registered analyzers."""
        self._analyzers.clear()


_DEFAULT_REGISTRY: IntelligenceRegistry | None = None


def get_default_registry() -> IntelligenceRegistry:
    """Return the global default intelligence registry initialized with standard analyzers."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        reg = IntelligenceRegistry()
        reg.register("normalizer", FailureNormalizer())
        reg.register("clustering", FailureClusterer())
        reg.register("patterns", PatternDetector())
        reg.register("correlation", CorrelationAnalyzer())
        reg.register("trends", TrendAnalyzer())
        reg.register("impact", ImpactAnalyzer())
        reg.register("recommendations", RecommendationEngine())
        reg.register("confidence", ConfidenceEngine())
        reg.register("explainer", IntelligenceExplainer())
        _DEFAULT_REGISTRY = reg
    return _DEFAULT_REGISTRY
