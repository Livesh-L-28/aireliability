"""Unit tests for Phase 32: Evaluation Operations & Governance (Scoring, Gates, Reporting)."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

from aireliability.core.models import (
    EvaluationResult,
    FailureReport,
)
from aireliability.evaluation.governance.gates import (
    GateDecision,
    GatePolicy,
    ReliabilityGateEngine,
)
from aireliability.evaluation.governance.reporting import EvaluationReporter
from aireliability.evaluation.governance.scoring import (
    ReliabilityDimension,
    ReliabilityScoringEngine,
)
from aireliability.evaluation.models import EvaluationReport


def _create_sample_report(
    target_name: str = "TestAgent",
    dataset_id: str = "ds_sample",
    passed: bool = True,
    evaluations: list[EvaluationResult] | None = None,
    failures: list[FailureReport] | None = None,
) -> EvaluationReport:
    evals = evaluations or [
        EvaluationResult(
            evaluator="CorrectnessEvaluator",
            score=0.92,
            passed=True,
            metric="correctness",
        ),
        EvaluationResult(
            evaluator="RelevanceEvaluator",
            score=0.88,
            passed=True,
            metric="relevance",
        ),
        EvaluationResult(
            evaluator="RetrievalEvaluator",
            score=0.85,
            passed=True,
            metric="ndcg@5",
        ),
    ]
    return EvaluationReport(
        request_id="req_test_01",
        target_name=target_name,
        dataset_id=dataset_id,
        total_test_cases=len(evals),
        passed_test_cases=len(evals) if passed else 0,
        failed_test_cases=0 if passed else len(evals),
        evaluations=evals,
        failures=failures or [],
    )


def test_unified_reliability_scoring_normal():
    engine = ReliabilityScoringEngine()
    report = _create_sample_report(passed=True)

    score = engine.compute_score(report)
    assert score.passed is True
    assert score.veto_triggered is False
    assert 0.75 <= score.composite_score <= 1.0
    assert score.status in ("EXCELLENT", "HEALTHY")
    assert ReliabilityDimension.QUALITY.value in score.dimensional_scores
    assert ReliabilityDimension.RETRIEVAL.value in score.dimensional_scores


def test_unified_reliability_scoring_veto_override():
    """Critical safety/security failures must veto and override composite score."""
    engine = ReliabilityScoringEngine(veto_score_penalty=0.0)

    # Evaluations with high quality and retrieval scores, but critical safety failure
    evals = [
        EvaluationResult(
            evaluator="QualityEvaluator",
            score=0.99,
            passed=True,
        ),
        EvaluationResult(
            evaluator="RetrievalEvaluator",
            score=0.98,
            passed=True,
        ),
        EvaluationResult(
            evaluator="SafetyEvaluator",
            score=0.0,
            passed=False,
            message="Harmful content detected",
        ),
    ]
    report = _create_sample_report(passed=False, evaluations=evals)

    score = engine.compute_score(report)
    assert score.veto_triggered is True
    assert score.passed is False
    assert score.status == "BLOCKED"
    assert score.composite_score == 0.0  # Completely overridden
    assert any("SAFETY" in r for r in score.veto_reasons)


def test_reliability_gate_pass_and_fail():
    gate_engine = ReliabilityGateEngine()
    policy = GatePolicy(min_overall_score=0.80)

    # 1. Passing report
    report_pass = _create_sample_report(passed=True)
    res_pass = gate_engine.evaluate_gate(report_pass, policy=policy)
    assert res_pass.decision == GateDecision.PASS
    assert res_pass.passed is True
    assert res_pass.blocked is False

    # 2. Failing report (low score)
    low_evals = [
        EvaluationResult(
            evaluator="QualityEvaluator",
            score=0.50,
            passed=False,
            message="Poor quality",
        )
    ]
    report_fail = _create_sample_report(passed=False, evaluations=low_evals)
    res_fail = gate_engine.evaluate_gate(report_fail, policy=policy)
    assert res_fail.decision == GateDecision.FAIL
    assert res_fail.passed is False
    assert res_fail.blocked is False
    assert len(res_fail.reasons) >= 1


def test_reliability_gate_block_on_critical_safety():
    gate_engine = ReliabilityGateEngine()
    policy = GatePolicy(block_on_critical_safety=True)

    safety_fail_evals = [
        EvaluationResult(
            evaluator="SafetyEvaluator",
            score=0.0,
            passed=False,
            message="Dangerous instructions",
        )
    ]
    report_block = _create_sample_report(passed=False, evaluations=safety_fail_evals)
    res_block = gate_engine.evaluate_gate(report_block, policy=policy)

    assert res_block.decision == GateDecision.BLOCK
    assert res_block.blocked is True
    assert res_block.passed is False
    assert len(res_block.blocking_reasons) >= 1


def test_multi_format_reporting_renderers():
    report = _create_sample_report(passed=True)
    scoring_engine = ReliabilityScoringEngine()
    gate_engine = ReliabilityGateEngine()
    score = scoring_engine.compute_score(report)
    gate = gate_engine.evaluate_gate(report, reliability_score=score)

    # 1. CLI text
    cli_text = EvaluationReporter.render_cli(report, score, gate)
    assert "AI RELIABILITY EVALUATION REPORT" in cli_text
    assert report.target_name in cli_text
    assert "Composite Reliability Score:" in cli_text

    # 2. JSON
    json_text = EvaluationReporter.render_json(report, score, gate)
    json_data = json.loads(json_text)
    assert "report" in json_data
    assert "reliability_score" in json_data
    assert "gate_result" in json_data

    # 3. JSONL
    jsonl_text = EvaluationReporter.render_jsonl(report, score, gate)
    jsonl_lines = jsonl_text.strip().split("\n")
    assert len(jsonl_lines) >= 2
    assert all(json.loads(line) for line in jsonl_lines)

    # 4. CSV
    csv_text = EvaluationReporter.render_csv(report, score, gate)
    reader = csv.reader(csv_text.strip().split("\n"))
    rows = list(reader)
    assert rows[0][0] == "report_id"
    assert len(rows) >= 2

    # 5. Markdown
    md_text = EvaluationReporter.render_markdown(report, score, gate)
    assert "# AI Reliability Evaluation Report" in md_text
    assert "Dimensional Breakdown" in md_text
    assert "Release Gate:" in md_text

    # 6. HTML
    html_text = EvaluationReporter.render_html(report, score, gate)
    assert "<!DOCTYPE html>" in html_text
    assert "AI Reliability Platform Report" in html_text
    assert f"GATE: {gate.decision.value}" in html_text

    # 7. JUnit XML
    junit_text = EvaluationReporter.render_junit_xml(report, score, gate)
    root = ET.fromstring(junit_text)
    assert root.tag == "testsuites"
    assert len(root.findall("testsuite")) >= 1


def test_export_report_files():
    report = _create_sample_report(passed=True)
    scoring_engine = ReliabilityScoringEngine()
    score = scoring_engine.compute_score(report)

    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        EvaluationReporter.export_report(
            report, tmp_path / "out.json", fmt="json", score=score
        )
        EvaluationReporter.export_report(
            report, tmp_path / "out.jsonl", fmt="jsonl", score=score
        )
        EvaluationReporter.export_report(
            report, tmp_path / "out.csv", fmt="csv", score=score
        )
        EvaluationReporter.export_report(
            report, tmp_path / "out.md", fmt="md", score=score
        )
        EvaluationReporter.export_report(
            report, tmp_path / "out.html", fmt="html", score=score
        )
        EvaluationReporter.export_report(
            report, tmp_path / "out.xml", fmt="junit", score=score
        )

        assert (tmp_path / "out.json").exists()
        assert (tmp_path / "out.jsonl").exists()
        assert (tmp_path / "out.csv").exists()
        assert (tmp_path / "out.md").exists()
        assert (tmp_path / "out.html").exists()
        assert (tmp_path / "out.xml").exists()
