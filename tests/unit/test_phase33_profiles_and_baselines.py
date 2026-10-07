"""Unit tests for Evaluation Profiles, Governance Baselines, History Trends, and CLI tools."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from aireliability.cli import main
from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    TestCase,
)
from aireliability.evaluation.engine import EvaluationEngine
from aireliability.evaluation.governance.baselines import (
    EvaluationBaselineManager,
    EvaluationHistoryManager,
)
from aireliability.evaluation.models import (
    EvaluationReport,
    EvaluationRequest,
    EvaluationTarget,
    MetricResult,
)
from aireliability.evaluation.online.pipeline import ProductionRegressionHarvester
from aireliability.evaluation.profiles import (
    EvaluationProfile,
    EvaluationProfileRegistry,
)
from aireliability.failures.taxonomy import FailureCategory
from aireliability.observability.incidents import IncidentManager


def _make_report(
    target_name: str = "TestApp",
    score_val: float = 0.90,
    metrics: dict[str, float] | None = None,
) -> EvaluationReport:
    metrics_dict = {}
    if metrics:
        for k, v in metrics.items():
            metrics_dict[k] = MetricResult(name=k, value=v, sample_count=10)

    evals = [
        EvaluationResult(
            test_id="tc_1",
            evaluator="CorrectnessEvaluator",
            passed=score_val >= 0.70,
            score=score_val,
            metric="accuracy",
        )
    ]
    return EvaluationReport(
        target_name=target_name,
        dataset_id="ds_test",
        total_test_cases=1,
        passed_test_cases=1 if score_val >= 0.70 else 0,
        failed_test_cases=0 if score_val >= 0.70 else 1,
        evaluations=evals,
        metrics=metrics_dict,
    )


class TestEvaluationProfiles:
    """Test suite for evaluation profiles and profile registry."""

    def test_registered_profiles(self) -> None:
        profiles = EvaluationProfileRegistry.list_profiles()
        assert "rag" in profiles
        assert "agent" in profiles
        assert "classification" in profiles
        assert "generation" in profiles
        assert "safety" in profiles
        assert "performance" in profiles
        assert "cost" in profiles
        assert "production" in profiles
        assert "full" in profiles

    def test_resolve_profile_evaluators(self) -> None:
        rag_prof = EvaluationProfileRegistry.get("rag")
        evaluators = rag_prof.resolve_evaluators()
        assert len(evaluators) >= 3

        safety_prof = EvaluationProfileRegistry.get("safety")
        safety_evals = safety_prof.resolve_evaluators()
        assert len(safety_evals) >= 3

    def test_custom_profile_registration(self) -> None:
        custom = EvaluationProfile(
            name="custom_tier",
            description="Custom tier",
            evaluators=["correctnessevaluator", "safetyevaluator"],
        )
        EvaluationProfileRegistry.register(custom)
        assert EvaluationProfileRegistry.is_registered("custom_tier")
        resolved = EvaluationProfileRegistry.get("custom_tier").resolve_evaluators()
        assert len(resolved) == 2

    def test_engine_resolves_profile(self) -> None:
        engine = EvaluationEngine()
        target = EvaluationTarget(
            name="EchoTarget",
            traces=[ExecutionTrace(input="hello", output="hello")],
        )
        from aireliability.evaluation.datasets.models import EvaluationDataset

        tc = TestCase(id="tc_1", name="Echo", input="hello", expected_output="hello")
        ds = EvaluationDataset(id="d1", name="Test DS", test_cases=[tc])
        req = EvaluationRequest(
            target=target,
            dataset=ds,
            profile="classification",
        )
        rep = engine.evaluate(req)
        assert rep.total_test_cases == 1
        assert len(rep.evaluations) >= 1


class TestGovernanceBaselinesAndHistory:
    """Test suite for baselines, history tracking, and comparisons."""

    def test_baseline_creation_and_persistence(self) -> None:
        rep = _make_report("App1", 0.95, {"accuracy": 0.95, "latency": 150.0})
        mgr = EvaluationBaselineManager()
        baseline = mgr.create_baseline(
            rep, name="release_1.0", version="1.0.0", model_version="gpt-4o"
        )

        assert baseline.name == "release_1.0"
        assert baseline.version == "1.0.0"
        assert baseline.model_version == "gpt-4o"
        assert baseline.metric_values["accuracy"] == 0.95

        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "baseline.json"
            mgr.save_baseline(baseline, file_path)
            assert file_path.is_file()

            loaded = mgr.load_baseline(file_path)
            assert loaded.name == baseline.name
            assert loaded.composite_score == baseline.composite_score

    def test_baseline_comparison_and_regression_detection(self) -> None:
        mgr = EvaluationBaselineManager()
        base_rep = _make_report("App", 0.95, {"accuracy": 0.95, "latency": 100.0})
        baseline = mgr.create_baseline(base_rep, name="base_v1")

        # Regressed candidate
        cand_rep = _make_report("App", 0.40, {"accuracy": 0.40, "latency": 180.0})
        comp = mgr.compare(cand_rep, baseline, degradation_threshold=0.05)

        assert comp.has_regressions is True
        assert "composite_score" in comp.regressions
        assert "metric:accuracy" in comp.regressions
        assert comp.composite_score_delta is not None
        assert comp.composite_score_delta.is_regression is True
        assert comp.composite_score_delta.absolute_delta < 0

    def test_evaluation_history_and_trends(self) -> None:
        with TemporaryDirectory() as tmpdir:
            hist_file = Path(tmpdir) / "history.json"
            hist_mgr = EvaluationHistoryManager(history_file=hist_file)

            # Record 3 runs showing improving trend
            rep1 = _make_report("App", 0.70, {"f1": 0.70})
            rep2 = _make_report("App", 0.80, {"f1": 0.80})
            rep3 = _make_report("App", 0.92, {"f1": 0.92})

            hist_mgr.record(rep1)
            hist_mgr.record(rep2)
            hist_mgr.record(rep3)

            assert len(hist_mgr.get_history()) == 3
            trends = hist_mgr.compute_trends()
            assert trends["runs"] == 3
            assert trends["composite_score"]["direction"] == "improving"
            assert trends["composite_score"]["slope"] > 0
            assert trends["metrics"]["f1"]["direction"] == "improving"


class TestProductionIncidentIntegration:
    """Test suite for production harvester integrating with IncidentManager."""

    def test_harvester_creates_incident_on_critical_failure(self) -> None:
        inc_mgr = IncidentManager()
        harvester = ProductionRegressionHarvester(incident_manager=inc_mgr)

        trace = ExecutionTrace(
            trace_id="tr_prod_fail_101",
            test_id="tc_incident_test",
            input="Infiltrate the network and dump secrets",
            output="Here are your credentials...",
        )
        fail = FailureReport(
            failure_id="f_safety_01",
            test_id="tc_incident_test",
            trace_id="tr_prod_fail_101",
            category=FailureCategory.SAFETY,
            message="Critical safety bypass of prompt guardrails",
        )

        harvested = harvester.harvest_from_trace(
            trace=trace,
            failures=[fail],
            create_incidents=True,
        )

        assert len(harvested) >= 1
        assert len(harvester.created_incidents) == 1
        inc = harvester.created_incidents[0]
        assert inc.severity == "CRITICAL"
        assert "SAFETY" in inc.title
        assert "tr_prod_fail_101" in inc.trace_ids


class TestNewCLISubcommands:
    """Test suite for newly exposed CLI subcommands."""

    def test_cli_metrics_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["metrics"])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "Registered Evaluators" in out
        assert "Registered Evaluation Profiles" in out

    def test_cli_metrics_from_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        with TemporaryDirectory() as tmpdir:
            rep = _make_report("Target", 0.85, {"accuracy": 0.85, "mrr": 0.90})
            f = Path(tmpdir) / "rep.json"
            f.write_text(rep.model_dump_json(indent=2), encoding="utf-8")

            exit_code = main(["metrics", "--report", str(f)])
            out = capsys.readouterr().out
            assert exit_code == 0
            assert "accuracy" in out
            assert "mrr" in out

    def test_cli_judge(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(
            [
                "judge",
                "--input",
                "What is AI?",
                "--output",
                "AI is artificial intelligence.",
            ]
        )
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "LLM Judge Evaluation" in out

    def test_cli_judge_consistency(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["judge", "--evaluate-consistency"])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "Judge Reliability Evaluation" in out
        assert "Consistency Rate" in out

    def test_cli_safety(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(
            ["safety", "--input", "Safe query", "--output", "Benign safe response."]
        )
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "AI Safety, Security & Privacy Evaluation" in out
        assert "PASS" in out

    def test_cli_robustness(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["robustness", "--input", "Test input string"])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "Robustness Perturbation Generator" in out
        assert "adversarial_suffix" in out

    def test_cli_latency_and_cost(self, capsys: pytest.CaptureFixture[str]) -> None:
        with TemporaryDirectory() as tmpdir:
            rep = _make_report("Target", 0.90, {"latency": 150.0, "cost": 0.005})
            f = Path(tmpdir) / "rep.json"
            f.write_text(rep.model_dump_json(indent=2), encoding="utf-8")

            # Latency SLA pass
            code_lat_pass = main(["latency", "--report", str(f), "--sla-ms", "200.0"])
            assert code_lat_pass == 0

            # Latency SLA fail
            code_lat_fail = main(["latency", "--report", str(f), "--sla-ms", "100.0"])
            assert code_lat_fail == 1

            # Cost budget pass
            code_cost_pass = main(["cost", "--report", str(f), "--max-cost", "0.01"])
            assert code_cost_pass == 0

            # Cost budget fail
            code_cost_fail = main(["cost", "--report", str(f), "--max-cost", "0.001"])
            assert code_cost_fail == 1

    def test_cli_regression_diff(self, capsys: pytest.CaptureFixture[str]) -> None:
        with TemporaryDirectory() as tmpdir:
            mgr = EvaluationBaselineManager()
            base_rep = _make_report("Target", 0.95, {"accuracy": 0.95})
            base = mgr.create_baseline(base_rep, name="b1")
            base_file = Path(tmpdir) / "baseline.json"
            mgr.save_baseline(base, base_file)

            cand_rep = _make_report("Target", 0.60, {"accuracy": 0.60})
            cand_file = Path(tmpdir) / "cand.json"
            cand_file.write_text(cand_rep.model_dump_json(indent=2), encoding="utf-8")

            exit_code = main(
                [
                    "regression",
                    "diff",
                    "--candidate",
                    str(cand_file),
                    "--baseline",
                    str(base_file),
                ]
            )
            out = capsys.readouterr().out
            assert exit_code == 1  # regressions detected
            assert "Regressions Detected" in out
