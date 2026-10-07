"""Intelligent, evidence-backed remediation recommendation engine."""

from __future__ import annotations

from collections.abc import Sequence

from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.models import (
    CrossRunCorrelation,
    EvidenceReference,
    FailureCluster,
    FailurePattern,
    ImpactAssessment,
    PatternType,
    RecommendationPriority,
    ReliabilityRecommendation,
    ReliabilityTrend,
    TrendDirection,
)


class RecommendationEngine:
    """Generates explainable, deterministic remediation recommendations based on empirical evidence."""

    def generate_recommendations(
        self,
        clusters: Sequence[FailureCluster],
        patterns: Sequence[FailurePattern] | None = None,
        correlations: Sequence[CrossRunCorrelation] | None = None,
        trends: Sequence[ReliabilityTrend] | None = None,
        impacts: Sequence[ImpactAssessment] | None = None,
        evidence_pool: list[EvidenceReference] | None = None,
    ) -> list[ReliabilityRecommendation]:
        """Evaluate intelligence findings and generate prioritized recommendations."""
        recommendations: list[ReliabilityRecommendation] = []
        rec_counter = 1

        patterns_list = list(patterns or [])
        correlations_list = list(correlations or [])
        trends_list = list(trends or [])

        # Rule 1: Critical Safety or Security Violations
        safety_clusters = [
            c for c in clusters if c.dominant_category in ("safety", "security")
        ]
        if safety_clusters:
            all_ids = [fid for c in safety_clusters for fid in c.failure_ids]
            all_comps = list(
                {comp for c in safety_clusters for comp in c.affected_components}
            )
            all_ev = [ev for c in safety_clusters for ev in c.evidence]
            recommendations.append(
                ReliabilityRecommendation(
                    recommendation_id=f"rec_safety_{rec_counter}",
                    title="Enforce Release Gate Block & Add Safety Regression Tests",
                    description=(
                        f"Detected {len(all_ids)} critical safety/security failure(s) across "
                        f"{len(safety_clusters)} cluster(s). Critical security violations must not pass to production."
                    ),
                    priority=RecommendationPriority.CRITICAL,
                    suggested_action=(
                        "1. Trigger release gate BLOCK.\n"
                        "2. Harvest failing traces into the golden regression test suite.\n"
                        "3. Inspect guardrail filtering and system prompt protection layers."
                    ),
                    rationale="Safety and security failures trigger non-compensatory veto policies under governance rules.",
                    confidence=ConfidenceEngine.calculate(
                        evidence_count=len(all_ev) or 2, sample_size=len(all_ids)
                    ),
                    evidence=all_ev[:5],
                    affected_components=all_comps,
                    related_failures=all_ids[:10],
                    related_clusters=[c.cluster_id for c in safety_clusters],
                    remediation_links={
                        "action": "gate_block",
                        "dataset": "golden_regressions",
                    },
                )
            )
            rec_counter += 1

        # Rule 2: Newly Introduced Failure Clusters
        new_patterns = [p for p in patterns_list if p.pattern_type == PatternType.NEW]
        if new_patterns:
            for p in new_patterns:
                recommendations.append(
                    ReliabilityRecommendation(
                        recommendation_id=f"rec_new_{rec_counter}",
                        title=f"Investigate Newly Introduced Regressions in {p.title}",
                        description=f"Cluster {p.fingerprint[:8]} was not present in the baseline run and represents a new regression.",
                        priority=RecommendationPriority.HIGH,
                        suggested_action=(
                            "1. Diff prompt and model configuration against reference baseline.\n"
                            "2. Synthesize a reproducible regression test.\n"
                            "3. Validate fix before merging PR."
                        ),
                        rationale="Failures absent from reference baselines indicate candidate code regressions.",
                        confidence=p.confidence,
                        evidence=p.evidence,
                        affected_components=p.affected_components,
                        related_patterns=[p.pattern_id],
                        remediation_links={"action": "regression_diff"},
                    )
                )
                rec_counter += 1

        # Rule 3: Retrieval Degraded + Hallucination Co-occurrence
        retrieval_clusters = [c for c in clusters if c.dominant_category == "retrieval"]
        hallucination_clusters = [
            c
            for c in clusters
            if c.dominant_category == "output" and "hallucination" in c.name.lower()
        ]
        if retrieval_clusters and hallucination_clusters:
            combined_ev = [
                ev
                for c in (retrieval_clusters + hallucination_clusters)
                for ev in c.evidence
            ]
            recommendations.append(
                ReliabilityRecommendation(
                    recommendation_id=f"rec_rag_{rec_counter}",
                    title="Optimize Retrieval Coverage to Eliminate Downstream Hallucinations",
                    description=(
                        f"Found {len(retrieval_clusters)} retrieval failure clusters coinciding with "
                        f"{len(hallucination_clusters)} hallucination clusters. Root cause analysis points to context starvation."
                    ),
                    priority=RecommendationPriority.HIGH,
                    suggested_action=(
                        "1. Verify retriever index freshness and embedding model compatibility.\n"
                        "2. Increase retrieval top-k or adjust chunk overlap strategy.\n"
                        "3. Add explicit citation enforcement to generator prompt."
                    ),
                    rationale="Hallucinations often stem directly from missing or irrelevant context chunks rather than generator defects.",
                    confidence=ConfidenceEngine.calculate(
                        evidence_count=len(combined_ev) or 3, sample_size=5
                    ),
                    evidence=combined_ev[:5],
                    affected_components=list(
                        {
                            comp
                            for c in retrieval_clusters
                            for comp in c.affected_components
                        }
                    ),
                    related_clusters=[
                        c.cluster_id
                        for c in retrieval_clusters + hallucination_clusters
                    ],
                    remediation_links={"pipeline": "rag_evaluator"},
                )
            )
            rec_counter += 1

        # Rule 4: Tool Calling & Argument Inconsistencies
        tool_clusters = [c for c in clusters if c.dominant_category == "tool"]
        if tool_clusters:
            tool_ev = [ev for c in tool_clusters for ev in c.evidence]
            recommendations.append(
                ReliabilityRecommendation(
                    recommendation_id=f"rec_tool_{rec_counter}",
                    title="Refine Agent System Prompt Tool Schemas and Instructions",
                    description=f"Identified {len(tool_clusters)} tool calling failure cluster(s) with argument or ordering errors.",
                    priority=RecommendationPriority.HIGH,
                    suggested_action=(
                        "1. Audit tool JSON Schema specifications for ambiguity.\n"
                        "2. Provide 1-2 few-shot tool execution examples in the agent prompt.\n"
                        "3. Ensure fallback error handling when external tools return non-200 responses."
                    ),
                    rationale="Tool calling syntax failures are most effectively resolved through strict JSON schemas and few-shot examples.",
                    confidence=ConfidenceEngine.calculate(
                        evidence_count=len(tool_ev) or 2, sample_size=3
                    ),
                    evidence=tool_ev[:5],
                    affected_components=list(
                        {comp for c in tool_clusters for comp in c.affected_components}
                    ),
                    related_clusters=[c.cluster_id for c in tool_clusters],
                    remediation_links={"action": "inspect_tools"},
                )
            )
            rec_counter += 1

        # Rule 5: Negative Reliability Trends (Downward Trajectory in Quality / Pass Rate)
        degrading_trends = [
            t for t in trends_list if t.direction == TrendDirection.DECREASING
        ]
        for t in degrading_trends:
            if t.metric_or_dimension in ("accuracy", "pass_rate", "composite_score"):
                recommendations.append(
                    ReliabilityRecommendation(
                        recommendation_id=f"rec_trend_{rec_counter}",
                        title=f"Halt Release: Downward Trajectory in {t.metric_or_dimension}",
                        description=f"{t.description} Across {t.observations_count} historical evaluation runs.",
                        priority=RecommendationPriority.HIGH,
                        suggested_action=(
                            "1. Run 'airel regression diff' against the last known passing baseline.\n"
                            "2. Inspect recent prompt or dependency commits.\n"
                            "3. Run automated root cause diagnosis."
                        ),
                        rationale="Sustained degradation across consecutive runs indicates systematic quality regression.",
                        confidence=t.confidence,
                        evidence=t.evidence,
                        affected_components=[],
                        remediation_links={"action": "diff_baseline"},
                    )
                )
                rec_counter += 1

        # Rule 6: Escalating Defect Trends (Increasing Hallucination or Latency)
        escalating_trends = [
            t for t in trends_list if t.direction == TrendDirection.INCREASING
        ]
        for t in escalating_trends:
            if "hallucination" in t.metric_or_dimension.lower():
                recommendations.append(
                    ReliabilityRecommendation(
                        recommendation_id=f"rec_trend_hal_{rec_counter}",
                        title="Investigate Retrieval Quality Due to Rising Hallucination Rate",
                        description=f"{t.description} Hallucination metric worsened across {t.observations_count} runs.",
                        priority=RecommendationPriority.HIGH,
                        suggested_action=(
                            "1. Audit context recall and relevance of retrieved documents.\n"
                            "2. Increase top-k retrieval candidates and evaluate reranking.\n"
                            "3. Validate whether knowledge base indexing is outdated."
                        ),
                        rationale="Rising hallucination rates in generative models are predominantly driven by retrieval context starvation.",
                        confidence=t.confidence,
                        evidence=t.evidence,
                        affected_components=["retriever"],
                        remediation_links={"action": "audit_retriever"},
                    )
                )
                rec_counter += 1
            elif "latency" in t.metric_or_dimension.lower():
                recommendations.append(
                    ReliabilityRecommendation(
                        recommendation_id=f"rec_trend_lat_{rec_counter}",
                        title="Investigate Model and Provider Configuration Due to Latency Growth",
                        description=f"{t.description} Observed latency trend escalation.",
                        priority=RecommendationPriority.HIGH,
                        suggested_action="Review LLM inference latency breakdown, streaming response tokens, and tool network overhead.",
                        rationale="Systematic latency escalation degrades user SLAs and increases compute cost.",
                        confidence=t.confidence,
                        evidence=t.evidence,
                        affected_components=["model", "provider"],
                        remediation_links={"action": "inspect_latency"},
                    )
                )
                rec_counter += 1

        # Rule 7: Configuration Change Correlations
        for corr in correlations_list:
            if corr.source_change_type in ("retriever", "retriever_version"):
                recommendations.append(
                    ReliabilityRecommendation(
                        recommendation_id=f"rec_corr_ret_{rec_counter}",
                        title="Investigate Retriever Configuration and Embedding Index",
                        description=(
                            f"Retriever configuration update '{corr.source_change_value}' "
                            f"correlates with {corr.observed_effect}."
                        ),
                        priority=RecommendationPriority.HIGH,
                        suggested_action=(
                            "1. Audit vector embeddings and chunk overlap for the updated retriever.\n"
                            "2. Compare retrieval benchmark against previous index snapshot.\n"
                            "3. Roll back or tune similarity threshold."
                        ),
                        rationale="Empirical correlation connects recent retriever configuration shift with metric degradation.",
                        confidence=corr.confidence,
                        evidence=corr.evidence,
                        affected_components=["retriever"],
                        remediation_links={"action": "audit_retriever"},
                    )
                )
                rec_counter += 1
            elif corr.source_change_type in ("model", "model_version"):
                recommendations.append(
                    ReliabilityRecommendation(
                        recommendation_id=f"rec_corr_mod_{rec_counter}",
                        title="Investigate Model Downgrade & Provider Behavior",
                        description=f"Model change '{corr.source_change_value}' correlates with {corr.observed_effect}.",
                        priority=RecommendationPriority.HIGH,
                        suggested_action="Review model prompt formatting, reasoning capacity, and temperature parameters.",
                        rationale="Model version migration directly coincides with quality drop.",
                        confidence=corr.confidence,
                        evidence=corr.evidence,
                        affected_components=["model"],
                        remediation_links={"action": "evaluate_model"},
                    )
                )
                rec_counter += 1

        # Rule 8: Monotonically Increasing Failure Rates
        increasing_patterns = [
            p for p in patterns_list if p.pattern_type == PatternType.INCREASING
        ]
        for p in increasing_patterns:
            recommendations.append(
                ReliabilityRecommendation(
                    recommendation_id=f"rec_inc_{rec_counter}",
                    title=f"Address Escalating Failure Volume in {p.title}",
                    description=p.description,
                    priority=RecommendationPriority.MEDIUM,
                    suggested_action="Investigate why this specific failure category has multiplied in frequency over sequential runs.",
                    rationale="Escalating failure counts indicate growing system entropy or edge case drift.",
                    confidence=p.confidence,
                    evidence=p.evidence,
                    affected_components=p.affected_components,
                    related_patterns=[p.pattern_id],
                )
            )
            rec_counter += 1

        # Sort recommendations by priority order (CRITICAL > HIGH > MEDIUM > LOW)
        priority_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }
        recommendations.sort(key=lambda r: priority_order.get(r.priority, 99))
        return recommendations
