"""Top-level Reliability Intelligence Engine orchestrating normalization, clustering, patterns, trends, impact, confidence, and recommendations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aireliability.core.models import ExecutionTrace, FailureReport
from aireliability.diagnosis.models import RootCause, RootCauseReport
from aireliability.evaluation.governance.baselines import (
    EvaluationBaseline,
    EvaluationHistoryManager,
)
from aireliability.evaluation.models import EvaluationReport
from aireliability.intelligence.aggregation import (
    IntelligenceTelemetry,
    aggregate_summary,
)
from aireliability.intelligence.clustering import FailureClusterer
from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.correlation import CorrelationAnalyzer
from aireliability.intelligence.evidence import (
    from_baseline,
    from_evaluation_report,
    from_execution_trace,
    from_failure_report,
    from_root_cause,
)
from aireliability.intelligence.explain import IntelligenceExplainer
from aireliability.intelligence.impact import ImpactAnalyzer
from aireliability.intelligence.models import (
    CrossRunCorrelation,
    EvidenceReference,
    FailureCluster,
    FailurePattern,
    ImpactAssessment,
    IntelligenceAnalysis,
    NormalizedFailure,
    ReliabilityRecommendation,
    ReliabilityTrend,
)
from aireliability.intelligence.patterns import PatternDetector
from aireliability.intelligence.recommendations import RecommendationEngine
from aireliability.intelligence.registry import (
    IntelligenceRegistry,
    get_default_registry,
)
from aireliability.intelligence.similarity import FailureNormalizer
from aireliability.intelligence.trends import TrendAnalyzer
from aireliability.observability.incidents import IncidentManager
from aireliability.observability.manager import ObservabilityManager


class ReliabilityIntelligenceEngine:
    """Orchestrator for transforming raw reliability evaluation outcomes into actionable intelligence."""

    def __init__(
        self,
        registry: IntelligenceRegistry | None = None,
        normalizer: FailureNormalizer | None = None,
        clusterer: FailureClusterer | None = None,
        pattern_detector: PatternDetector | None = None,
        correlation_analyzer: CorrelationAnalyzer | None = None,
        trend_analyzer: TrendAnalyzer | None = None,
        impact_analyzer: ImpactAnalyzer | None = None,
        recommendation_engine: RecommendationEngine | None = None,
        confidence_engine: type[ConfidenceEngine] | None = None,
        explainer: IntelligenceExplainer | None = None,
        observability: ObservabilityManager | None = None,
        incident_manager: IncidentManager | None = None,
    ) -> None:
        self.registry = registry or get_default_registry()

        self.normalizer: FailureNormalizer = normalizer or (
            self.registry.get("normalizer")
            if self.registry.has("normalizer")
            else FailureNormalizer()
        )
        self.clusterer: FailureClusterer = clusterer or (
            self.registry.get("clustering")
            if self.registry.has("clustering")
            else FailureClusterer()
        )
        self.pattern_detector: PatternDetector = pattern_detector or (
            self.registry.get("patterns")
            if self.registry.has("patterns")
            else PatternDetector()
        )
        self.correlation_analyzer: CorrelationAnalyzer = correlation_analyzer or (
            self.registry.get("correlation")
            if self.registry.has("correlation")
            else CorrelationAnalyzer()
        )
        self.trend_analyzer: TrendAnalyzer = trend_analyzer or (
            self.registry.get("trends")
            if self.registry.has("trends")
            else TrendAnalyzer()
        )
        self.impact_analyzer: ImpactAnalyzer = impact_analyzer or (
            self.registry.get("impact")
            if self.registry.has("impact")
            else ImpactAnalyzer()
        )
        self.recommendation_engine: RecommendationEngine = recommendation_engine or (
            self.registry.get("recommendations")
            if self.registry.has("recommendations")
            else RecommendationEngine()
        )
        self.confidence_engine = confidence_engine or ConfidenceEngine
        self.explainer: IntelligenceExplainer = explainer or (
            self.registry.get("explainer")
            if self.registry.has("explainer")
            else IntelligenceExplainer()
        )

        self.telemetry = IntelligenceTelemetry(
            observability=observability,
            incident_manager=incident_manager,
        )

    def analyze(
        self,
        report: EvaluationReport | None = None,
        reports: Sequence[EvaluationReport] | None = None,
        failures: Sequence[FailureReport] | None = None,
        history: Sequence[EvaluationReport] | EvaluationHistoryManager | None = None,
        baseline_report: EvaluationReport | None = None,
        baseline: EvaluationBaseline | None = None,
        traces: Sequence[ExecutionTrace] | None = None,
        root_causes: Sequence[RootCause] | None = None,
        target_name: str | None = None,
    ) -> IntelligenceAnalysis:
        """Run the comprehensive end-to-end intelligence analysis pipeline."""
        target = target_name or (
            report.target_name
            if report
            else (
                "historical_analysis"
                if history
                else ("production_analysis" if traces else "reliability_system")
            )
        )

        with self.telemetry.track_analysis(target):
            # 1. Gather all failures
            all_failures: list[FailureReport] = []
            if failures:
                all_failures.extend(failures)
            if report and report.failures:
                all_failures.extend(report.failures)
            if reports:
                for rep in reports:
                    all_failures.extend(rep.failures)

            # 2. Gather root causes
            rc_pool: list[RootCause] = list(root_causes or [])
            if report and report.root_causes:
                for rc_item in report.root_causes:
                    if isinstance(rc_item, RootCauseReport):
                        if (
                            hasattr(rc_item, "primary_root_cause")
                            and rc_item.primary_root_cause
                        ):
                            rc_pool.append(rc_item.primary_root_cause)
                        if (
                            hasattr(rc_item, "secondary_root_causes")
                            and rc_item.secondary_root_causes
                        ):
                            rc_pool.extend(rc_item.secondary_root_causes)
                    elif isinstance(rc_item, RootCause):
                        rc_pool.append(rc_item)

            # Map root causes by failure_id or trace_id for matching
            rc_by_trace: dict[str, RootCause] = {}
            for rc in rc_pool:
                if hasattr(rc, "trace_id") and rc.trace_id:
                    rc_by_trace[rc.trace_id] = rc

            # 3. Gather traces
            trace_pool: list[ExecutionTrace] = list(traces or [])
            trace_by_id: dict[str, ExecutionTrace] = {t.trace_id: t for t in trace_pool}

            # 4. Build Evidence Pool
            evidence_pool: list[EvidenceReference] = []
            if report:
                evidence_pool.append(from_evaluation_report(report))
            for f in all_failures:
                evidence_pool.append(from_failure_report(f))
            for rc in rc_pool:
                evidence_pool.append(from_root_cause(rc))
            for tr in trace_pool:
                evidence_pool.append(from_execution_trace(tr))
            if baseline:
                evidence_pool.append(from_baseline(baseline))

            # 5. Normalize Failures
            normalized_failures: list[NormalizedFailure] = []
            for f in all_failures:
                matched_rc = rc_by_trace.get(f.trace_id)
                matched_tr = trace_by_id.get(f.trace_id)
                norm = self.normalizer.normalize(
                    failure=f,
                    root_cause=matched_rc,
                    trace=matched_tr,
                )
                normalized_failures.append(norm)

            self.telemetry.record_failures_analyzed(len(normalized_failures))

            # 6. Cluster Failures
            clusters: list[FailureCluster] = self.clusterer.cluster(
                normalized_failures, evidence_pool=evidence_pool
            )
            self.telemetry.record_clusters_generated(len(clusters))

            # 7. Pattern Detection
            patterns: list[FailurePattern] = self.pattern_detector.detect_patterns(
                clusters=clusters,
                baseline=baseline,
                evidence_pool=evidence_pool,
            )
            self.telemetry.record_patterns_detected(len(patterns))

            # 8. Cross-Run Correlation
            correlations: list[CrossRunCorrelation] = []
            if report and baseline_report:
                correlations = self.correlation_analyzer.analyze_correlations(
                    current_report=report,
                    baseline_report=baseline_report,
                    clusters=clusters,
                    evidence_pool=evidence_pool,
                )
                self.telemetry.record_correlations_detected(len(correlations))

            # 9. Longitudinal Trends
            trends: list[ReliabilityTrend] = []
            if isinstance(history, EvaluationHistoryManager):
                history_entries = history.get_history(limit=50)
                if history_entries:
                    # Score series
                    score_vals = [
                        entry["composite_score"]
                        for entry in history_entries
                        if "composite_score" in entry
                    ]
                    if score_vals:
                        trends.append(
                            self.trend_analyzer.analyze_series(
                                "composite_score",
                                score_vals,
                                evidence_pool=evidence_pool,
                            )
                        )

                    # Pass rate series
                    pass_rate_vals = [
                        entry["passed_test_cases"] / max(1, entry["total_test_cases"])
                        for entry in history_entries
                        if "passed_test_cases" in entry and "total_test_cases" in entry
                    ]
                    if pass_rate_vals:
                        trends.append(
                            self.trend_analyzer.analyze_series(
                                "pass_rate", pass_rate_vals, evidence_pool=evidence_pool
                            )
                        )

                    # Individual metrics
                    metric_keys = {
                        k
                        for entry in history_entries
                        if "metrics" in entry and isinstance(entry["metrics"], dict)
                        for k in entry["metrics"]
                    }
                    for m_name in sorted(metric_keys):
                        vals = [
                            entry["metrics"][m_name]
                            for entry in history_entries
                            if "metrics" in entry and m_name in entry["metrics"]
                        ]
                        if vals:
                            trends.append(
                                self.trend_analyzer.analyze_series(
                                    m_name, vals, evidence_pool=evidence_pool
                                )
                            )
            elif isinstance(history, (list, tuple)) and history:
                trends = self.trend_analyzer.analyze_reports(history)
            elif reports and len(reports) >= 2:
                trends = self.trend_analyzer.analyze_reports(reports)

            # 10. Impact Assessment
            total_evals = (
                report.total_test_cases
                if report
                else (
                    sum(r.total_test_cases for r in reports)
                    if reports
                    else max(1, len(all_failures))
                )
            )
            impacts: list[ImpactAssessment] = self.impact_analyzer.assess_all(
                clusters, total_evaluations=total_evals
            )

            # 11. Recommendations
            recommendations: list[ReliabilityRecommendation] = (
                self.recommendation_engine.generate_recommendations(
                    clusters=clusters,
                    patterns=patterns,
                    correlations=correlations,
                    trends=trends,
                    impacts=impacts,
                    evidence_pool=evidence_pool,
                )
            )
            self.telemetry.record_recommendations_generated(len(recommendations))

            # 12. Maybe create incident for critical issues
            for imp in impacts:
                if (
                    imp.safety_critical
                    or imp.security_critical
                    or imp.impact_score >= 0.90
                ):
                    matching_rec = next(
                        (r for r in recommendations if r.priority.value == "CRITICAL"),
                        None,
                    )
                    self.telemetry.maybe_create_incident(imp, matching_rec)

            # 13. Overall Confidence
            analysis_conf = self.confidence_engine.calculate(
                evidence_count=len(evidence_pool),
                sample_size=max(1, total_evals),
                agreement_rate=0.90,
                data_completeness=1.0 if report else 0.85,
            )

            # 14. Compile Summary
            summary = aggregate_summary(
                failures=normalized_failures,
                clusters=clusters,
                patterns=patterns,
                correlations=correlations,
                trends=trends,
                impacts=impacts,
                recommendations=recommendations,
            )

            return IntelligenceAnalysis(
                target_name=target,
                summary=summary,
                clusters=clusters,
                patterns=patterns,
                correlations=correlations,
                trends=trends,
                impacts=impacts,
                recommendations=recommendations,
                confidence=analysis_conf,
                evidence=evidence_pool,
                metadata={
                    "normalized_failures_count": len(normalized_failures),
                    "raw_failures_count": len(all_failures),
                },
            )

    def analyze_evaluation(
        self,
        report: EvaluationReport,
        history: Sequence[EvaluationReport] | EvaluationHistoryManager | None = None,
        baseline_report: EvaluationReport | None = None,
        baseline: EvaluationBaseline | None = None,
        traces: Sequence[ExecutionTrace] | None = None,
    ) -> IntelligenceAnalysis:
        """Analyze a completed evaluation run against history and baselines."""
        return self.analyze(
            report=report,
            history=history,
            baseline_report=baseline_report,
            baseline=baseline,
            traces=traces,
            target_name=report.target_name,
        )

    def analyze_failures(
        self,
        failures: Sequence[FailureReport],
        traces: Sequence[ExecutionTrace] | None = None,
        root_causes: Sequence[RootCause] | None = None,
        target_name: str = "failures",
    ) -> IntelligenceAnalysis:
        """Analyze a collection of raw failure reports in isolation."""
        return self.analyze(
            failures=failures,
            traces=traces,
            root_causes=root_causes,
            target_name=target_name,
        )

    def analyze_history(
        self,
        history: Sequence[EvaluationReport] | EvaluationHistoryManager,
        target_name: str | None = None,
    ) -> IntelligenceAnalysis:
        """Analyze historical evaluation trends and longitudinal patterns."""
        reports = list(history) if isinstance(history, (list, tuple)) else None
        return self.analyze(
            reports=reports,
            history=history,
            target_name=target_name or "historical_analysis",
        )

    def analyze_production(
        self,
        traces: Sequence[ExecutionTrace] | None = None,
        failures: Sequence[FailureReport] | None = None,
        monitor: Any | None = None,
        target_name: str = "production",
    ) -> IntelligenceAnalysis:
        """Analyze production traces and sampled runtime failures."""
        prod_failures = list(failures or [])
        prod_traces = list(traces or [])
        if monitor and hasattr(monitor, "get_recent_failures"):
            prod_failures.extend(monitor.get_recent_failures())
        return self.analyze(
            failures=prod_failures,
            traces=prod_traces,
            target_name=target_name,
        )

    def explain(self, analysis: IntelligenceAnalysis) -> dict[str, Any]:
        """Produce structured dictionary answering the 10 core questions."""
        return self.explainer.explain_ten_questions(analysis)

    def explain_text(self, analysis: IntelligenceAnalysis) -> str:
        """Format terminal/markdown report answering the 10 core questions."""
        return self.explainer.format_text(analysis)
