"""Unit tests for Phase 38 Models and Configuration Fingerprinting."""

from __future__ import annotations

from aireliability.optimization.fingerprint import (
    compute_configuration_fingerprint,
    create_configuration,
)
from aireliability.optimization.models import (
    CandidateStatus,
    ComponentCategory,
    ConstraintOperator,
    ObjectiveDirection,
    OptimizationConstraint,
    OptimizationObjective,
    OptimizationProblem,
    OptimizationResult,
    ParetoFrontier,
    SelectionStrategy,
    StoppingReason,
    VariableDomain,
)


def test_optimization_enums_values() -> None:
    """Verify enum representations match expected string literals."""
    assert ObjectiveDirection.MAXIMIZE == "MAXIMIZE"
    assert ObjectiveDirection.MINIMIZE == "MINIMIZE"
    assert ObjectiveDirection.TARGET == "TARGET"

    assert ConstraintOperator.GE == ">="
    assert ConstraintOperator.LE == "<="

    assert VariableDomain.FLOAT == "float"
    assert VariableDomain.INT == "int"
    assert VariableDomain.CHOICE == "choice"

    assert ComponentCategory.GENERATION == "generation"
    assert ComponentCategory.RETRIEVAL == "retrieval"

    assert CandidateStatus.PARETO_OPTIMAL == "PARETO_OPTIMAL"
    assert StoppingReason.NO_FEASIBLE_CONFIGURATION == "NO_FEASIBLE_CONFIGURATION"
    assert SelectionStrategy.BALANCED == "balanced_score"


def test_constraint_evaluation() -> None:
    """Test constraint mathematical comparison operators."""
    c_ge = OptimizationConstraint(
        constraint_id="c_ge",
        metric="quality",
        operator=ConstraintOperator.GE,
        threshold=0.85,
    )
    assert c_ge.evaluate(0.90) is True
    assert c_ge.evaluate(0.85) is True
    assert c_ge.evaluate(0.80) is False

    c_le = OptimizationConstraint(
        constraint_id="c_le",
        metric="latency",
        operator=ConstraintOperator.LE,
        threshold=1.0,
    )
    assert c_le.evaluate(0.8) is True
    assert c_le.evaluate(1.2) is False

    c_eq = OptimizationConstraint(
        constraint_id="c_eq",
        metric="batch_size",
        operator=ConstraintOperator.EQ,
        threshold=4.0,
    )
    assert c_eq.evaluate(4.0) is True
    assert c_eq.evaluate(5.0) is False


def test_configuration_fingerprint_deterministic() -> None:
    """Test that configuration fingerprinting is strictly deterministic and key-order independent."""
    cfg1 = {"temperature": 0.7, "top_k": 5, "model": "small"}
    cfg2 = {"model": "small", "temperature": 0.7, "top_k": 5}

    fp1 = compute_configuration_fingerprint(cfg1)
    fp2 = compute_configuration_fingerprint(cfg2)

    assert fp1 == fp2
    assert fp1.startswith("cfg_")


def test_configuration_fingerprint_ignores_volatile_fields() -> None:
    """Test that timestamps, run IDs, and metadata are excluded from fingerprint."""
    base = {"temperature": 0.5, "top_k": 10}
    with_volatile = {
        "temperature": 0.5,
        "top_k": 10,
        "timestamp": "2026-10-06T12:00:00Z",
        "id": "run_999",
        "candidate_id": "cand_123",
        "execution_id": "exec_abc",
        "metadata": {"user": "alice"},
    }

    fp_clean = compute_configuration_fingerprint(base)
    fp_volatile = compute_configuration_fingerprint(with_volatile)

    assert fp_clean == fp_volatile


def test_create_configuration_factory() -> None:
    """Test create_configuration auto-computes fingerprint."""
    cfg = create_configuration(
        {"chunk_size": 512, "top_k": 4}, description="Test Config"
    )
    assert cfg.fingerprint.startswith("cfg_")
    assert cfg.values["chunk_size"] == 512
    assert cfg.description == "Test Config"


def test_optimization_problem_and_result_models() -> None:
    """Test instantiation and defaults of OptimizationProblem and OptimizationResult."""
    base_cfg = create_configuration({"temperature": 0.7})
    prob = OptimizationProblem(
        name="Test Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90},
        objectives=[OptimizationObjective(objective_id="quality", metric="quality")],
    )
    assert prob.problem_id.startswith("prob_")
    assert len(prob.objectives) == 1

    frontier = ParetoFrontier(
        points=[],
        objective_ids=["quality"],
        non_dominated_candidate_ids=[],
        dominated_candidate_ids=[],
    )

    result = OptimizationResult(
        problem=prob,
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90},
        candidates=[],
        pareto_frontier=frontier,
        stopping_reason=StoppingReason.COMPLETED,
    )
    assert result.optimization_id.startswith("opt_")
    assert result.stopping_reason == StoppingReason.COMPLETED
