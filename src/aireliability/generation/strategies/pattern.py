"""Pattern-driven test generation leveraging Phase 34 Intelligence patterns, clusters, and recommendations."""

from __future__ import annotations

from typing import Any

from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
    TestType,
)
from aireliability.intelligence.models import (
    FailureCluster,
    FailurePattern,
    IntelligenceAnalysis,
    PatternType,
    ReliabilityRecommendation,
)


class PatternTestGenerator:
    """Generates tests for recurring, persistent, or increasing failure patterns identified by intelligence."""

    strategy = GenerationStrategy.PATTERN_DRIVEN

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        tests: list[GeneratedTest] = []

        patterns: list[FailurePattern] = []
        clusters: list[FailureCluster] = []
        recommendations: list[ReliabilityRecommendation] = []

        if isinstance(source, FailurePattern):
            patterns.append(source)
        elif isinstance(source, FailureCluster):
            clusters.append(source)
        elif isinstance(source, ReliabilityRecommendation):
            recommendations.append(source)
        elif isinstance(source, IntelligenceAnalysis):
            patterns.extend(source.patterns)
            clusters.extend(source.clusters)
            recommendations.extend(source.recommendations)
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, FailurePattern):
                    patterns.append(item)
                elif isinstance(item, FailureCluster):
                    clusters.append(item)
                elif isinstance(item, ReliabilityRecommendation):
                    recommendations.append(item)

        for pat in patterns[: config.max_candidates]:
            tests.append(self._from_pattern(pat, config))

        for cluster in clusters[: config.max_candidates]:
            tests.append(self._from_cluster(cluster, config))

        for rec in recommendations[: config.max_candidates]:
            tests.append(self._from_recommendation(rec, config))

        return tests[: config.max_candidates]

    def _from_pattern(
        self,
        pat: FailurePattern,
        config: TestGenerationConfig,
    ) -> GeneratedTest:
        prov = TestProvenance(
            source_type=GenerationSourceType.FAILURE_PATTERN,
            source_id=pat.pattern_id,
            source_pattern_id=pat.pattern_id,
            generator_name="PatternTestGenerator",
            deterministic_seed=config.deterministic_seed,
            rationale=f"Intelligence pattern '{pat.title}' ({pat.pattern_type.value}, frequency={pat.frequency})",
            metadata={
                "fingerprint": pat.fingerprint,
                "affected": pat.affected_components,
            },
        )

        priority = (
            TestPriority.CRITICAL
            if pat.pattern_type in (PatternType.INCREASING, PatternType.PERSISTENT)
            else TestPriority.HIGH
        )

        return GeneratedTest(
            name=f"guard_pattern_{pat.pattern_id[:8]}",
            test_type=TestType.REGRESSION,
            strategy=self.strategy,
            input=f"Verification prompt exercising behavior for pattern '{pat.title}'",
            expected_output=None,
            expected_criteria=[
                f"must prevent occurrence of pattern {pat.pattern_type.value}",
                f"must stabilize components: {', '.join(pat.affected_components) or 'all'}",
            ],
            reference_answer=None,
            has_ground_truth=False,
            provenance=prov,
            confidence=pat.confidence.score,
            risk_level=TestRiskLevel.HIGH
            if priority == TestPriority.CRITICAL
            else TestRiskLevel.MEDIUM,
            priority=priority,
            tags=["pattern_driven", f"pattern_type:{pat.pattern_type.value}"]
            + [f"component:{c}" for c in pat.affected_components],
            metadata=dict(pat.metadata),
            deterministic_seed=config.deterministic_seed,
        )

    def _from_cluster(
        self,
        cluster: FailureCluster,
        config: TestGenerationConfig,
    ) -> GeneratedTest:
        prov = TestProvenance(
            source_type=GenerationSourceType.FAILURE_CLUSTER,
            source_id=cluster.cluster_id,
            source_cluster_id=cluster.cluster_id,
            source_failure_id=cluster.representative_failure_id,
            generator_name="PatternTestGenerator",
            deterministic_seed=config.deterministic_seed,
            rationale=f"Cluster '{cluster.name}' (freq={cluster.frequency}, dominant_category={cluster.dominant_category})",
        )

        return GeneratedTest(
            name=f"guard_cluster_{cluster.cluster_id[:8]}",
            test_type=TestType.REGRESSION,
            strategy=self.strategy,
            input=f"Cluster verification prompt for '{cluster.name}'",
            expected_output=None,
            expected_criteria=[
                f"must eliminate root cause: {cluster.dominant_root_cause}",
                f"must prevent cluster '{cluster.name}' failures",
            ],
            reference_answer=None,
            has_ground_truth=False,
            provenance=prov,
            confidence=cluster.confidence.score,
            risk_level=TestRiskLevel.MEDIUM,
            priority=TestPriority.HIGH,
            tags=["cluster_driven", f"category:{cluster.dominant_category}"],
            metadata=dict(cluster.metadata),
            deterministic_seed=config.deterministic_seed,
        )

    def _from_recommendation(
        self,
        rec: ReliabilityRecommendation,
        config: TestGenerationConfig,
    ) -> GeneratedTest:
        prov = TestProvenance(
            source_type=GenerationSourceType.RECOMMENDATION,
            source_id=rec.recommendation_id,
            source_recommendation_id=rec.recommendation_id,
            generator_name="PatternTestGenerator",
            deterministic_seed=config.deterministic_seed,
            rationale=f"Derived from remediation recommendation: {rec.title}",
        )

        return GeneratedTest(
            name=f"verify_rec_{rec.recommendation_id[:8]}",
            test_type=TestType.INTEGRATION,
            strategy=self.strategy,
            input=f"Remediation test verifying action: {rec.suggested_action}",
            expected_output=None,
            expected_criteria=[
                f"must satisfy recommendation requirement: {rec.title}",
                f"rationale verification: {rec.rationale}",
            ],
            reference_answer=None,
            has_ground_truth=False,
            provenance=prov,
            confidence=rec.confidence.score,
            risk_level=TestRiskLevel.MEDIUM,
            priority=TestPriority.HIGH,
            tags=["recommendation_driven"]
            + [f"component:{c}" for c in rec.affected_components],
            metadata=dict(rec.metadata),
            deterministic_seed=config.deterministic_seed,
        )
