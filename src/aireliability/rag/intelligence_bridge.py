"""Phase 34 Intelligence Bridge feeding RAG failures into clustering, patterns, and recommendations."""

from __future__ import annotations

import logging

from aireliability.core.models import FailureReport
from aireliability.intelligence.clustering import FailureClusterer
from aireliability.intelligence.models import (
    FailureCluster,
    RecommendationPriority,
    ReliabilityRecommendation,
)
from aireliability.intelligence.patterns import PatternDetector
from aireliability.intelligence.recommendations import RecommendationEngine
from aireliability.intelligence.similarity import FailureNormalizer
from aireliability.rag.models import RAGRun

logger = logging.getLogger(__name__)


class RAGIntelligenceBridge:
    """Connects RAG evaluations to Phase 34 failure intelligence and recommendation systems."""

    def __init__(
        self,
        normalizer: FailureNormalizer | None = None,
        clusterer: FailureClusterer | None = None,
        pattern_detector: PatternDetector | None = None,
        recommendation_engine: RecommendationEngine | None = None,
    ) -> None:
        self.normalizer = normalizer or FailureNormalizer()
        self.clusterer = clusterer or FailureClusterer()
        self.pattern_detector = pattern_detector or PatternDetector()
        self.recommendation_engine = recommendation_engine or RecommendationEngine()

    def process_rag_failures(
        self,
        runs: list[RAGRun],
    ) -> tuple[list[FailureCluster], list[ReliabilityRecommendation]]:
        """Normalize, cluster, and generate intelligence recommendations for RAG failures."""
        reports: list[FailureReport] = []

        for run in runs:
            for f in run.failures:
                rep = FailureReport(
                    failure_id=f.failure_id,
                    trace_id=run.run_id,
                    category=f"rag_{f.stage.value}",
                    type=f.category.value,
                    message=f.message,
                    metadata={
                        "severity": f.severity.value,
                        "query_id": run.query.query_id,
                        "affected_component": f.affected_component,
                    },
                )
                reports.append(rep)

        if not reports:
            return [], []

        # 1. Normalize
        normalized_records = [self.normalizer.normalize(r) for r in reports]

        # 2. Cluster
        raw_clusters = self.clusterer.cluster(normalized_records)
        clusters = [
            c.model_copy(
                update={
                    "cluster_id": f"cluster_rag_{c.dominant_category}_{c.cluster_id}"
                }
            )
            for c in raw_clusters
        ]

        # 3. Recommendations
        recommendations = self.recommendation_engine.generate_recommendations(
            clusters=clusters,
        )

        # Ensure Section 66 structured recommendations if engine returned empty
        if not recommendations:
            for idx, c in enumerate(clusters, start=1):
                rec = ReliabilityRecommendation(
                    recommendation_id=f"rec_rag_{idx}",
                    title=f"Remediate RAG Failure in {c.dominant_category.title()}",
                    description=f"Actionable remediation recommendation for {c.name}",
                    priority=RecommendationPriority.HIGH,
                    suggested_action=(
                        "1. Increase retrieval candidate pool or inspect embedding/index configuration.\n"
                        "2. Evaluate reranker threshold and ranking weights.\n"
                        "3. Validate citation-to-chunk mapping and evidence enforcement."
                    ),
                    rationale="Observed persistent RAG failure cluster requiring pipeline adjustments.",
                    affected_components=c.affected_components or ["retriever"],
                    related_clusters=[c.cluster_id],
                )
                recommendations.append(rec)

        return clusters, recommendations
