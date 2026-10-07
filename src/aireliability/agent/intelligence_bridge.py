"""Phase 34 Intelligence Bridge for Phase 40 Advanced Agent Reliability.

Connects agent trajectory failures into Phase 34 IntelligenceEngine:
- FailureNormalizer: maps AgentFailure into NormalizedFailure with canonical fingerprints.
- FailureClusterer: groups structural and behavioral agent failure clusters.
- PatternDetector: identifies recurring, tool-specific, and trajectory loop patterns.
- ImpactAnalyzer: calculates operational impact and severity.
- RecommendationEngine: synthesizes intelligence recommendations.
"""

from __future__ import annotations

import logging
from typing import Any

from aireliability.agent.models import AgentFailure, AgentRun
from aireliability.intelligence.clustering import FailureClusterer
from aireliability.intelligence.impact import ImpactAnalyzer
from aireliability.intelligence.models import (
    FailureCluster,
    NormalizedFailure,
)
from aireliability.intelligence.patterns import PatternDetector
from aireliability.intelligence.recommendations import RecommendationEngine

logger = logging.getLogger(__name__)


class AgentIntelligenceBridge:
    """Bridges Agent reliability failures to Phase 34 Intelligence subsystems."""

    def __init__(
        self,
        clusterer: FailureClusterer | None = None,
        pattern_detector: PatternDetector | None = None,
        impact_analyzer: ImpactAnalyzer | None = None,
        recommendation_engine: RecommendationEngine | None = None,
    ) -> None:
        self.clusterer = clusterer or FailureClusterer()
        self.pattern_detector = pattern_detector or PatternDetector()
        self.impact_analyzer = impact_analyzer or ImpactAnalyzer()
        self.recommendation_engine = recommendation_engine or RecommendationEngine()

    def normalize_agent_failure(
        self,
        failure: AgentFailure,
        run_id: str = "agent_run",
        agent_id: str = "agent",
    ) -> NormalizedFailure:
        """Convert an AgentFailure into a Phase 34 NormalizedFailure."""
        # Derive canonical fingerprint: category + stage + affected component
        fp = f"{failure.category.value}:{failure.stage.value}:{failure.affected_component}"
        return NormalizedFailure(
            fingerprint=fp,
            failure_id=failure.failure_id,
            category=f"agent_{failure.stage.value}",
            failure_type=failure.category.value,
            root_cause_category=failure.stage.value,
            root_cause_type=failure.category.value,
            evaluator="AdvancedAgentReliabilityEngine",
            component=failure.affected_component or agent_id,
            trace_id=run_id,
            severity=failure.severity.value,
            confidence=failure.confidence,
            sanitized_message=failure.message,
            metadata=dict(failure.metadata),
        )

    def cluster_agent_failures(
        self,
        failures: list[AgentFailure],
        run_id: str = "agent_run",
        agent_id: str = "agent",
    ) -> list[FailureCluster]:
        """Normalize and cluster agent failures using Phase 34 FailureClusterer."""
        if not failures:
            return []
        normalized = [
            self.normalize_agent_failure(f, run_id=run_id, agent_id=agent_id)
            for f in failures
        ]
        return self.clusterer.cluster(normalized)

    def analyze_run_intelligence(
        self,
        run: AgentRun,
    ) -> dict[str, Any]:
        """Perform end-to-end intelligence analysis across an AgentRun's diagnosed failures."""
        if not run.failures:
            return {
                "clusters": [],
                "patterns": [],
                "recommendations": [],
                "summary": "No failures diagnosed in agent run",
            }

        clusters = self.cluster_agent_failures(
            run.failures,
            run_id=run.run_id,
            agent_id=run.agent_id,
        )

        patterns = self.pattern_detector.detect_patterns(clusters)
        recommendations = self.recommendation_engine.generate_recommendations(clusters)

        return {
            "clusters": clusters,
            "patterns": patterns,
            "recommendations": recommendations,
            "summary": f"Identified {len(clusters)} clusters, {len(patterns)} patterns, and {len(recommendations)} recommendations",
        }
