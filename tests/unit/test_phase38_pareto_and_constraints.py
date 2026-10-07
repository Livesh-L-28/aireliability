"""Unit tests for Pareto dominance, frontier extraction, crowding distance, and hard constraints."""

from __future__ import annotations

from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    CandidateStatus,
    ConstraintOperator,
    ObjectiveDirection,
    OptimizationCandidate,
    OptimizationConstraint,
    OptimizationObjective,
)
from aireliability.optimization.pareto import (
    check_dominance,
    find_pareto_frontier,
)


def _build_candidate(
    cid: str, values: dict[str, float], is_feasible: bool = True
) -> OptimizationCandidate:
    cfg = create_configuration({"dummy": 1})
    cand = OptimizationCandidate(
        candidate_id=cid,
        configuration=cfg,
        fingerprint=cfg.fingerprint,
        is_feasible=is_feasible,
    )
    cand.objective_values = dict(values)
    return cand


def test_pareto_dominance_maximization_and_minimization() -> None:
    """Test pairwise Pareto dominance logic."""
    obj_qual = OptimizationObjective(
        objective_id="quality", metric="quality", direction=ObjectiveDirection.MAXIMIZE
    )
    obj_cost = OptimizationObjective(
        objective_id="cost", metric="cost", direction=ObjectiveDirection.MINIMIZE
    )
    objs = [obj_qual, obj_cost]

    # Candidate A: Quality 0.95, Cost 0.02
    # Candidate B: Quality 0.90, Cost 0.05
    # A dominates B (higher quality, lower cost)
    vals_a = {"quality": 0.95, "cost": 0.02}
    vals_b = {"quality": 0.90, "cost": 0.05}

    assert check_dominance(vals_a, vals_b, objs) is True
    assert check_dominance(vals_b, vals_a, objs) is False

    # Candidate C: Quality 0.98, Cost 0.08
    # Neither A nor C dominates each other (trade-off)
    vals_c = {"quality": 0.98, "cost": 0.08}
    assert check_dominance(vals_a, vals_c, objs) is False
    assert check_dominance(vals_c, vals_a, objs) is False


def test_find_pareto_frontier_tradeoffs() -> None:
    """Test extraction of non-dominated Pareto frontier with competing objectives."""
    objs = [
        OptimizationObjective(
            objective_id="quality",
            metric="quality",
            direction=ObjectiveDirection.MAXIMIZE,
        ),
        OptimizationObjective(
            objective_id="cost", metric="cost", direction=ObjectiveDirection.MINIMIZE
        ),
    ]

    c_a = _build_candidate("c_a", {"quality": 0.95, "cost": 0.05})  # Pareto
    c_b = _build_candidate("c_b", {"quality": 0.90, "cost": 0.02})  # Pareto (cheaper)
    c_c = _build_candidate(
        "c_c", {"quality": 0.88, "cost": 0.06}
    )  # Dominated by both A and B
    c_d = _build_candidate(
        "c_d", {"quality": 0.98, "cost": 0.10}
    )  # Pareto (highest quality)

    frontier = find_pareto_frontier([c_a, c_b, c_c, c_d], objs)

    assert "c_a" in frontier.non_dominated_candidate_ids
    assert "c_b" in frontier.non_dominated_candidate_ids
    assert "c_d" in frontier.non_dominated_candidate_ids
    assert "c_c" in frontier.dominated_candidate_ids

    assert c_c.is_pareto is False
    assert c_c.status == CandidateStatus.DOMINATED


def test_hard_constraint_veto() -> None:
    """A candidate violating a hard safety/security constraint must NEVER become Pareto-optimal."""
    objs = [
        OptimizationObjective(
            objective_id="quality",
            metric="quality",
            direction=ObjectiveDirection.MAXIMIZE,
        ),
        OptimizationObjective(
            objective_id="cost", metric="cost", direction=ObjectiveDirection.MINIMIZE
        ),
    ]
    constraints = [
        OptimizationConstraint(
            constraint_id="hard_safety",
            metric="safety",
            operator=ConstraintOperator.GE,
            threshold=0.95,
            is_hard=True,
        )
    ]

    # Candidate Safe: Quality 0.90, Cost 0.05, Safety 0.98
    c_safe = _build_candidate("c_safe", {"quality": 0.90, "cost": 0.05, "safety": 0.98})
    # Candidate Unsafe: Quality 0.99, Cost 0.01, Safety 0.80 (Violates hard safety constraint!)
    c_unsafe = _build_candidate(
        "c_unsafe", {"quality": 0.99, "cost": 0.01, "safety": 0.80}
    )

    frontier = find_pareto_frontier([c_safe, c_unsafe], objs, constraints=constraints)

    assert "c_safe" in frontier.non_dominated_candidate_ids
    assert "c_unsafe" not in frontier.non_dominated_candidate_ids
    assert c_unsafe.is_feasible is False
    assert c_unsafe.is_pareto is False
    assert c_unsafe.status == CandidateStatus.INVALID
    assert len(c_unsafe.constraint_violations) > 0


def test_normalization_and_crowding_distance() -> None:
    """Test objective value normalization and NSGA-II crowding distance computation."""
    objs = [
        OptimizationObjective(
            objective_id="quality",
            metric="quality",
            direction=ObjectiveDirection.MAXIMIZE,
        ),
        OptimizationObjective(
            objective_id="latency",
            metric="latency",
            direction=ObjectiveDirection.MINIMIZE,
        ),
    ]

    c1 = _build_candidate("c1", {"quality": 0.80, "latency": 0.2})
    c2 = _build_candidate("c2", {"quality": 0.90, "latency": 0.5})
    c3 = _build_candidate("c3", {"quality": 0.95, "latency": 1.0})

    frontier = find_pareto_frontier([c1, c2, c3], objs)

    # All 3 are non-dominated trade-offs
    assert len(frontier.non_dominated_candidate_ids) == 3

    # Extreme points should receive high/infinite crowding distance
    ext_c1 = next(p for p in frontier.points if p.candidate_id == "c1")
    ext_c3 = next(p for p in frontier.points if p.candidate_id == "c3")
    mid_c2 = next(p for p in frontier.points if p.candidate_id == "c2")

    assert ext_c1.crowding_distance == 1000.0  # Capped inf
    assert ext_c3.crowding_distance == 1000.0  # Capped inf
    assert 0.0 <= mid_c2.crowding_distance < 1000.0
