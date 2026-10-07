"""Deterministic, multi-dimensional quality scoring for generated tests."""

from __future__ import annotations

from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    TestPriority,
    TestQualityScore,
    TestRiskLevel,
)


class TestQualityScorer:
    """Calculates explainable, deterministic quality scores across multiple reliability dimensions."""

    def score(self, test: GeneratedTest) -> TestQualityScore:
        """Calculate dimensional scores and composite quality for a generated test."""
        # 1. Provenance strength (0.0 to 1.0)
        prov = test.provenance
        if prov.source_type in (
            GenerationSourceType.FAILURE_REPORT,
            GenerationSourceType.INCIDENT,
            GenerationSourceType.PRODUCTION_TRACE,
            GenerationSourceType.GRAPH_PATH,
        ):
            prov_strength = 1.0
        elif prov.source_type in (
            GenerationSourceType.FAILURE_CLUSTER,
            GenerationSourceType.FAILURE_PATTERN,
            GenerationSourceType.REGRESSION_TEST,
            GenerationSourceType.RECOMMENDATION,
        ):
            prov_strength = 0.90
        elif prov.source_type == GenerationSourceType.EXISTING_TEST:
            prov_strength = 0.80
        else:
            prov_strength = 0.70

        # 2. Failure relevance (0.0 to 1.0)
        if prov.source_failure_id or prov.source_incident_id:
            fail_relevance = 1.0
        elif prov.source_pattern_id or prov.source_cluster_id:
            fail_relevance = 0.85
        else:
            fail_relevance = 0.70

        # 3. Coverage (0.0 to 1.0)
        coverage_factors = 0.5  # Base input coverage
        if test.context or test.retrieved_documents:
            coverage_factors += 0.15
        if test.tool_definitions or test.expected_tool_calls:
            coverage_factors += 0.15
        if len(test.expected_criteria) >= 2:
            coverage_factors += 0.10
        elif len(test.expected_criteria) == 1:
            coverage_factors += 0.05
        if test.expected_trajectory_constraints:
            coverage_factors += 0.10
        coverage_score = min(1.0, coverage_factors)

        # 4. Correctness confidence (0.0 to 1.0)
        if test.has_ground_truth and test.reference_answer is not None:
            correctness_conf = 1.0
        elif bool(test.expected_output):
            correctness_conf = 0.95
        elif bool(test.expected_criteria):
            correctness_conf = 0.85
        else:
            correctness_conf = 0.50

        # 5. Reproducibility score (0.0 to 1.0)
        repro_score = 0.90
        if test.deterministic_seed is not None or prov.deterministic_seed is not None:
            repro_score = 1.0
        if "volatile" in test.tags:
            repro_score -= 0.30

        # 6. Novelty & Diversity score
        novelty_score = 0.85
        if test.tags and len(test.tags) >= 3:
            novelty_score = 0.95

        diversity_score = 0.85

        # 7. Risk & Impact score
        risk_map = {
            TestRiskLevel.LOW: 0.1,
            TestRiskLevel.MEDIUM: 0.4,
            TestRiskLevel.HIGH: 0.7,
            TestRiskLevel.CRITICAL: 1.0,
        }
        risk_score = risk_map.get(test.risk_level, 0.2)

        impact_map = {
            TestPriority.LOW: 0.3,
            TestPriority.MEDIUM: 0.6,
            TestPriority.HIGH: 0.85,
            TestPriority.CRITICAL: 1.0,
        }
        impact_score = impact_map.get(test.priority, 0.5)

        # Source confidence
        source_confidence = test.confidence

        # Composite Score Calculation (Weighted blend)
        weights = {
            "provenance_strength": 0.25,
            "failure_relevance": 0.20,
            "coverage_score": 0.20,
            "correctness_confidence": 0.20,
            "reproducibility_score": 0.15,
        }

        total_score = (
            prov_strength * weights["provenance_strength"]
            + fail_relevance * weights["failure_relevance"]
            + coverage_score * weights["coverage_score"]
            + correctness_conf * weights["correctness_confidence"]
            + repro_score * weights["reproducibility_score"]
        )
        total_score = round(min(1.0, max(0.0, total_score)), 4)

        factors = {
            "provenance_strength": prov_strength,
            "failure_relevance": fail_relevance,
            "coverage_score": coverage_score,
            "novelty_score": novelty_score,
            "diversity_score": diversity_score,
            "correctness_confidence": correctness_conf,
            "reproducibility_score": repro_score,
            "risk_score": risk_score,
            "impact_score": impact_score,
            "source_confidence": source_confidence,
        }

        explanation = (
            f"Quality score {total_score:.2f} based on provenance ({prov_strength:.2f}), "
            f"relevance ({fail_relevance:.2f}), coverage ({coverage_score:.2f}), "
            f"correctness confidence ({correctness_conf:.2f}), reproducibility ({repro_score:.2f})."
        )

        return TestQualityScore(
            total_score=total_score,
            provenance_strength=prov_strength,
            failure_relevance=fail_relevance,
            coverage_score=coverage_score,
            novelty_score=novelty_score,
            diversity_score=diversity_score,
            correctness_confidence=correctness_conf,
            reproducibility_score=repro_score,
            risk_score=risk_score,
            impact_score=impact_score,
            source_confidence=source_confidence,
            explanation=explanation,
            factors=factors,
        )
