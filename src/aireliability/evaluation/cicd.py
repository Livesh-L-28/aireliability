"""CI/CD integration utilities, GitHub Actions workflow generation, and PR comment reporting."""

from __future__ import annotations

from pathlib import Path

from aireliability.evaluation.governance.gates import GateResult
from aireliability.evaluation.governance.reporting import EvaluationReporter
from aireliability.evaluation.governance.scoring import UnifiedReliabilityScore
from aireliability.evaluation.models import EvaluationReport

DEFAULT_WORKFLOW_TEMPLATE = """name: AI Evaluation & Reliability Gate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: write
  checks: write

jobs:
  evaluate:
    name: AI Reliability Evaluation
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install AI Reliability Framework
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"

      - name: Execute Evaluation Suite
        run: |
          mkdir -p artifacts/evaluation
          airel evaluate run \\
            --output artifacts/evaluation/report.json \\
            --format json

      - name: Evaluate Release Gate Policy
        id: release_gate
        run: |
          airel gate \\
            --report artifacts/evaluation/report.json \\
            --min-score 0.85

      - name: Generate Multi-Format Reports
        if: always()
        run: |
          airel report --report artifacts/evaluation/report.json --format markdown --output artifacts/evaluation/summary.md
          airel report --report artifacts/evaluation/report.json --format html --output artifacts/evaluation/dashboard.html
          airel report --report artifacts/evaluation/report.json --format junit --output artifacts/evaluation/junit.xml
          airel report --report artifacts/evaluation/report.json --format pr-comment --output artifacts/evaluation/pr_comment.md

      - name: Publish Test Summary
        if: always()
        run: |
          if [ -f artifacts/evaluation/summary.md ]; then
            cat artifacts/evaluation/summary.md >> $GITHUB_STEP_SUMMARY
          fi

      - name: Upload Evaluation Artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-evaluation-artifacts
          path: artifacts/evaluation/
"""


def generate_github_actions_workflow() -> str:
    """Return production-ready GitHub Actions workflow YAML string."""
    return DEFAULT_WORKFLOW_TEMPLATE.strip() + "\n"


def write_github_workflow_template(
    target_path: Path | str = ".github/workflows/ai-eval.yml",
    overwrite: bool = False,
) -> Path:
    """Write GitHub Actions evaluation workflow template to target directory."""
    path = Path(target_path)
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_github_actions_workflow(), encoding="utf-8")
    return path


def generate_pr_comment(
    report: EvaluationReport,
    score: UnifiedReliabilityScore | None = None,
    gate: GateResult | None = None,
    baseline_score: float | None = None,
) -> str:
    """Generate high-impact GitHub pull request comment."""
    return EvaluationReporter.render_pr_comment(
        report=report,
        score=score,
        gate=gate,
        baseline_score=baseline_score,
    )
