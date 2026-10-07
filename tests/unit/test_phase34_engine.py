"""Unit tests for ReliabilityIntelligenceEngine orchestrator and Registry."""

from __future__ import annotations

from aireliability.core.models import FailureReport
from aireliability.diagnosis.models import RootCause, RootCauseCategory, RootCauseType
from aireliability.evaluation.governance.baselines import EvaluationHistoryManager
from aireliability.evaluation.models import EvaluationReport, MetricResult
from aireliability.intelligence.engine import ReliabilityIntelligenceEngine
from aireliability.intelligence.explain import IntelligenceExplainer
from aireliability.intelligence.models import (
    IntelligenceAnalysis,
)
from aireliability.intelligence.registry import (
    IntelligenceRegistry,
    get_default_registry,
)
from aireliability.observability.manager import ObservabilityManager


def _make_report_with_failures(
    report_id: str = "rep_101",
    target_name: str = "medical_qa_agent",
    fail_count: int = 5,
    category: str = "retrieval",
) -> EvaluationReport:
    failures = [
        FailureReport(
            failure_id=f"fail_{i}",
            trace_id=f"tr_{i}",
            test_id=f"test_{i}",
            category=category,
            type="missing_context",
            message=f"Retrieval returned empty context for symptom query {i}",
            metadata={"component": "retriever:vector_store"},
        )
        for i in range(fail_count)
    ]
    metrics = {
        "accuracy": MetricResult(name="accuracy", value=0.75),
        "groundedness": MetricResult(name="groundedness", value=0.60),
    }
    return EvaluationReport(
        report_id=report_id,
        target_name=target_name,
        dataset_id="golden_med",
        total_test_cases=20,
        passed_test_cases=15,
        failed_test_cases=fail_count,
        metrics=metrics,
        failures=failures,
    )


def test_registry_lifecycle() -> None:
    reg = IntelligenceRegistry()
    assert reg.list() == []

    reg.register("test_analyzer", object())
    assert reg.has("test_analyzer")
    assert "test_analyzer" in reg.list()
    assert reg.get("test_analyzer") is not None

    reg.unregister("test_analyzer")
    assert not reg.has("test_analyzer")

    # Default registry has standard analyzers pre-registered
    default_reg = get_default_registry()
    assert default_reg.has("normalizer")
    assert default_reg.has("clustering")
    assert default_reg.has("patterns")
    assert default_reg.has("trends")
    assert default_reg.has("impact")
    assert default_reg.has("recommendations")


def test_engine_analyze_evaluation_end_to_end() -> None:
    engine = ReliabilityIntelligenceEngine()
    rep = _make_report_with_failures(fail_count=6, category="retrieval")

    analysis: IntelligenceAnalysis = engine.analyze_evaluation(rep)
    assert analysis.target_name == "medical_qa_agent"
    assert analysis.summary.total_failures_analyzed == 6
    assert analysis.summary.total_clusters >= 1
    assert "retrieval" in analysis.summary.dominant_failure_categories

    # Explainer answers the 10 questions
    expl = engine.explain(analysis)
    assert "questions" in expl
    q = expl["questions"]
    assert "1_what_failed" in q
    assert "2_why_did_it_fail" in q
    assert "3_has_this_happened_before" in q
    assert "4_are_multiple_failures_related" in q
    assert "5_is_this_failure_getting_worse" in q
    assert "6_associated_components" in q
    assert "7_impact" in q
    assert "8_confidence" in q
    assert "9_evidence" in q
    assert "10_investigate_first" in q

    text_report = engine.explain_text(analysis)
    assert "AI RELIABILITY INTELLIGENCE REPORT" in text_report
    assert "WHAT FAILED?" in text_report
    assert "WHAT SHOULD AN ENGINEER INVESTIGATE OR FIX FIRST?" in text_report


def test_engine_with_history_manager() -> None:
    engine = ReliabilityIntelligenceEngine()
    history_mgr = EvaluationHistoryManager()

    for i in range(3):
        rep = _make_report_with_failures(
            report_id=f"rep_{i}",
            fail_count=i + 1,
        )
        history_mgr.record(rep)

    curr_rep = _make_report_with_failures(report_id="rep_curr", fail_count=4)
    analysis = engine.analyze_evaluation(curr_rep, history=history_mgr)

    assert analysis.summary.total_trends >= 1
    assert len(analysis.trends) >= 1


def test_engine_incident_creation_on_critical_failure() -> None:
    obs = ObservabilityManager()
    incident_mgr = obs.incidents
    engine = ReliabilityIntelligenceEngine(
        observability=obs, incident_manager=incident_mgr
    )

    safety_failures = [
        FailureReport(
            failure_id="f_safe_1",
            trace_id="tr_safe_1",
            category="safety",
            type="harmful_output",
            message="Harmful medical advice generated without disclaimers",
            metadata={"component": "guardrail:safety"},
        )
    ]
    rep = EvaluationReport(
        report_id="rep_safety",
        target_name="medical_advisor",
        dataset_id="safety_set",
        total_test_cases=5,
        passed_test_cases=4,
        failed_test_cases=1,
        failures=safety_failures,
    )

    analysis = engine.analyze_evaluation(rep)
    assert analysis.summary.critical_issues_count >= 1

    # An incident should have been created in incident_mgr
    incidents = incident_mgr.list_incidents()
    assert len(incidents) >= 1
    assert incidents[0].severity == "CRITICAL"


def test_engine_analyze_failures_standalone() -> None:
    engine = ReliabilityIntelligenceEngine()
    rc = RootCause(
        category=RootCauseCategory.TOOL,
        type=RootCauseType.WRONG_ARGUMENT,
        description="Missing required argument 'query'",
        trace_id="tr_standalone",
    )
    fail = FailureReport(
        failure_id="f_tool_1",
        trace_id="tr_standalone",
        category="tool",
        type="wrong_argument",
        message="Missing parameter: query",
    )

    analysis = engine.analyze_failures([fail], root_causes=[rc])
    assert analysis.summary.total_failures_analyzed == 1
    assert len(analysis.clusters) == 1
    assert analysis.clusters[0].dominant_category == "tool"


def test_explainer_format_json() -> None:
    explainer = IntelligenceExplainer()
    engine = ReliabilityIntelligenceEngine()
    rep = _make_report_with_failures(fail_count=2)
    analysis = engine.analyze_evaluation(rep)

    json_output = explainer.format_json(analysis)
    assert '"questions"' in json_output
    assert '"1_what_failed"' in json_output
    assert '"10_investigate_first"' in json_output
