"""Unit tests for Phase 38 CLI subcommands and options."""

from __future__ import annotations

import json
from pathlib import Path

from aireliability.cli import main
from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationObjective,
    OptimizationProblem,
    OptimizationResult,
    ParetoFrontier,
    StoppingReason,
)
from aireliability.optimization.serialization import OptimizationSerializer


def _create_temp_result_file(tmp_path: Path) -> Path:
    base_cfg = create_configuration({"temperature": 0.7, "top_k": 5})
    prob = OptimizationProblem(
        name="CLI Test",
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "cost": 0.02},
        objectives=[OptimizationObjective(objective_id="quality", metric="quality")],
    )
    cand = OptimizationCandidate(
        candidate_id="cand_cli_1",
        configuration=base_cfg,
        fingerprint=base_cfg.fingerprint,
        objective_values={
            "quality": 0.95,
            "cost": 0.015,
            "safety": 0.98,
            "security": 0.99,
        },
        baseline_deltas={
            "quality": {
                "baseline": 0.90,
                "candidate": 0.95,
                "absolute": 0.05,
                "percentage": 5.56,
            }
        },
        is_pareto=True,
    )
    frontier = ParetoFrontier(
        points=[],
        objective_ids=["quality"],
        non_dominated_candidate_ids=["cand_cli_1"],
        dominated_candidate_ids=[],
    )
    res = OptimizationResult(
        problem=prob,
        baseline_config=base_cfg,
        baseline_metrics={"quality": 0.90, "cost": 0.02},
        candidates=[cand],
        pareto_frontier=frontier,
        selected_candidate=cand,
        stopping_reason=StoppingReason.COMPLETED,
        budget_used={"candidates": 1, "evaluations": 1},
    )
    res_file = tmp_path / "opt_result.json"
    res_file.write_text(OptimizationSerializer.to_json(res), encoding="utf-8")
    return res_file


def test_cli_optimize_plan(tmp_path: Path, capsys) -> None:
    """Test airel optimize plan creates a problem definition."""
    out_file = str(tmp_path / "planned_prob.json")
    code = main(["optimize", "plan", "--output", out_file, "--json"])
    assert code == 0
    assert Path(out_file).exists()


def test_cli_optimize_run(tmp_path: Path, capsys) -> None:
    """Test airel optimize run executes search and outputs result."""
    out_file = str(tmp_path / "run_res.json")
    code = main(
        [
            "optimize",
            "run",
            "--strategy",
            "random",
            "--max-candidates",
            "4",
            "--seed",
            "42",
            "--output",
            out_file,
            "--json",
        ]
    )
    assert code == 0
    assert Path(out_file).exists()
    content = json.loads(Path(out_file).read_text(encoding="utf-8"))
    assert "optimization_id" in content
    assert len(content["candidates"]) <= 4


def test_cli_optimize_compare_and_pareto(tmp_path: Path, capsys) -> None:
    """Test airel optimize compare and pareto inspect result files."""
    res_file = _create_temp_result_file(tmp_path)

    code_comp = main(["optimize", "compare", str(res_file)])
    assert code_comp == 0
    out_comp = capsys.readouterr().out
    assert "Baseline vs Candidate Comparison" in out_comp

    code_par = main(["optimize", "pareto", str(res_file)])
    assert code_par == 0
    out_par = capsys.readouterr().out
    assert "Pareto Frontier Solutions" in out_par


def test_cli_optimize_validate_and_deploy(tmp_path: Path, capsys) -> None:
    """Test airel optimize validate and deploy subcommands."""
    res_file = _create_temp_result_file(tmp_path)

    code_val = main(["optimize", "validate", str(res_file)])
    assert code_val == 0
    out_val = capsys.readouterr().out
    assert "Validation PASSED" in out_val

    code_dep = main(
        [
            "optimize",
            "deploy",
            str(res_file),
            "--strategy",
            "canary",
            "--percentage",
            "10.0",
        ]
    )
    assert code_dep == 0
    out_dep = capsys.readouterr().out
    assert "Deployed candidate" in out_dep


def test_cli_optimize_budget_and_status(tmp_path: Path, capsys) -> None:
    """Test airel optimize budget and status subcommands."""
    res_file = _create_temp_result_file(tmp_path)

    code_bud = main(["optimize", "budget", str(res_file)])
    assert code_bud == 0
    out_bud = capsys.readouterr().out
    assert "Budget Consumption" in out_bud

    code_stat = main(["optimize", "status", str(res_file)])
    assert code_stat == 0
    out_stat = capsys.readouterr().out
    assert "Optimization Status" in out_stat
