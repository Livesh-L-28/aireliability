"""Integration tests for Phase 34 AI Reliability Intelligence with evaluation, governance, and CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aireliability import (
    ContinuousReliabilityMonitor,
    ProductionRegressionHarvester,
    ProductionSampler,
)
from aireliability.cli import main
from aireliability.core.models import (
    ExecutionTrace,
    FailureReport,
    TestCase,
)
from aireliability.diagnosis.models import RootCause, RootCauseCategory, RootCauseType
from aireliability.evaluation.engine import EvaluationEngine
from aireliability.evaluation.governance.baselines import (
    EvaluationHistoryManager,
)
from aireliability.evaluation.models import (
    EvaluationReport,
    EvaluationTarget,
    MetricResult,
)
from aireliability.execution.runner import ReliabilityRunner
from aireliability.intelligence.engine import ReliabilityIntelligenceEngine
from aireliability.intelligence.models import (
    ImpactSeverity,
    RecommendationPriority,
)
from aireliability.observability.incidents import IncidentManager
from aireliability.observability.manager import ObservabilityManager
from aireliability.regression import BaselineManager


def test_phase34_backward_compatibility_v020_apis() -> None:
    """Verify that all public v0.2.0 platform APIs remain intact and functional."""
    # Core
    tc = TestCase(name="test_1", input="hello", expected="world")
    trace = ExecutionTrace(input="hello", output="world")
    runner = ReliabilityRunner(agent=lambda x: x)
    assert runner is not None
    assert tc.name == "test_1"
    assert trace.input == "hello"

    # Evaluation
    target = EvaluationTarget(name="agent_target")
    eval_engine = EvaluationEngine()
    assert eval_engine is not None
    assert target.name == "agent_target"

    # Diagnosis & Governance
    rc = RootCause(
        category=RootCauseCategory.OUTPUT, type=RootCauseType.UNEXPECTED_OUTPUT
    )
    base_mgr = BaselineManager()
    hist_mgr = EvaluationHistoryManager()
    assert rc.category == RootCauseCategory.OUTPUT
    assert base_mgr is not None
    assert hist_mgr is not None

    # Observability & Production
    obs = ObservabilityManager()
    inc_mgr = IncidentManager()
    sampler = ProductionSampler()
    monitor = ContinuousReliabilityMonitor()
    harvester = ProductionRegressionHarvester()
    assert obs is not None
    assert inc_mgr is not None
    assert sampler is not None
    assert monitor is not None
    assert harvester is not None


def test_phase34_full_platform_pipeline_integration(tmp_path: Path) -> None:
    """End-to-end integration: Evaluation -> Diagnosis -> Intelligence -> Incident -> Recommendations."""
    obs = ObservabilityManager()
    engine = ReliabilityIntelligenceEngine(
        observability=obs, incident_manager=obs.incidents
    )

    # 1. Synthesize failing evaluation report with security breach
    failures = [
        FailureReport(
            failure_id="f_sec_1",
            trace_id="tr_sec_1",
            category="security",
            type="credential_exposure",
            message="Model leaked private API key in output response",
            metadata={"component": "guardrail:data_leak"},
        ),
        FailureReport(
            failure_id="f_ret_1",
            trace_id="tr_ret_1",
            category="retrieval",
            type="missing_context",
            message="Knowledge base search failed for user query",
            metadata={"component": "retriever:vector_db"},
        ),
        FailureReport(
            failure_id="f_ret_2",
            trace_id="tr_ret_2",
            category="retrieval",
            type="missing_context",
            message="Knowledge base search returned zero results",
            metadata={"component": "retriever:vector_db"},
        ),
    ]

    report = EvaluationReport(
        report_id="rep_e2e",
        target_name="support_agent",
        dataset_id="golden_support",
        total_test_cases=10,
        passed_test_cases=7,
        failed_test_cases=3,
        metrics={
            "accuracy": MetricResult(name="accuracy", value=0.70),
            "groundedness": MetricResult(name="groundedness", value=0.65),
        },
        failures=failures,
    )

    # 2. Run Intelligence Engine
    analysis = engine.analyze_evaluation(report)

    # 3. Verify Clusters
    assert len(analysis.clusters) >= 2
    cat_names = {c.dominant_category for c in analysis.clusters}
    assert "security" in cat_names
    assert "retrieval" in cat_names

    # 4. Verify Impact & Incident Triggering
    sec_impact = next((imp for imp in analysis.impacts if imp.security_critical), None)
    assert sec_impact is not None
    assert sec_impact.observed_impact == ImpactSeverity.CRITICAL

    incidents = obs.incidents.list_incidents()
    assert len(incidents) >= 1
    assert incidents[0].severity == "CRITICAL"
    title_lower = incidents[0].title.lower()
    assert any(
        w in title_lower for w in ("security", "safety", "critical", "gate", "block")
    )

    # 5. Verify Recommendations
    crit_recs = [
        r
        for r in analysis.recommendations
        if r.priority == RecommendationPriority.CRITICAL
    ]
    assert len(crit_recs) >= 1
    assert "Block" in crit_recs[0].title or "Gate" in crit_recs[0].title

    # 6. Verify Explainer
    answers = engine.explain(analysis)
    assert answers["questions"]["1_what_failed"]["total_failures"] == 3
    assert answers["questions"]["7_impact"]["critical_issues_count"] >= 1
    assert len(answers["questions"]["10_investigate_first"]["action_items"]) >= 1


def test_phase34_cli_subcommands_e2e(tmp_path: Path, capsys: Any) -> None:
    """Test all `airel intelligence` CLI subcommands against report files and JSON outputs."""
    report_file = tmp_path / "test_report.json"
    rep_data = {
        "report_id": "rep_cli_test",
        "target_name": "agent_cli",
        "dataset_id": "ds_cli",
        "total_test_cases": 10,
        "passed_test_cases": 8,
        "failed_test_cases": 2,
        "metrics": {"accuracy": {"name": "accuracy", "value": 0.80}},
        "failures": [
            {
                "failure_id": "fail_1",
                "trace_id": "trace_1",
                "category": "tool",
                "type": "wrong_tool",
                "message": "Model called tool:lookup instead of tool:search",
                "metadata": {"component": "tool:lookup"},
            },
            {
                "failure_id": "fail_2",
                "trace_id": "trace_2",
                "category": "tool",
                "type": "wrong_tool",
                "message": "Model called tool:lookup instead of tool:search",
                "metadata": {"component": "tool:lookup"},
            },
        ],
    }
    report_file.write_text(json.dumps(rep_data), encoding="utf-8")

    # 1. airel intelligence analyze
    code = main(["intelligence", "analyze", str(report_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "AI RELIABILITY INTELLIGENCE REPORT" in out

    # 2. airel intelligence analyze --json
    code = main(["intelligence", "analyze", str(report_file), "--json"])
    assert code == 0
    json_out = capsys.readouterr().out
    parsed = json.loads(json_out)
    assert parsed["target_name"] == "agent_cli"
    assert parsed["summary"]["total_failures_analyzed"] == 2

    # 3. airel intelligence failures
    code = main(["intelligence", "failures", str(report_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Normalized Failures" in out
    assert "tool:lookup" in out

    # 4. airel intelligence clusters
    code = main(["intelligence", "clusters", str(report_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Failure Clusters" in out

    # 5. airel intelligence patterns
    code = main(["intelligence", "patterns", str(report_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Failure Patterns" in out

    # 6. airel intelligence impact
    code = main(["intelligence", "impact", str(report_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Impact Assessments" in out

    # 7. airel intelligence recommendations
    code = main(["intelligence", "recommendations", str(report_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Reliability Recommendations" in out

    # 8. airel intelligence explain
    code = main(["intelligence", "explain", str(report_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "WHAT FAILED?" in out
    assert "WHY DID IT FAIL?" in out
    assert "WHAT SHOULD AN ENGINEER INVESTIGATE OR FIX FIRST?" in out

    # 9. Test missing file error handling
    code = main(["intelligence", "analyze", "non_existent_file.json"])
    assert code == 1
