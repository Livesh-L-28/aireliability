"""Unit tests for Phase 34 CrossRunCorrelation analyzer."""

from __future__ import annotations

from aireliability.evaluation.models import EvaluationReport, MetricResult
from aireliability.intelligence.correlation import CorrelationAnalyzer
from aireliability.intelligence.models import CorrelationType


def _make_report(
    report_id: str,
    metrics: dict[str, float],
    metadata: dict[str, str],
) -> EvaluationReport:
    m_dict = {name: MetricResult(name=name, value=val) for name, val in metrics.items()}
    return EvaluationReport(
        report_id=report_id,
        target_name="agent",
        dataset_id="golden",
        total_test_cases=20,
        passed_test_cases=15,
        failed_test_cases=5,
        metrics=m_dict,
        metadata=metadata,
    )


def test_model_version_correlation() -> None:
    analyzer = CorrelationAnalyzer()
    base_rep = _make_report("base", {"accuracy": 0.90}, {"model": "claude-3-opus"})
    curr_rep = _make_report("curr", {"accuracy": 0.70}, {"model": "claude-3-haiku"})

    correlations = analyzer.analyze_correlations(curr_rep, base_rep)
    assert len(correlations) == 1
    corr = correlations[0]
    assert corr.source_change_type == "model_version"
    assert "claude-3-opus -> claude-3-haiku" in corr.source_change_value
    assert corr.affected_metric_or_failure == "accuracy"
    assert corr.is_causal is False
    assert corr.relationship_type == CorrelationType.CORRELATED


def test_retriever_version_correlation() -> None:
    analyzer = CorrelationAnalyzer()
    base_rep = _make_report("base", {"context_recall": 0.85}, {"retriever": "bm25"})
    curr_rep = _make_report("curr", {"context_recall": 0.60}, {"retriever": "dense_v1"})

    correlations = analyzer.analyze_correlations(curr_rep, base_rep)
    assert len(correlations) == 1
    corr = correlations[0]
    assert corr.source_change_type == "retriever_version"
    assert "bm25 -> dense_v1" in corr.source_change_value
    assert corr.affected_metric_or_failure == "context_recall"
    assert corr.is_causal is False


def test_prompt_version_correlation() -> None:
    analyzer = CorrelationAnalyzer()
    base_rep = _make_report(
        "base", {"instruction_following": 0.95}, {"prompt_version": "v1.2"}
    )
    curr_rep = _make_report(
        "curr", {"instruction_following": 0.80}, {"prompt_version": "v2.0"}
    )

    correlations = analyzer.analyze_correlations(curr_rep, base_rep)
    assert len(correlations) == 1
    corr = correlations[0]
    assert corr.source_change_type == "prompt_version"
    assert "v1.2 -> v2.0" in corr.source_change_value
    assert corr.affected_metric_or_failure == "instruction_following"


def test_no_changes_no_correlations() -> None:
    analyzer = CorrelationAnalyzer()
    base_rep = _make_report("base", {"accuracy": 0.90}, {"model": "gpt-4o"})
    curr_rep = _make_report("curr", {"accuracy": 0.91}, {"model": "gpt-4o"})

    correlations = analyzer.analyze_correlations(curr_rep, base_rep)
    assert len(correlations) == 0


def test_none_baseline_returns_empty() -> None:
    analyzer = CorrelationAnalyzer()
    curr_rep = _make_report("curr", {"accuracy": 0.70}, {"model": "gpt-4o"})
    assert analyzer.analyze_correlations(curr_rep, None) == []
