"""Unit tests for Candidate Evaluation, Statistical Sampling, and Result Caching."""

from __future__ import annotations

from aireliability.optimization.evaluator import (
    OptimizationEvaluator,
    _compute_baseline_deltas,
)
from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    CandidateStatus,
    OptimizationCandidate,
    OptimizationObjective,
    OptimizationProblem,
)


def test_baseline_deltas_calculation() -> None:
    """Test absolute, relative, and percentage delta computation."""
    cand_metrics = {"quality": 0.94, "latency": 0.9, "cost": 0.015}
    base_metrics = {"quality": 0.91, "latency": 1.2, "cost": 0.020}

    deltas = _compute_baseline_deltas(cand_metrics, base_metrics)

    assert deltas["quality"]["absolute"] == 0.03
    assert round(deltas["quality"]["percentage"], 2) == 3.30

    assert deltas["latency"]["absolute"] == -0.3
    assert round(deltas["latency"]["percentage"], 2) == -25.0

    assert deltas["cost"]["absolute"] == -0.005
    assert round(deltas["cost"]["percentage"], 2) == -25.0


def test_evaluator_execution_and_deltas() -> None:
    """Test candidate evaluation against problem baseline and objectives."""
    evaluator = OptimizationEvaluator()
    base_cfg = create_configuration({"temperature": 0.7, "top_k": 5})
    prob = OptimizationProblem(
        name="Eval Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "latency": 0.85, "cost": 0.02},
        objectives=[
            OptimizationObjective(objective_id="quality", metric="quality"),
            OptimizationObjective(objective_id="cost", metric="cost"),
        ],
    )

    cand_cfg = create_configuration({"temperature": 0.4, "top_k": 8})
    cand = OptimizationCandidate(
        candidate_id="cand_test_1",
        configuration=cand_cfg,
        fingerprint=cand_cfg.fingerprint,
    )

    evaluated, exps = evaluator.evaluate_candidate(cand, prob, repeats=1)

    assert evaluated.status == CandidateStatus.EVALUATED
    assert "quality" in evaluated.objective_values
    assert "cost" in evaluated.objective_values
    assert "quality" in evaluated.baseline_deltas
    assert evaluated.confidence > 0.0
    assert len(exps) == 1


def test_repeated_evaluation_statistics() -> None:
    """Test repeated candidate evaluations calculate mean, median, variance, and confidence."""
    eval_calls = 0

    def mock_eval(cfg: dict) -> dict[str, float]:
        nonlocal eval_calls
        eval_calls += 1
        # Slightly noisy metrics across runs
        return {
            "quality": 0.92 + (eval_calls * 0.005),
            "cost": 0.018,
            "latency": 0.65,
        }

    evaluator = OptimizationEvaluator(custom_evaluator_fn=mock_eval)
    prob = OptimizationProblem(
        name="Noise Problem",
        baseline_config=create_configuration({"temperature": 0.5}),
        baseline_metrics={"quality": 0.90},
        objectives=[OptimizationObjective(objective_id="quality", metric="quality")],
    )

    cand = OptimizationCandidate(
        candidate_id="cand_noise",
        configuration=create_configuration({"temperature": 0.4}),
        fingerprint="cfg_noise",
    )

    evaluated, exps = evaluator.evaluate_candidate(cand, prob, repeats=3)

    assert eval_calls == 3
    assert len(exps) == 3
    stats = evaluated.metric_stats["quality"]
    assert stats["count"] == 3
    assert stats["mean"] > 0.90
    assert "variance" in stats
    assert "std_dev" in stats
    assert 0.1 <= evaluated.confidence <= 1.0


def test_evaluator_result_caching() -> None:
    """Test that repeated calls with same fingerprint hit cache without re-executing evaluator."""
    call_count = 0

    def counting_eval(cfg: dict) -> dict[str, float]:
        nonlocal call_count
        call_count += 1
        return {"quality": 0.95, "cost": 0.01}

    evaluator = OptimizationEvaluator(custom_evaluator_fn=counting_eval)
    prob = OptimizationProblem(
        name="Cache Problem",
        baseline_config=create_configuration({"dummy": 1}),
        baseline_metrics={"quality": 0.90},
        objectives=[OptimizationObjective(objective_id="quality", metric="quality")],
    )

    cand1 = OptimizationCandidate(
        candidate_id="cand_cache_1",
        configuration=create_configuration({"temp": 0.5}),
        fingerprint="cfg_fixed_123",
    )

    cand2 = OptimizationCandidate(
        candidate_id="cand_cache_2",
        configuration=create_configuration({"temp": 0.5}),
        fingerprint="cfg_fixed_123",  # Identical fingerprint!
    )

    eval1, _ = evaluator.evaluate_candidate(cand1, prob)
    assert call_count == 1
    assert "cached" not in eval1.metadata

    eval2, _ = evaluator.evaluate_candidate(cand2, prob)
    assert call_count == 1  # Cache HIT: counting_eval was NOT called again
    assert eval2.metadata.get("cached") is True
    assert eval2.objective_values == eval1.objective_values
