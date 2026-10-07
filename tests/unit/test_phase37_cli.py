"""Unit tests for Phase 37 CLI commands (airel heal *)."""

import json
from pathlib import Path

import pytest

from aireliability.cli import main


def test_cli_heal_plan_basic(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Test 'airel heal plan' outputs planned proposal."""
    out_file = tmp_path / "plan_out.json"
    exit_code = main(
        [
            "heal",
            "plan",
            "JSON formatting error in response",
            "--component",
            "system_prompt",
            "--output",
            str(out_file),
        ]
    )
    assert exit_code == 0
    assert out_file.exists()

    with open(out_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["repair_type"] == "prompt_repair"
    assert data["state"] == "PROPOSED"


def test_cli_heal_full_lifecycle_flow(tmp_path: Path) -> None:
    """Test full sequential lifecycle execution via CLI."""
    prop_file = tmp_path / "proposal.json"

    # 1. Plan
    assert (
        main(
            [
                "heal",
                "plan",
                "Missing retrieval evidence",
                "--type",
                "retrieval",
                "--output",
                str(prop_file),
            ]
        )
        == 0
    )

    # 2. Simulate
    assert main(["heal", "simulate", str(prop_file)]) == 0
    with open(prop_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["state"] in ("SIMULATED", "NEEDS_APPROVAL", "APPROVED")

    # 3. Approve
    assert main(["heal", "approve", str(prop_file), "--approver", "lead_dev"]) == 0
    with open(prop_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["state"] == "APPROVED"
    assert data["approval"]["approver"] == "lead_dev"

    # 4. Apply
    assert (
        main(
            [
                "heal",
                "apply",
                str(prop_file),
                "--strategy",
                "canary",
                "--percentage",
                "20",
            ]
        )
        == 0
    )
    with open(prop_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["state"] == "CANARY"
    assert data["rollout_state"]["active_percentage"] == 20.0

    # 5. Verify
    assert (
        main(
            [
                "heal",
                "verify",
                str(prop_file),
                "--samples",
                "25",
                "--error-rate",
                "0.01",
            ]
        )
        == 0
    )
    with open(prop_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["state"] == "VERIFIED"

    # 6. Promote
    assert (
        main(
            [
                "heal",
                "promote",
                str(prop_file),
                "--actor",
                "lead_dev",
                "--notes",
                "Production validated",
            ]
        )
        == 0
    )
    with open(prop_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["state"] == "PROMOTED"
    assert data["rollout_state"]["active_percentage"] == 100.0


def test_cli_heal_rollback(tmp_path: Path) -> None:
    """Test 'airel heal rollback' re-sets proposal to ROLLED_BACK."""
    prop_file = tmp_path / "rollback_proposal.json"
    main(
        [
            "heal",
            "plan",
            "Memory leak in agent",
            "--type",
            "agent",
            "--output",
            str(prop_file),
        ]
    )
    main(["heal", "approve", str(prop_file)])
    main(["heal", "apply", str(prop_file), "--strategy", "canary"])

    # Rollback
    exit_code = main(
        [
            "heal",
            "rollback",
            str(prop_file),
            "--reason",
            "Spike in errors",
            "--actor",
            "sre_engineer",
        ]
    )
    assert exit_code == 0
    with open(prop_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["state"] == "ROLLED_BACK"
    assert data["rollout_state"]["active_percentage"] == 0.0


def test_cli_heal_status(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """Test 'airel heal status' displays overview."""
    prop_file = tmp_path / "status_prop.json"
    main(["heal", "plan", "Agent stuck in loop", "--output", str(prop_file)])

    exit_code = main(["heal", "status", str(prop_file)])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Proposal Status:" in captured
    assert "Repair Type:" in captured
