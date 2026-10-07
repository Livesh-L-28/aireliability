"""Unit tests for Phase 38 Serialization (JSON, JSONL, CSV, Markdown)."""

from __future__ import annotations

from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationObjective,
    OptimizationProblem,
    OptimizationResult,
    ParetoFrontier,
    ParetoPoint,
    StoppingReason,
)
from aireliability.optimization.serialization import OptimizationSerializer


def _build_sample_result() -> OptimizationResult:
    base_cfg = create_configuration({"temperature": 0.7, "top_k": 5})
    prob = OptimizationProblem(
        name="Ser Problem",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "cost": 0.02},
        objectives=[
            OptimizationObjective(objective_id="quality", metric="quality"),
            OptimizationObjective(objective_id="cost", metric="cost"),
        ],
    )

    cand1 = OptimizationCandidate(
        candidate_id="cand_1",
        configuration=create_configuration({"temperature": 0.4, "top_k": 8}),
        fingerprint="cfg_1",
        objective_values={"quality": 0.94, "cost": 0.015},
        baseline_deltas={
            "quality": {
                "baseline": 0.90,
                "candidate": 0.94,
                "absolute": 0.04,
                "percentage": 4.44,
            }
        },
        is_pareto=True,
    )
    cand2 = OptimizationCandidate(
        candidate_id="cand_2",
        configuration=create_configuration({"temperature": 0.9, "top_k": 3}),
        fingerprint="cfg_2",
        objective_values={"quality": 0.85, "cost": 0.010},
        is_pareto=False,
    )

    frontier = ParetoFrontier(
        points=[
            ParetoPoint(
                candidate_id="cand_1",
                objective_values={"quality": 0.94, "cost": 0.015},
                rank=1,
            )
        ],
        objective_ids=["quality", "cost"],
        non_dominated_candidate_ids=["cand_1"],
        dominated_candidate_ids=["cand_2"],
    )

    return OptimizationResult(
        problem=prob,
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "cost": 0.02},
        candidates=[cand1, cand2],
        pareto_frontier=frontier,
        selected_candidate=cand1,
        stopping_reason=StoppingReason.COMPLETED,
        duration_seconds=1.23,
    )


def test_json_roundtrip_serialization() -> None:
    """Test full round-trip JSON serialization and validation of OptimizationResult."""
    result = _build_sample_result()
    serialized = OptimizationSerializer.to_json(result)
    assert isinstance(serialized, str)

    restored = OptimizationSerializer.from_json(serialized)
    assert restored.optimization_id == result.optimization_id
    assert restored.problem.name == result.problem.name
    assert len(restored.candidates) == 2
    assert restored.selected_candidate is not None
    assert restored.selected_candidate.candidate_id == "cand_1"
    assert restored.stopping_reason == StoppingReason.COMPLETED


def test_jsonl_serialization() -> None:
    """Test candidate list serialization to JSON Lines."""
    result = _build_sample_result()
    jsonl_str = OptimizationSerializer.to_jsonl(result.candidates)
    lines = jsonl_str.strip().splitlines()
    assert len(lines) == 2

    restored_cands = OptimizationSerializer.from_jsonl(jsonl_str)
    assert len(restored_cands) == 2
    assert restored_cands[0].candidate_id == "cand_1"
    assert restored_cands[1].candidate_id == "cand_2"


def test_csv_export() -> None:
    """Test exporting candidates as CSV table."""
    result = _build_sample_result()
    csv_str = OptimizationSerializer.to_csv(result.candidates)
    assert "candidate_id" in csv_str
    assert "cand_1" in csv_str
    assert "cand_2" in csv_str
    assert "obj_quality" in csv_str
    assert "param_temperature" in csv_str


def test_markdown_report_generation() -> None:
    """Test markdown optimization report includes tables, metrics, and Pareto section."""
    result = _build_sample_result()
    md = OptimizationSerializer.to_markdown(result)
    assert "# Optimization Report" in md
    assert "Executive Summary" in md
    assert "Baseline Configuration & Metrics" in md
    assert "Selected Optimal Candidate" in md
    assert "Pareto Frontier Candidates" in md
    assert "cand_1" in md
