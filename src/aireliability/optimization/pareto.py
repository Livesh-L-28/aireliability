"""Multi-objective Pareto dominance, frontier extraction, and crowding distance analysis."""

from __future__ import annotations

import math
from typing import Any

from aireliability.optimization.models import (
    CandidateStatus,
    ObjectiveDirection,
    OptimizationCandidate,
    OptimizationConstraint,
    OptimizationObjective,
    ParetoFrontier,
    ParetoPoint,
)


def _is_better(
    v_a: float, v_b: float, obj: OptimizationObjective, epsilon: float = 1e-9
) -> bool:
    """Return True if v_a is strictly better than v_b for given objective direction."""
    if obj.direction == ObjectiveDirection.MAXIMIZE:
        return v_a > v_b + epsilon
    if obj.direction == ObjectiveDirection.MINIMIZE:
        return v_a < v_b - epsilon
    if obj.direction == ObjectiveDirection.TARGET:
        target = obj.target_value or 0.0
        return abs(v_a - target) < abs(v_b - target) - epsilon
    return False


def _is_worse(
    v_a: float, v_b: float, obj: OptimizationObjective, epsilon: float = 1e-9
) -> bool:
    """Return True if v_a is strictly worse than v_b for given objective direction."""
    if obj.direction == ObjectiveDirection.MAXIMIZE:
        return v_a < v_b - epsilon
    if obj.direction == ObjectiveDirection.MINIMIZE:
        return v_a > v_b + epsilon
    if obj.direction == ObjectiveDirection.TARGET:
        target = obj.target_value or 0.0
        return abs(v_a - target) > abs(v_b - target) + epsilon
    return False


def check_dominance(
    a_vals: dict[str, float],
    b_vals: dict[str, float],
    objectives: list[OptimizationObjective],
    epsilon: float = 1e-9,
) -> bool:
    """Check if candidate A Pareto-dominates candidate B.

    Candidate A dominates B if:
    1. A is no worse than B across all objectives.
    2. A is strictly better than B in at least one objective.
    """
    has_strictly_better = False

    for obj in objectives:
        v_a = a_vals.get(obj.objective_id, a_vals.get(obj.metric, 0.0))
        v_b = b_vals.get(obj.objective_id, b_vals.get(obj.metric, 0.0))

        if _is_worse(v_a, v_b, obj, epsilon):
            return False

        if _is_better(v_a, v_b, obj, epsilon):
            has_strictly_better = True

    return has_strictly_better


def normalize_objectives(
    candidates: list[OptimizationCandidate],
    objectives: list[OptimizationObjective],
) -> dict[str, dict[str, float]]:
    """Normalize objective values across candidates into [0.0, 1.0] intervals.

    Stores normalized values directly on candidate.normalized_values and returns a lookup dict.
    """
    if not candidates or not objectives:
        return {}

    # Extract bounds per objective
    bounds: dict[str, tuple[float, float]] = {}
    for obj in objectives:
        vals = [
            c.objective_values.get(
                obj.objective_id, c.objective_values.get(obj.metric, 0.0)
            )
            for c in candidates
        ]
        min_v = min(vals) if vals else 0.0
        max_v = max(vals) if vals else 1.0
        bounds[obj.objective_id] = (min_v, max_v)

    norm_map: dict[str, dict[str, float]] = {}
    for cand in candidates:
        cand_norm: dict[str, float] = {}
        for obj in objectives:
            val = cand.objective_values.get(
                obj.objective_id, cand.objective_values.get(obj.metric, 0.0)
            )
            min_v, max_v = bounds[obj.objective_id]
            span = max_v - min_v

            norm_val = 1.0 if span <= 1e-12 else (val - min_v) / span

            # For MINIMIZE objectives, invert so 1.0 is always optimal
            if obj.direction == ObjectiveDirection.MINIMIZE:
                norm_val = 1.0 - norm_val
            elif obj.direction == ObjectiveDirection.TARGET:
                target = obj.target_value or 0.0
                err = abs(val - target)
                max_err = max(abs(min_v - target), abs(max_v - target), 1e-6)
                norm_val = max(0.0, 1.0 - (err / max_err))

            cand_norm[obj.objective_id] = round(max(0.0, min(1.0, norm_val)), 6)

        cand.normalized_values = cand_norm
        norm_map[cand.candidate_id] = cand_norm

    return norm_map


def calculate_crowding_distance(
    points: list[ParetoPoint],
    objectives: list[OptimizationObjective],
) -> list[ParetoPoint]:
    """Calculate NSGA-II crowding distance for Pareto frontier points to measure diversity.

    Returns updated points list with crowding_distance fields set.
    """
    n = len(points)
    if n <= 2:
        return [
            ParetoPoint(
                candidate_id=p.candidate_id,
                configuration_values=p.configuration_values,
                objective_values=p.objective_values,
                normalized_values=p.normalized_values,
                rank=p.rank,
                crowding_distance=float("inf"),
                is_dominated=p.is_dominated,
            )
            for p in points
        ]

    distances = {p.candidate_id: 0.0 for p in points}

    for obj in objectives:
        key = obj.objective_id
        sorted_points = sorted(
            points,
            key=lambda pt: pt.objective_values.get(
                key, pt.objective_values.get(obj.metric, 0.0)
            ),
        )

        min_val = sorted_points[0].objective_values.get(
            key, sorted_points[0].objective_values.get(obj.metric, 0.0)
        )
        max_val = sorted_points[-1].objective_values.get(
            key, sorted_points[-1].objective_values.get(obj.metric, 0.0)
        )
        val_range = max_val - min_val

        # Extremes receive infinite crowding distance
        distances[sorted_points[0].candidate_id] = float("inf")
        distances[sorted_points[-1].candidate_id] = float("inf")

        if val_range > 1e-12:
            for i in range(1, n - 1):
                prev_val = sorted_points[i - 1].objective_values.get(
                    key, sorted_points[i - 1].objective_values.get(obj.metric, 0.0)
                )
                next_val = sorted_points[i + 1].objective_values.get(
                    key, sorted_points[i + 1].objective_values.get(obj.metric, 0.0)
                )
                cid = sorted_points[i].candidate_id
                if not math.isinf(distances[cid]):
                    distances[cid] += (next_val - prev_val) / val_range

    result_points: list[ParetoPoint] = []
    for p in points:
        cd = distances.get(p.candidate_id, 0.0)
        # Cap inf to 1000.0 for json-friendly serialization
        serialized_cd = 1000.0 if math.isinf(cd) else round(cd, 6)
        result_points.append(
            ParetoPoint(
                candidate_id=p.candidate_id,
                configuration_values=p.configuration_values,
                objective_values=p.objective_values,
                normalized_values=p.normalized_values,
                rank=p.rank,
                crowding_distance=serialized_cd,
                is_dominated=p.is_dominated,
            )
        )

    return result_points


def evaluate_constraints(
    candidate: OptimizationCandidate,
    constraints: list[OptimizationConstraint],
) -> tuple[bool, list[str]]:
    """Evaluate constraints against candidate objective or metric values.

    Returns (is_feasible, list_of_violation_reasons).
    """
    violations: list[str] = []
    is_feasible = True

    for c in constraints:
        # Check candidate objective values first, then metadata
        val = candidate.objective_values.get(c.metric, candidate.metadata.get(c.metric))
        if val is None:
            # Check baseline deltas or stats
            val = candidate.metric_stats.get(c.metric, {}).get("mean")

        if val is None:
            continue

        if not c.evaluate(float(val)):
            msg = (
                f"Constraint '{c.constraint_id}' violated: {c.metric}={val} "
                f"fails {c.operator.value} {c.threshold}"
            )
            violations.append(msg)
            if c.is_hard:
                is_feasible = False

    return is_feasible, violations


def find_pareto_frontier(
    candidates: list[OptimizationCandidate],
    objectives: list[OptimizationObjective],
    constraints: list[OptimizationConstraint] | None = None,
) -> ParetoFrontier:
    """Extract the non-dominated Pareto frontier from candidate evaluations.

    Candidates violating hard constraints are deemed infeasible and can NEVER
    become Pareto-optimal.
    """
    if not candidates:
        return ParetoFrontier(
            points=[],
            objective_ids=[o.objective_id for o in objectives],
            non_dominated_candidate_ids=[],
            dominated_candidate_ids=[],
        )

    # Step 1: Pre-filter hard constraints
    active_constraints = constraints or []
    for cand in candidates:
        is_feas, violations = evaluate_constraints(cand, active_constraints)
        if not is_feas:
            cand.is_feasible = False
            cand.status = CandidateStatus.INVALID
            cand.constraint_violations = violations

    # Step 2: Normalize objectives across all evaluated candidates
    normalize_objectives(candidates, objectives)

    # Step 3: Dominance check among feasible candidates
    feasible_cands = [c for c in candidates if c.is_feasible]
    dominated_ids: set[str] = set()
    non_dominated_ids: set[str] = set()

    for i, c_a in enumerate(feasible_cands):
        is_dom = False
        for j, c_b in enumerate(feasible_cands):
            if i != j and check_dominance(
                c_b.objective_values, c_a.objective_values, objectives
            ):
                is_dom = True
                break

        if is_dom:
            dominated_ids.add(c_a.candidate_id)
            c_a.is_pareto = False
            c_a.status = CandidateStatus.DOMINATED
        else:
            non_dominated_ids.add(c_a.candidate_id)
            c_a.is_pareto = True
            c_a.status = CandidateStatus.PARETO_OPTIMAL

    # Build ParetoPoint records
    raw_points: list[ParetoPoint] = []
    for cand in feasible_cands:
        raw_points.append(
            ParetoPoint(
                candidate_id=cand.candidate_id,
                configuration_values=cand.configuration.values,
                objective_values=cand.objective_values,
                normalized_values=cand.normalized_values,
                rank=1 if cand.candidate_id in non_dominated_ids else 2,
                crowding_distance=0.0,
                is_dominated=cand.candidate_id in dominated_ids,
            )
        )

    # Calculate crowding distance on non-dominated frontier points
    frontier_subset = [p for p in raw_points if p.candidate_id in non_dominated_ids]
    frontier_with_distance = calculate_crowding_distance(frontier_subset, objectives)

    # Map distance back to candidates
    cd_map = {p.candidate_id: p.crowding_distance for p in frontier_with_distance}
    for cand in candidates:
        if cand.candidate_id in cd_map:
            cand.crowding_distance = cd_map[cand.candidate_id]

    # Combine back all points
    final_points = frontier_with_distance + [
        p for p in raw_points if p.candidate_id in dominated_ids
    ]

    return ParetoFrontier(
        points=final_points,
        objective_ids=[o.objective_id for o in objectives],
        non_dominated_candidate_ids=sorted(non_dominated_ids),
        dominated_candidate_ids=sorted(dominated_ids),
        metadata={
            "total_candidates": len(candidates),
            "feasible_candidates": len(feasible_cands),
            "pareto_size": len(non_dominated_ids),
        },
    )


def extract_frontier_summary(
    frontier: ParetoFrontier,
) -> list[dict[str, Any]]:
    """Return a table-friendly projection of the Pareto frontier for visualization."""
    summary: list[dict[str, Any]] = []
    for pt in frontier.points:
        row: dict[str, Any] = {
            "candidate_id": pt.candidate_id,
            "is_pareto": not pt.is_dominated,
            "rank": pt.rank,
            "crowding_distance": pt.crowding_distance,
        }
        for k, v in pt.objective_values.items():
            row[k] = v
        for k, v in pt.configuration_values.items():
            row[f"param_{k}"] = v
        summary.append(row)
    return summary
