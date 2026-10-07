"""Unit tests for Reliability Gates, Policy Selector, and Tie-breaking Hierarchy."""

from __future__ import annotations

from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.gates import OptimizationGateChecker
from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationPolicy,
    ParetoFrontier,
    SelectionStrategy,
)
from aireliability.optimization.selector import OptimizationSelector


def _make_candidate(
    cid: str,
    metrics: dict[str, float],
    is_feasible: bool = True,
    normalized: dict[str, float] | None = None,
) -> OptimizationCandidate:
    cfg = create_configuration({"test": cid})
    cand = OptimizationCandidate(
        candidate_id=cid,
        configuration=cfg,
        fingerprint=cfg.fingerprint,
        is_feasible=is_feasible,
        objective_values=dict(metrics),
        normalized_values=dict(normalized or metrics),
    )
    return cand


def test_gate_checker_pass_and_fail() -> None:
    """Test gate checker enforces safety, security, and quality cutoffs."""
    gate_checker = OptimizationGateChecker()
    policy = OptimizationPolicy(
        required_safety=0.95,
        required_security=0.95,
        required_quality=0.85,
    )

    passing_cand = _make_candidate(
        "c_pass", {"safety": 0.98, "security": 0.99, "quality": 0.90}
    )
    passed, reasons = gate_checker.check_gates(passing_cand, policy)
    assert passed is True
    assert reasons == []

    failing_cand = _make_candidate(
        "c_fail", {"safety": 0.80, "security": 0.99, "quality": 0.90}
    )
    passed, reasons = gate_checker.check_gates(failing_cand, policy)
    assert passed is False
    assert any("Safety gate failed" in r for r in reasons)


def test_gate_checker_regression_veto() -> None:
    """Test gate checker detects and vetoes critical quality regression over baseline."""
    gate_checker = OptimizationGateChecker()
    policy = OptimizationPolicy()
    base_metrics = {"quality": 0.92, "error_rate": 0.02}

    regressed_cand = _make_candidate(
        "c_regress",
        {"quality": 0.82, "error_rate": 0.10, "safety": 0.98, "security": 0.99},
    )
    passed, reasons = gate_checker.check_gates(
        regressed_cand, policy, baseline_metrics=base_metrics
    )
    assert passed is False
    assert any("Critical regression detected" in r for r in reasons)


def test_selector_strategies() -> None:
    """Test selection strategies: highest_quality, lowest_cost, lowest_latency, balanced."""
    c_qual = _make_candidate(
        "c_qual",
        {
            "quality": 0.98,
            "cost": 0.10,
            "latency": 1.5,
            "safety": 0.99,
            "security": 0.99,
        },
    )
    c_cost = _make_candidate(
        "c_cost",
        {
            "quality": 0.88,
            "cost": 0.01,
            "latency": 0.8,
            "safety": 0.99,
            "security": 0.99,
        },
    )
    c_lat = _make_candidate(
        "c_lat",
        {
            "quality": 0.89,
            "cost": 0.05,
            "latency": 0.3,
            "safety": 0.99,
            "security": 0.99,
        },
    )

    cands = [c_qual, c_cost, c_lat]
    frontier = ParetoFrontier(
        points=[],
        objective_ids=["quality", "cost", "latency"],
        non_dominated_candidate_ids=["c_qual", "c_cost", "c_lat"],
        dominated_candidate_ids=[],
    )

    selector = OptimizationSelector()

    # 1. Highest quality
    pol_q = OptimizationPolicy(selection_strategy=SelectionStrategy.HIGHEST_QUALITY)
    sel_q, _, _ = selector.select(frontier, cands, pol_q)
    assert sel_q is not None
    assert sel_q.candidate_id == "c_qual"

    # 2. Lowest cost
    pol_c = OptimizationPolicy(selection_strategy=SelectionStrategy.LOWEST_COST)
    sel_c, _, _ = selector.select(frontier, cands, pol_c)
    assert sel_c is not None
    assert sel_c.candidate_id == "c_cost"

    # 3. Lowest latency
    pol_l = OptimizationPolicy(selection_strategy=SelectionStrategy.LOWEST_LATENCY)
    sel_l, _, _ = selector.select(frontier, cands, pol_l)
    assert sel_l is not None
    assert sel_l.candidate_id == "c_lat"


def test_selector_tie_breaking_hierarchy() -> None:
    """When candidates have identical strategy score, safety and security break ties."""
    # Two candidates with identical quality, but cand_a has higher safety
    c_a = _make_candidate(
        "c_a",
        {
            "quality": 0.95,
            "cost": 0.05,
            "safety": 0.99,
            "security": 0.99,
            "reliability": 0.98,
        },
    )
    c_b = _make_candidate(
        "c_b",
        {
            "quality": 0.95,
            "cost": 0.05,
            "safety": 0.96,
            "security": 0.99,
            "reliability": 0.98,
        },
    )

    cands = [c_b, c_a]
    frontier = ParetoFrontier(
        points=[],
        objective_ids=["quality"],
        non_dominated_candidate_ids=["c_a", "c_b"],
        dominated_candidate_ids=[],
    )

    selector = OptimizationSelector()
    policy = OptimizationPolicy(selection_strategy=SelectionStrategy.HIGHEST_QUALITY)

    selected, _, _ = selector.select(frontier, cands, policy)
    assert selected is not None
    assert selected.candidate_id == "c_a"  # c_a preferred due to higher safety score!


def test_selector_no_feasible_solution() -> None:
    """If all candidates violate gates, selector returns None and explainable failure."""
    c_bad1 = _make_candidate(
        "c_bad1", {"safety": 0.70, "security": 0.90, "quality": 0.50}
    )
    c_bad2 = _make_candidate(
        "c_bad2", {"safety": 0.60, "security": 0.90, "quality": 0.60}
    )

    frontier = ParetoFrontier(
        points=[],
        objective_ids=["quality"],
        non_dominated_candidate_ids=["c_bad1", "c_bad2"],
        dominated_candidate_ids=[],
    )

    selector = OptimizationSelector()
    policy = OptimizationPolicy(required_safety=0.95)

    selected, decision, explanation = selector.select(
        frontier, [c_bad1, c_bad2], policy
    )
    assert selected is None
    assert decision is None
    assert "NO_FEASIBLE_CONFIGURATION" in explanation
