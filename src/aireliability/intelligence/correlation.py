"""Cross-run correlation analyzer connecting configuration changes to reliability shifts."""

from __future__ import annotations

from collections.abc import Sequence

from aireliability.evaluation.models import EvaluationReport
from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.models import (
    CorrelationType,
    CrossRunCorrelation,
    EvidenceReference,
    FailureCluster,
)


class CorrelationAnalyzer:
    """Detects empirical correlations between configuration changes and reliability outcomes."""

    def analyze_correlations(
        self,
        current_report: EvaluationReport,
        baseline_report: EvaluationReport | None = None,
        clusters: Sequence[FailureCluster] | None = None,
        evidence_pool: list[EvidenceReference] | None = None,
    ) -> list[CrossRunCorrelation]:
        """Correlate metadata/configuration diffs with metric drops and failure clusters."""
        if not baseline_report:
            return []

        correlations: list[CrossRunCorrelation] = []
        curr_meta = current_report.metadata or {}
        base_meta = baseline_report.metadata or {}

        # 1. Model version change correlation
        curr_model = curr_meta.get("model") or curr_meta.get("model_version")
        base_model = base_meta.get("model") or base_meta.get("model_version")
        if curr_model and base_model and curr_model != base_model:
            # Check for accuracy/quality shifts
            curr_acc = current_report.metrics.get(
                "accuracy"
            ) or current_report.metrics.get("correctness")
            base_acc = baseline_report.metrics.get(
                "accuracy"
            ) or baseline_report.metrics.get("correctness")
            if curr_acc and base_acc and (curr_acc.value - base_acc.value) < -0.05:
                delta = curr_acc.value - base_acc.value
                conf = ConfidenceEngine.calculate(
                    evidence_count=2,
                    sample_size=current_report.total_test_cases,
                    agreement_rate=0.85,
                )
                correlations.append(
                    CrossRunCorrelation(
                        source_change_type="model_version",
                        source_change_value=f"{base_model} -> {curr_model}",
                        observed_effect=f"Accuracy dropped by {abs(delta):.2%}",
                        affected_metric_or_failure="accuracy",
                        strength=min(1.0, abs(delta) * 2),
                        is_causal=False,
                        relationship_type=CorrelationType.CORRELATED,
                        confidence=conf,
                        description=(
                            f"Model version change from '{base_model}' to '{curr_model}' "
                            f"coincides with a {abs(delta):.2%} drop in accuracy."
                        ),
                    )
                )

        # 2. Retriever configuration change correlation
        curr_retriever = curr_meta.get("retriever") or curr_meta.get(
            "retriever_version"
        )
        base_retriever = base_meta.get("retriever") or base_meta.get(
            "retriever_version"
        )
        if curr_retriever and base_retriever and curr_retriever != base_retriever:
            # Check for retrieval / context metric changes
            curr_recall = (
                current_report.metrics.get("context_recall")
                or current_report.metrics.get("recall_at_k")
                or current_report.metrics.get("retrieval")
            )
            base_recall = (
                baseline_report.metrics.get("context_recall")
                or baseline_report.metrics.get("recall_at_k")
                or baseline_report.metrics.get("retrieval")
            )
            if (
                curr_recall
                and base_recall
                and (curr_recall.value - base_recall.value) < -0.05
            ):
                delta = curr_recall.value - base_recall.value
                conf = ConfidenceEngine.calculate(
                    evidence_count=2,
                    sample_size=current_report.total_test_cases,
                    agreement_rate=0.9,
                )
                correlations.append(
                    CrossRunCorrelation(
                        source_change_type="retriever_version",
                        source_change_value=f"{base_retriever} -> {curr_retriever}",
                        observed_effect=f"Retrieval recall dropped by {abs(delta):.2%}",
                        affected_metric_or_failure="context_recall",
                        strength=min(1.0, abs(delta) * 2),
                        is_causal=False,
                        relationship_type=CorrelationType.INFERRED,
                        confidence=conf,
                        description=(
                            f"Retriever update from '{base_retriever}' to '{curr_retriever}' "
                            f"strongly correlates with a {abs(delta):.2%} drop in retrieval quality."
                        ),
                    )
                )

        # 3. Prompt version change correlation
        curr_prompt = curr_meta.get("prompt_version") or curr_meta.get("prompt")
        base_prompt = base_meta.get("prompt_version") or base_meta.get("prompt")
        if curr_prompt and base_prompt and curr_prompt != base_prompt:
            curr_if = current_report.metrics.get(
                "instruction_following"
            ) or current_report.metrics.get("format_validation")
            base_if = baseline_report.metrics.get(
                "instruction_following"
            ) or baseline_report.metrics.get("format_validation")
            if curr_if and base_if and (curr_if.value - base_if.value) < -0.05:
                delta = curr_if.value - base_if.value
                conf = ConfidenceEngine.calculate(
                    evidence_count=2,
                    sample_size=current_report.total_test_cases,
                    agreement_rate=0.8,
                )
                correlations.append(
                    CrossRunCorrelation(
                        source_change_type="prompt_version",
                        source_change_value=f"{base_prompt} -> {curr_prompt}",
                        observed_effect=f"Instruction compliance dropped by {abs(delta):.2%}",
                        affected_metric_or_failure="instruction_following",
                        strength=min(1.0, abs(delta) * 2),
                        is_causal=False,
                        relationship_type=CorrelationType.CORRELATED,
                        confidence=conf,
                        description=(
                            f"Prompt modification from '{base_prompt}' to '{curr_prompt}' "
                            f"coincides with an instruction-following degradation."
                        ),
                    )
                )

        # 4. Correlate with failure clusters
        if clusters:
            for c in clusters:
                if (
                    c.dominant_category == "retrieval"
                    and curr_retriever != base_retriever
                    and curr_retriever
                ):
                    correlations.append(
                        CrossRunCorrelation(
                            source_change_type="retriever_version",
                            source_change_value=str(curr_retriever),
                            observed_effect=f"{c.frequency} retrieval failure occurrences in cluster '{c.name}'",
                            affected_metric_or_failure=c.cluster_id,
                            strength=0.85,
                            is_causal=False,
                            relationship_type=CorrelationType.INFERRED,
                            confidence=c.confidence,
                            evidence=c.evidence,
                            description=(
                                f"Retrieval failure cluster '{c.name}' ({c.frequency} failures) "
                                f"coincides with active retriever '{curr_retriever}'."
                            ),
                        )
                    )

        return correlations
