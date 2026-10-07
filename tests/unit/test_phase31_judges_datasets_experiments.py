"""Unit tests for Phase 31 Judges, Reliability, Datasets, Regressions, Experiments, Online Drift, and EvaluationEngine."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    RunResult,
    TestCase,
)
from aireliability.evaluation.datasets.manager import (
    DatasetManager,
    compare_datasets,
    validate_dataset,
)
from aireliability.evaluation.datasets.models import DatasetSplit, EvaluationDataset
from aireliability.evaluation.engine import EvaluationEngine
from aireliability.evaluation.experiments.manager import ExperimentManager
from aireliability.evaluation.experiments.models import VariantConfig
from aireliability.evaluation.judges.providers import CustomCallableJudge
from aireliability.evaluation.judges.reliability import (
    JudgeReliabilityEvaluator,
    cohens_kappa,
    fleiss_kappa,
)
from aireliability.evaluation.models import EvaluationRequest, EvaluationTarget
from aireliability.evaluation.online.bridge import (
    ProductionSampler,
)
from aireliability.evaluation.online.drift import (
    EvaluationDriftDetector,
    calculate_psi,
)
from aireliability.evaluation.regression.diff import EvaluationRegressionDetector
from aireliability.evaluation.regression.models import RegressionDimension
from aireliability.evaluation.semantic.mock_judge import MockSemanticJudge


def test_custom_callable_judge():
    def custom_fn(
        prompt: str, output: str, reference: str | None, criteria: list[str] | None
    ):
        return (0.9, "Looks solid")

    judge = CustomCallableJudge(callable_fn=custom_fn, judge_name="MyCustomJudge")
    res = judge.judge(prompt="What is AI?", output="Artificial intelligence.")
    assert res.score == 0.9
    assert res.passed is True
    assert res.provider == "custom"
    assert res.model == "MyCustomJudge"


def test_judge_reliability_and_kappas():
    # Cohen's Kappa
    rater_1 = ["pass", "pass", "fail", "pass"]
    rater_2 = ["pass", "pass", "fail", "pass"]
    assert cohens_kappa(rater_1, rater_2) == 1.0

    rater_disagree = ["fail", "fail", "pass", "fail"]
    assert cohens_kappa(rater_1, rater_disagree) < 0.0

    # Fleiss Kappa
    # 3 raters evaluating 4 items
    ratings = [
        [0, 3],  # 3 raters chose category 1
        [1, 2],
        [3, 0],
        [0, 3],
    ]
    fk = fleiss_kappa(ratings)
    assert 0.0 <= fk <= 1.0

    # JudgeReliabilityEvaluator
    evaluator = JudgeReliabilityEvaluator(judge_name="TestJudge")
    judge = MockSemanticJudge(default_score=0.85)
    test_cases = [
        TestCase(
            name="t1", input="Explain gravity", expected_output="force of attraction"
        ),
        TestCase(name="t2", input="Explain atoms", expected_output="building blocks"),
    ]
    report = evaluator.evaluate_judge(
        judge=judge,
        test_cases=test_cases,
        outputs=["Gravity is a force.", "Atoms are tiny particles."],
    )
    assert report.judge_name == "MockSemanticJudge"
    assert report.consistency_rate >= 0.0


def test_dataset_models_and_manager():
    tc1 = TestCase(name="tc1", input="Hi")
    tc2 = TestCase(name="tc2", input="Bye")
    dataset = EvaluationDataset(
        name="Golden Set",
        split=DatasetSplit.TEST,
        test_cases=[tc1, tc2],
        tags=["nlp", "core"],
    )

    # Validate
    errors = validate_dataset(dataset)
    assert len(errors) == 0

    # Export & Import via Manager
    with TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "dataset.json"
        jsonl_path = Path(tmpdir) / "dataset.jsonl"
        csv_path = Path(tmpdir) / "dataset.csv"

        DatasetManager.export_to_json(dataset, json_path)
        DatasetManager.export_to_jsonl(dataset, jsonl_path)
        DatasetManager.export_to_csv(dataset, csv_path)

        loaded_json = DatasetManager.load_from_json(json_path)
        loaded_jsonl = DatasetManager.load_from_jsonl(jsonl_path, name="From JSONL")
        loaded_csv = DatasetManager.load_from_csv(csv_path, name="From CSV")

        assert len(loaded_json.test_cases) == 2
        assert len(loaded_jsonl.test_cases) == 2
        assert len(loaded_csv.test_cases) == 2

    # Compare
    tc3 = TestCase(name="tc3", input="New test")
    dataset_v2 = EvaluationDataset(
        name="Golden Set v2",
        test_cases=[tc1, tc3],
    )
    diff = compare_datasets(dataset, dataset_v2)
    assert len(diff["added"]) == 1
    assert len(diff["removed"]) == 1


def test_regression_detector():
    tc = TestCase(name="tc_reg", input="prompt")
    trace_baseline = ExecutionTrace(
        test_id=tc.id,
        latency_ms=100.0,
        output="Good Answer",
    )
    ev_baseline = EvaluationResult(
        evaluator="QualityEvaluator",
        score=0.95,
        passed=True,
    )
    run_baseline = RunResult(
        test_case=tc,
        trace=trace_baseline,
        evaluations=[ev_baseline],
        passed=True,
    )

    trace_current = ExecutionTrace(
        test_id=tc.id,
        latency_ms=800.0,
        output="Degraded Answer",
    )
    ev_current = EvaluationResult(
        evaluator="QualityEvaluator",
        score=0.40,
        passed=False,
        message="Output degraded",
    )
    run_current = RunResult(
        test_case=tc,
        trace=trace_current,
        evaluations=[ev_current],
        passed=False,
    )

    detector = EvaluationRegressionDetector(min_score_drop=0.20)
    summary = detector.compare_runs([run_baseline], [run_current])

    assert summary.has_regressions is True
    assert summary.total_regressions >= 1
    assert RegressionDimension.QUALITY.value in summary.regressions_by_dimension
    assert len(summary.generated_regression_tests) >= 1
    assert len(summary.root_cause_reports) >= 1


def test_experiment_manager():
    mgr = ExperimentManager(alpha=0.05)
    var_a = VariantConfig(
        name="Prompt-A", model_name="gpt-4o", prompt_template="Prompt A: {input}"
    )
    var_b = VariantConfig(
        name="Prompt-B", model_name="gpt-4o", prompt_template="Prompt B: {input}"
    )

    scores_a = {"accuracy": [0.70, 0.72, 0.71, 0.69]}
    scores_b = {"accuracy": [0.90, 0.92, 0.91, 0.89]}

    res = mgr.compare(var_a, scores_a, var_b, scores_b)
    assert res.deltas["accuracy"] > 0.15
    assert res.winner == "Prompt-B"


def test_online_bridge_and_drift_detection():
    # Production sampling
    sampler = ProductionSampler(sample_rate=0.5, seed=123)
    trace_err = ExecutionTrace(test_id="t_err", status=ExecutionStatus.FAILED)
    assert sampler.should_sample(trace_err) is True

    # Drift detection using PSI
    base_dist = [0.85, 0.90, 0.88, 0.92, 0.87, 0.89]
    shifted_dist = [0.40, 0.45, 0.42, 0.38, 0.41, 0.39]

    psi = calculate_psi(base_dist, shifted_dist)
    assert psi > 0.25  # Significant distribution shift

    detector = EvaluationDriftDetector(psi_threshold=0.20)
    report = detector.detect_drift(
        metric="accuracy",
        baseline_values=base_dist,
        current_values=shifted_dist,
    )
    assert report.drift_detected is True
    assert report.severity == "SIGNIFICANT"


def test_evaluation_engine_end_to_end():
    tc = TestCase(name="greeting_test", input="Hello AI")
    dataset = EvaluationDataset(name="Simple Suite", test_cases=[tc])

    def mock_agent(case: TestCase) -> str:
        return f"Response to {case.input}"

    target = EvaluationTarget(name="MockAgent", agent=mock_agent)
    request = EvaluationRequest(
        dataset=dataset,
        target=target,
        evaluators=["JsonValid"],  # String-resolved evaluator from registry
    )

    engine = EvaluationEngine()
    report = engine.evaluate(request)

    assert report.total_test_cases == 1
    assert report.execution_id is not None
    assert report.dataset_id == dataset.id
