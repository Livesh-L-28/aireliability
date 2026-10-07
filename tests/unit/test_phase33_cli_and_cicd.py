"""Unit tests for Phase 33: Developer Platform & Production Integration.

Covers:
- Developer CLI commands: evaluate, dataset, score, gate, report, experiment
- Release gate exit codes: 0 for PASS, 1 for FAIL, 2 for BLOCK
- CI/CD integration: workflow generation, PR comment generation
- Production integration: ContinuousReliabilityMonitor, ProductionRegressionHarvester
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from aireliability.cli import main
from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
)
from aireliability.evaluation.cicd import (
    generate_github_actions_workflow,
    generate_pr_comment,
    write_github_workflow_template,
)
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.evaluation.governance.gates import (
    ReliabilityGateEngine,
)
from aireliability.evaluation.governance.scoring import (
    ReliabilityScoringEngine,
)
from aireliability.evaluation.models import EvaluationReport
from aireliability.evaluation.online.pipeline import (
    ContinuousReliabilityMonitor,
    ProductionRegressionHarvester,
)
from aireliability.failures.taxonomy import FailureCategory


def _create_dummy_report(
    target: str = "AssistantApp",
    passed: bool = True,
    critical_breach: bool = False,
) -> EvaluationReport:
    evals = [
        EvaluationResult(
            test_id="tc_1",
            evaluator="CorrectnessEvaluator",
            passed=passed,
            score=0.95 if passed else 0.40,
            metric="accuracy",
        ),
        EvaluationResult(
            test_id="tc_2",
            evaluator="SafetyEvaluator",
            passed=not critical_breach,
            score=0.10 if critical_breach else 0.98,
            metric="safety",
            message="Prompt injection detected"
            if critical_breach
            else "Safety checks passed",
        ),
    ]
    failures = []
    if critical_breach:
        failures.append(
            FailureReport(
                test_id="tc_2",
                trace_id="tr_999",
                category=FailureCategory.SAFETY,
                message="Critical jailbreak bypassed safety guardrails.",
            )
        )
    return EvaluationReport(
        report_id="rep_test_01",
        target_name=target,
        dataset_id="ds_sample",
        evaluations=evals,
        failures=failures,
        passed=passed and not critical_breach,
        passed_test_cases=1 if critical_breach or not passed else 2,
        failed_test_cases=1 if critical_breach or not passed else 0,
        total_test_cases=2,
    )


class TestPhase33CLI:
    """Test suite for Developer CLI extensions."""

    def test_cli_evaluate_run_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["evaluate", "run", "--format", "terminal"])
        captured = capsys.readouterr().out
        assert exit_code == 0
        assert "AI RELIABILITY EVALUATION REPORT" in captured

    def test_cli_evaluate_run_with_output_and_format(self) -> None:
        with TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "report.json"
            exit_code = main(
                ["evaluate", "run", "--output", str(out_path), "--format", "json"]
            )
            assert exit_code == 0
            assert out_path.exists()
            data = json.loads(out_path.read_text(encoding="utf-8"))
            assert "report" in data

    def test_cli_dataset_lifecycle(self) -> None:
        with TemporaryDirectory() as tmpdir:
            ds_path = Path(tmpdir) / "my_dataset.json"

            # 1. Create
            res_create = main(
                ["dataset", "create", "--name", "EvalSet", "--output", str(ds_path)]
            )
            assert res_create == 0
            assert ds_path.exists()

            # 2. Inspect
            res_inspect = main(["dataset", "inspect", "--file", str(ds_path)])
            assert res_inspect == 0

            # 3. Validate empty (valid schema)
            res_val = main(["dataset", "validate", "--file", str(ds_path)])
            assert res_val == 0

            # 4. Compare with candidate
            ds_path_b = Path(tmpdir) / "candidate.json"
            main(
                [
                    "dataset",
                    "create",
                    "--name",
                    "CandidateSet",
                    "--output",
                    str(ds_path_b),
                ]
            )
            res_cmp = main(
                [
                    "dataset",
                    "compare",
                    "--base",
                    str(ds_path),
                    "--candidate",
                    str(ds_path_b),
                ]
            )
            assert res_cmp == 0

    def test_cli_score_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        with TemporaryDirectory() as tmpdir:
            rep = _create_dummy_report()
            rep_file = Path(tmpdir) / "report.json"
            rep_file.write_text(rep.model_dump_json(), encoding="utf-8")

            exit_code = main(["score", "--report", str(rep_file)])
            captured = capsys.readouterr().out
            assert exit_code == 0
            assert "Composite Reliability Score:" in captured

    def test_cli_gate_exit_codes_pass_fail_block(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with TemporaryDirectory() as tmpdir:
            # 1. PASS (Code 0)
            rep_pass = _create_dummy_report(passed=True, critical_breach=False)
            f_pass = Path(tmpdir) / "pass.json"
            f_pass.write_text(rep_pass.model_dump_json(), encoding="utf-8")
            code_pass = main(["gate", "--report", str(f_pass), "--min-score", "0.50"])
            assert code_pass == 0

            # 2. FAIL (Code 1) - Low score below threshold
            rep_fail = _create_dummy_report(passed=False, critical_breach=False)
            f_fail = Path(tmpdir) / "fail.json"
            f_fail.write_text(rep_fail.model_dump_json(), encoding="utf-8")
            code_fail = main(["gate", "--report", str(f_fail), "--min-score", "0.99"])
            assert code_fail == 1

            # 3. BLOCK (Code 2) - Critical safety violation triggers non-compensatory veto
            rep_block = _create_dummy_report(passed=False, critical_breach=True)
            f_block = Path(tmpdir) / "block.json"
            f_block.write_text(rep_block.model_dump_json(), encoding="utf-8")
            code_block = main(["gate", "--report", str(f_block), "--min-score", "0.10"])
            assert code_block == 2

    def test_cli_report_formats(self, capsys: pytest.CaptureFixture[str]) -> None:
        with TemporaryDirectory() as tmpdir:
            rep = _create_dummy_report()
            rep_file = Path(tmpdir) / "report.json"
            rep_file.write_text(rep.model_dump_json(), encoding="utf-8")

            # Markdown
            res_md = main(["report", "--report", str(rep_file), "--format", "markdown"])
            out_md = capsys.readouterr().out
            assert res_md == 0
            assert "## Test Suite Summary" in out_md

            # HTML
            res_html = main(["report", "--report", str(rep_file), "--format", "html"])
            out_html = capsys.readouterr().out
            assert res_html == 0
            assert "<!DOCTYPE html>" in out_html
            assert "AI Reliability Evaluation Dashboard" in out_html

            # JUnit XML
            res_xml = main(["report", "--report", str(rep_file), "--format", "junit"])
            out_xml = capsys.readouterr().out
            assert res_xml == 0
            assert "<testsuites" in out_xml

            # PR Comment
            res_pr = main(
                ["report", "--report", str(rep_file), "--format", "pr-comment"]
            )
            out_pr = capsys.readouterr().out
            assert res_pr == 0
            assert "### 🤖 AI Reliability Evaluation Summary" in out_pr

    def test_cli_experiment_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        res = main(
            [
                "experiment",
                "--variant-a",
                "gpt-4o",
                "--variant-b",
                "claude-3-5-sonnet",
                "--metric",
                "accuracy",
            ]
        )
        out = capsys.readouterr().out
        assert res == 0
        assert "A/B Experiment:" in out
        assert "gpt-4o" in out
        assert "claude-3-5-sonnet" in out


class TestPhase33CICD:
    """Test suite for CI/CD workflow generation and PR comments."""

    def test_generate_github_actions_workflow(self) -> None:
        wf = generate_github_actions_workflow()
        assert "name: AI Evaluation & Reliability Gate" in wf
        assert "airel evaluate run" in wf
        assert "airel gate" in wf

    def test_write_github_workflow_template(self) -> None:
        with TemporaryDirectory() as tmpdir:
            wf_path = Path(tmpdir) / ".github" / "workflows" / "eval.yml"
            written = write_github_workflow_template(wf_path)
            assert written.exists()
            content = written.read_text(encoding="utf-8")
            assert "AI Evaluation & Reliability Gate" in content

    def test_generate_pr_comment(self) -> None:
        rep = _create_dummy_report()
        score = ReliabilityScoringEngine().calculate(rep)
        gate = ReliabilityGateEngine().evaluate(rep, score)
        comment = generate_pr_comment(
            report=rep, score=score, gate=gate, baseline_score=0.80
        )

        assert "### 🤖 AI Reliability Evaluation Summary" in comment
        assert "| **Composite Score** |" in comment
        assert "vs baseline" in comment
        assert "| **Release Gate** |" in comment


class TestPhase33ProductionIntegration:
    """Test suite for continuous reliability monitoring and automated regression harvesting."""

    def test_continuous_reliability_monitor(self) -> None:
        monitor = ContinuousReliabilityMonitor(window_size=5, max_age_seconds=60.0)

        results = [
            EvaluationResult(
                test_id=f"tc_{i}",
                evaluator="CorrectnessEvaluator",
                passed=True,
                score=0.90,
            )
            for i in range(10)
        ]
        monitor.record(results)

        # Sliding window enforces window_size = 5
        assert len(monitor.current_results) == 5
        score = monitor.current_score()
        assert score.composite_score >= 0.8
        assert monitor.is_healthy(min_score=0.8) is True

    def test_production_regression_harvester_loop(self) -> None:
        with TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "golden.json"
            harvester = ProductionRegressionHarvester(auto_save_path=save_path)

            trace = ExecutionTrace(
                trace_id="tr_prod_fail_1",
                test_id="prod_query_42",
                input={"query": "Show financial summary"},
                status=ExecutionStatus.FAILED,
            )
            failures = [
                FailureReport(
                    failure_id="fail_prod_01",
                    test_id="prod_query_42",
                    trace_id="tr_prod_fail_1",
                    category=FailureCategory.OUTPUT,
                    message="Model failed to return valid JSON balance sheet.",
                )
            ]

            harvested = harvester.harvest_from_trace(trace=trace, failures=failures)

            assert len(harvested) == 1
            tc = harvested[0]
            assert "Regression:" in tc.name
            assert "production_regression" in tc.tags
            assert tc.metadata.get("source_trace_id") == "tr_prod_fail_1"

            # Check that golden dataset was updated and persisted
            assert save_path.exists()
            saved_ds = EvaluationDataset.model_validate_json(
                save_path.read_text(encoding="utf-8")
            )
            assert len(saved_ds.test_cases) == 1
            assert saved_ds.test_cases[0].id == tc.id
