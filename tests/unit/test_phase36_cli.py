"""Unit tests for Phase 36 CLI commands (generate and test-generation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aireliability.cli import main
from aireliability.core.models import FailureReport
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.generation.serialization import export_tests_json


def test_cli_generate_tests_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify `airel generate tests --dry-run` outputs test generation summary."""
    ret = main(["generate", "tests", "What is the capital of Spain?", "--dry-run"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "=== Test Generation Results" in captured
    assert "[DRY RUN]" in captured


def test_cli_generate_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify `airel generate adversarial --json` prints valid JSON."""
    ret = main(
        ["generate", "adversarial", "Bypass prompt", "--json", "--max-candidates", "2"]
    )
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "request_id" in data
    assert "validated_tests" in data


def test_cli_generate_from_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify `airel generate from-failure` with FailureReport JSON input."""
    fail = FailureReport(
        failure_id="fail_cli_1",
        trace_id="tr_cli_1",
        category="security",
        type="injection",
        message="SQL injection vulnerability detected",
    )
    fail_file = tmp_path / "failure.json"
    fail_file.write_text(fail.model_dump_json(), encoding="utf-8")

    out_file = tmp_path / "generated.json"
    ret = main(
        [
            "generate",
            "from-failure",
            str(fail_file),
            "-o",
            str(out_file),
            "--format",
            "json",
        ]
    )
    assert ret == 0
    assert out_file.exists()
    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert "validated_tests" in content
    assert content["total_validated"] >= 1


def test_cli_generate_mutations(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify `airel generate mutations`."""
    ret = main(
        ["generate", "mutations", "Summarize this report", "--mutation-limit", "3"]
    )
    assert ret == 0
    captured = capsys.readouterr().out
    assert "mutations" in captured


def test_cli_test_generation_inspect_and_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify `airel test-generation inspect` and `validate`."""
    fail = FailureReport(
        failure_id="fail_insp",
        trace_id="tr_insp",
        category="rag",
        message="rag grounding error",
    )
    from aireliability.generation.engine import TestGenerationEngine
    from aireliability.generation.models import TestGenerationRequest

    engine = TestGenerationEngine()
    res = engine.generate(TestGenerationRequest(sources=[fail]))

    test_file = tmp_path / "tests.json"
    export_tests_json(res.validated_tests, test_file)

    # 1. inspect
    ret_insp = main(["test-generation", "inspect", str(test_file)])
    assert ret_insp == 0
    out_insp = capsys.readouterr().out
    assert "Inspecting" in out_insp

    # 2. validate
    ret_val = main(["test-generation", "validate", str(test_file)])
    assert ret_val == 0
    out_val = capsys.readouterr().out
    assert "VALIDATED" in out_val


def test_cli_test_generation_promote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify `airel test-generation promote`."""
    fail = FailureReport(
        failure_id="fail_prom",
        trace_id="tr_prom",
        category="rag",
        message="rag error",
    )
    from aireliability.generation.engine import TestGenerationEngine
    from aireliability.generation.models import TestGenerationRequest

    engine = TestGenerationEngine()
    res = engine.generate(TestGenerationRequest(sources=[fail]))

    test_file = tmp_path / "tests.json"
    export_tests_json(res.validated_tests, test_file)

    ds_file = tmp_path / "golden_ds.json"
    ds = EvaluationDataset(name="Golden", id="golden_1")
    ds_file.write_text(ds.model_dump_json(), encoding="utf-8")

    ret_prom = main(
        ["test-generation", "promote", str(test_file), "--dataset", str(ds_file)]
    )
    assert ret_prom == 0
    out_prom = capsys.readouterr().out
    assert "Successfully promoted" in out_prom
