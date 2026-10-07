"""Serialization and export/import utilities for generated tests and results."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from aireliability.generation.models import GeneratedTest, TestGenerationResult


def test_to_dict(test: GeneratedTest) -> dict[str, Any]:
    """Serialize a GeneratedTest to a dictionary."""
    return test.model_dump(mode="json")


def test_from_dict(data: dict[str, Any]) -> GeneratedTest:
    """Deserialize a dictionary into a GeneratedTest."""
    return GeneratedTest.model_validate(data)


def export_tests_json(
    tests: list[GeneratedTest], path: Path | str | None = None
) -> str:
    """Export list of tests as JSON string and optionally write to file."""
    data = [test_to_dict(t) for t in tests]
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    if path:
        Path(path).write_text(serialized, encoding="utf-8")
    return serialized


def import_tests_json(source: str | Path) -> list[GeneratedTest]:
    """Import tests from JSON string or file path."""
    content = (
        Path(source).read_text(encoding="utf-8")
        if isinstance(source, Path)
        or (isinstance(source, str) and Path(source).exists())
        else source
    )
    raw = json.loads(content)
    if isinstance(raw, dict):
        raw = [raw]
    return [test_from_dict(d) for d in raw]


def export_tests_jsonl(
    tests: list[GeneratedTest], path: Path | str | None = None
) -> str:
    """Export list of tests as JSONL string and optionally write to file."""
    lines = [json.dumps(test_to_dict(t), ensure_ascii=False) for t in tests]
    output = "\n".join(lines) + ("\n" if lines else "")
    if path:
        Path(path).write_text(output, encoding="utf-8")
    return output


def import_tests_jsonl(source: str | Path) -> list[GeneratedTest]:
    """Import tests from JSONL string or file path."""
    content = (
        Path(source).read_text(encoding="utf-8")
        if isinstance(source, Path)
        or (isinstance(source, str) and Path(source).exists())
        else source
    )
    tests = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            tests.append(test_from_dict(json.loads(line)))
    return tests


def export_tests_csv(tests: list[GeneratedTest], path: Path | str | None = None) -> str:
    """Export summary of tests to CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "test_id",
            "name",
            "strategy",
            "test_type",
            "status",
            "risk_level",
            "priority",
            "quality_score",
            "confidence",
            "has_ground_truth",
            "fingerprint",
        ]
    )
    for t in tests:
        q_score = t.quality_score.total_score if t.quality_score else ""
        writer.writerow(
            [
                t.test_id,
                t.name,
                t.strategy.value,
                t.test_type.value,
                t.status.value,
                t.risk_level.value,
                t.priority.value,
                q_score,
                t.confidence,
                t.has_ground_truth,
                t.fingerprint,
            ]
        )
    res = output.getvalue()
    if path:
        Path(path).write_text(res, encoding="utf-8")
    return res


def export_markdown_report(
    result: TestGenerationResult, path: Path | str | None = None
) -> str:
    """Generate Markdown report for a test generation run."""
    md = [
        "# Automated AI Test Generation Report",
        f"- **Request ID**: `{result.request_id}`",
        f"- **Timestamp**: `{result.timestamp.isoformat()}`",
        f"- **Duration**: `{result.duration_ms:.2f}ms`",
        f"- **Generator Version**: `{result.generator_version}`",
        "",
        "## Summary Metrics",
        "| Metric | Count |",
        "| :--- | :--- |",
        f"| **Total Candidates Generated** | {result.total_generated} |",
        f"| **Validated Candidates** | {result.total_validated} |",
        f"| **Rejected Candidates** | {result.total_rejected} |",
        f"| **Needs Review Candidates** | {len(result.needs_review_tests)} |",
        f"| **Promoted Tests** | {result.total_promoted} |",
        f"| **Duplicates Dropped** | {result.duplicate_count} |",
        "",
        "## Strategy Distribution",
    ]
    for strat, count in sorted(result.strategy_distribution.items()):
        md.append(f"- **{strat}**: {count}")

    md.extend(["", "## Validated Test Candidates"])
    if not result.validated_tests:
        md.append("_No tests passed validation._")
    else:
        for t in result.validated_tests[:10]:
            q_score = t.quality_score.total_score if t.quality_score else 0.0
            md.append(f"### `{t.name}` ({t.test_id})")
            md.append(
                f"- **Strategy**: `{t.strategy.value}` | **Type**: `{t.test_type.value}` | **Status**: `{t.status.value}`"
            )
            md.append(
                f"- **Quality**: `{q_score:.2f}` | **Risk**: `{t.risk_level.value}` | **Priority**: `{t.priority.value}`"
            )
            md.append(f"- **Input**: `{str(t.input)[:120]}`")
            if t.expected_criteria:
                md.append(f"- **Criteria**: {', '.join(t.expected_criteria)}")
            md.append("")

    res = "\n".join(md)
    if path:
        Path(path).write_text(res, encoding="utf-8")
    return res


def export_junit_xml(tests: list[GeneratedTest], path: Path | str | None = None) -> str:
    """Export validated tests as JUnit XML format."""
    total = len(tests)
    failures = sum(1 for t in tests if t.status.value == "rejected")
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="GeneratedAITests" tests="{total}" failures="{failures}" errors="0">',
    ]
    for t in tests:
        xml.append(
            f'  <testcase classname="{escape(t.strategy.value)}" name="{escape(t.name)}">'
        )
        if t.status.value == "rejected":
            reason = "; ".join(t.validation_reasons)
            xml.append(
                f'    <failure message="Validation Rejected">{escape(reason)}</failure>'
            )
        xml.append("  </testcase>")
    xml.append("</testsuite>")
    res = "\n".join(xml)
    if path:
        Path(path).write_text(res, encoding="utf-8")
    return res
