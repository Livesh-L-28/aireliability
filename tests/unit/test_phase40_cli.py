"""Unit tests for Phase 40 CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aireliability.cli import main


def test_cli_version(capsys):
    """Verify airel --version prints 1.4.0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "1.4.0" in captured.out


@pytest.mark.parametrize(
    "action",
    [
        "evaluate",
        "analyze",
        "trajectory",
        "plan",
        "tools",
        "loops",
        "retries",
        "memory",
        "state",
        "goals",
        "handoffs",
        "failures",
        "drift",
        "security",
        "regression",
        "diagnose",
        "tests",
        "heal",
        "optimize",
        "report",
        "inspect",
    ],
)
def test_cli_agent_subcommands_terminal(action: str, capsys):
    """Verify all 21 agent subcommands execute with exit code 0."""
    code = main(["agent", action])
    assert code == 0
    captured = capsys.readouterr()
    assert len(captured.out) > 0


@pytest.mark.parametrize(
    "action",
    [
        "evaluate",
        "analyze",
        "trajectory",
        "plan",
        "tools",
        "loops",
        "retries",
        "goals",
        "diagnose",
        "tests",
        "heal",
        "optimize",
        "inspect",
    ],
)
def test_cli_agent_subcommands_json(action: str, capsys):
    """Verify --json output is valid JSON for agent subcommands."""
    code = main(["agent", action, "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data is not None


def test_cli_agent_report_markdown(tmp_path: Path, capsys):
    """Verify markdown report generation and file export."""
    out_file = tmp_path / "report.md"
    code = main(["agent", "report", "--format", "markdown", "--output", str(out_file)])
    assert code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "# Agent Reliability Report" in content
