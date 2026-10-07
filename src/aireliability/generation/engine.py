"""Unified orchestrator for Automated AI Test Generation (Phase 36)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from aireliability.core.models import FailureReport, RegressionTest
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.evaluation.governance.baselines import EvaluationComparisonResult
from aireliability.evaluation.models import EvaluationReport
from aireliability.generation.deduplication import TestDeduplicator
from aireliability.generation.integrations import (
    GraphIntegrationBridge,
    ObservabilityIntegrationBridge,
)
from aireliability.generation.models import (
    GeneratedTest,
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
    TestGenerationResult,
    TestGenerationStatus,
)
from aireliability.generation.promotion import TestPromotionManager
from aireliability.generation.registry import GenerationRegistry, get_default_registry
from aireliability.generation.scoring import TestQualityScorer
from aireliability.generation.selection import TestSelector
from aireliability.generation.validators import TestValidator
from aireliability.graph.graph import KnowledgeGraph
from aireliability.intelligence.models import (
    FailureCluster,
    FailurePattern,
    IntelligenceAnalysis,
    ReliabilityRecommendation,
)
from aireliability.observability.incidents import IncidentRecord
from aireliability.observability.manager import ObservabilityManager
from aireliability.telemetry.sanitizer import SanitizationPolicy

logger = logging.getLogger(__name__)


class TestGenerationEngine:
    """Production-grade Automated AI Test Generation Engine.

    Executes the deterministic test generation pipeline:
    Source Normalization -> Strategy Selection -> Candidate Generation ->
    Validation -> Deduplication -> Quality Scoring -> Selection ->
    Promotion -> Graph & Observability Synchronization.
    """

    def __init__(
        self,
        registry: GenerationRegistry | None = None,
        validator: TestValidator | None = None,
        deduplicator: TestDeduplicator | None = None,
        scorer: TestQualityScorer | None = None,
        selector: TestSelector | None = None,
        promoter: TestPromotionManager | None = None,
        graph_bridge: GraphIntegrationBridge | None = None,
        obs_bridge: ObservabilityIntegrationBridge | None = None,
        sanitizer: SanitizationPolicy | None = None,
    ) -> None:
        self.registry = registry or get_default_registry()
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.validator = validator or TestValidator(sanitizer=self.sanitizer)
        self.deduplicator = deduplicator or TestDeduplicator()
        self.scorer = scorer or TestQualityScorer()
        self.selector = selector or TestSelector()
        self.promoter = promoter or TestPromotionManager()
        self.graph_bridge = graph_bridge or GraphIntegrationBridge()
        self.obs_bridge = obs_bridge or ObservabilityIntegrationBridge()

    def generate(
        self,
        request: TestGenerationRequest | Any,
        **kwargs: Any,
    ) -> TestGenerationResult:
        """Execute the end-to-end AI test generation pipeline."""
        start_time = time.perf_counter()

        # Step 0: Request normalization
        if not isinstance(request, TestGenerationRequest):
            sources = (
                request
                if isinstance(request, list)
                else [request]
                if request is not None
                else []
            )
            config = kwargs.get(
                "config",
                TestGenerationConfig(
                    **{
                        k: v
                        for k, v in kwargs.items()
                        if hasattr(TestGenerationConfig, k)
                    }
                ),
            )
            strategies = kwargs.get("strategies", [])
            target_ds = kwargs.get("target_dataset_id")
            request = TestGenerationRequest(
                sources=sources,
                strategies=strategies,
                config=config,
                target_dataset_id=target_ds,
                metadata=kwargs.get("metadata", {}),
            )

        config = request.config
        errors: list[dict[str, Any]] = []

        # Step 1: Detect or filter strategies
        resolved_strategies = self._resolve_strategies(request)

        # Step 2: Candidate Generation
        raw_candidates: list[GeneratedTest] = []
        for strat in resolved_strategies:
            if not self.registry.has_strategy(strat):
                errors.append(
                    {
                        "strategy": strat.value,
                        "error": f"Strategy {strat.value} not registered.",
                    }
                )
                continue

            generator = self.registry.get(strat)
            sources_to_run = request.sources if request.sources else [None]
            for src in sources_to_run:
                try:
                    candidates = generator.generate(src, config)
                    raw_candidates.extend(candidates)
                except Exception as exc:
                    logger.warning(
                        "Generation failed for strategy %s on source: %s",
                        strat.value,
                        exc,
                    )
                    errors.append(
                        {
                            "strategy": strat.value,
                            "source": str(type(src)),
                            "error": str(exc),
                        }
                    )

        # Step 3: Validation
        validated: list[GeneratedTest] = []
        rejected: list[GeneratedTest] = []
        needs_review: list[GeneratedTest] = []

        for candidate in raw_candidates:
            validated_candidate = self.validator.validate(candidate)
            if validated_candidate.status == TestGenerationStatus.VALIDATED:
                validated.append(validated_candidate)
            elif validated_candidate.status == TestGenerationStatus.REJECTED:
                rejected.append(validated_candidate)
            else:
                needs_review.append(validated_candidate)

        # Step 4: Deduplication
        dedup_mode = config.deduplication_mode
        self.deduplicator.mode = dedup_mode
        self.deduplicator.near_duplicate_threshold = config.near_duplicate_threshold
        unique_validated, dropped_dups = self.deduplicator.deduplicate(validated)

        # Step 5: Quality Scoring
        scored_tests: list[GeneratedTest] = []
        for t in unique_validated:
            score = self.scorer.score(t)
            scored_tests.append(t.model_copy(update={"quality_score": score}))

        # Step 6: Selection & Budgeting
        selected_tests = self.selector.select(scored_tests, config)

        # Step 7: Promotion (if configured)
        promoted_tests: list[GeneratedTest] = []
        if config.auto_promote:
            target_dataset = kwargs.get("dataset")
            if isinstance(target_dataset, EvaluationDataset):
                p_tests, _ = self.promoter.batch_promote_to_dataset(
                    selected_tests, target_dataset
                )
                promoted_tests = p_tests

        # Step 8: KnowledgeGraph Synchronization (if graph present)
        graph_target = kwargs.get("graph") or next(
            (s for s in request.sources if isinstance(s, KnowledgeGraph)), None
        )
        if isinstance(graph_target, KnowledgeGraph):
            for t in selected_tests:
                self.graph_bridge.record_generated_test(
                    graph_target, t, dataset_id=request.target_dataset_id
                )

        # Step 9: Observability Telemetry Recording (if obs present)
        obs_target = kwargs.get("observability")
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Step 10: Distributions
        strat_dist: dict[str, int] = defaultdict(int)
        src_dist: dict[str, int] = defaultdict(int)
        risk_dist: dict[str, int] = defaultdict(int)
        quality_dist: dict[str, float] = {}

        for t in selected_tests:
            strat_dist[t.strategy.value] += 1
            src_dist[t.provenance.source_type.value] += 1
            risk_dist[t.risk_level.value] += 1
            if t.quality_score:
                quality_dist[t.test_id] = t.quality_score.total_score

        result = TestGenerationResult(
            candidates=raw_candidates,
            validated_tests=selected_tests,
            rejected_tests=rejected,
            needs_review_tests=needs_review,
            promoted_tests=promoted_tests,
            duplicate_count=dropped_dups,
            total_generated=len(raw_candidates),
            total_validated=len(selected_tests),
            total_rejected=len(rejected),
            total_promoted=len(promoted_tests),
            strategy_distribution=dict(strat_dist),
            source_distribution=dict(src_dist),
            quality_distribution=quality_dist,
            risk_distribution=dict(risk_dist),
            errors=errors,
            duration_ms=duration_ms,
            metadata=dict(request.metadata),
        )

        if isinstance(obs_target, ObservabilityManager):
            self.obs_bridge.record_run(obs_target, result)

        return result

    def _resolve_strategies(
        self, request: TestGenerationRequest
    ) -> list[GenerationStrategy]:
        """Infer or filter the strategies to run based on request sources and constraints."""
        if request.strategies:
            allowed = request.config.allowed_strategies
            if allowed:
                return [s for s in request.strategies if s in allowed]
            return request.strategies

        # Auto-infer from source types
        inferred: set[GenerationStrategy] = set()
        for src in request.sources:
            if isinstance(src, (FailureReport, EvaluationReport)):
                inferred.add(GenerationStrategy.FAILURE_DRIVEN)
            elif isinstance(src, (RegressionTest, EvaluationComparisonResult)):
                inferred.add(GenerationStrategy.REGRESSION_DRIVEN)
            elif isinstance(src, KnowledgeGraph):
                inferred.add(GenerationStrategy.GRAPH_DRIVEN)
            elif isinstance(
                src,
                (
                    FailurePattern,
                    FailureCluster,
                    ReliabilityRecommendation,
                    IntelligenceAnalysis,
                ),
            ):
                inferred.add(GenerationStrategy.PATTERN_DRIVEN)
            elif isinstance(src, IncidentRecord):
                inferred.add(GenerationStrategy.INCIDENT_DRIVEN)
            elif hasattr(src, "trace_id") or hasattr(src, "steps"):
                inferred.add(GenerationStrategy.PRODUCTION_TRACE_DRIVEN)

        if not inferred:
            # Default to core synthetic & edge strategies if source is generic
            inferred.update(
                [
                    GenerationStrategy.EDGE_CASE,
                    GenerationStrategy.MUTATION_BASED,
                    GenerationStrategy.ADVERSARIAL,
                    GenerationStrategy.SAFETY_SECURITY_PRIVACY,
                    GenerationStrategy.ROBUSTNESS,
                    GenerationStrategy.CONSISTENCY,
                ]
            )

        allowed = request.config.allowed_strategies
        if allowed:
            return [s for s in inferred if s in allowed]
        return list(inferred)
