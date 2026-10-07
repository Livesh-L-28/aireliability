"""Unit tests for Phase 36 serialization round-trips and edge cases."""

from __future__ import annotations

from pathlib import Path

from aireliability.core.models import FailureReport
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
    TestProvenance,
    TestQualityScore,
)
from aireliability.generation.serialization import (
    export_junit_xml,
    export_markdown_report,
    export_tests_csv,
    export_tests_json,
    export_tests_jsonl,
    import_tests_json,
    import_tests_jsonl,
)


def _make_sample_test(test_id: str = "t_ser") -> GeneratedTest:
    prov = TestProvenance(
        source_type=GenerationSourceType.FAILURE_REPORT,
        source_id="f_ser",
        source_failure_id="f_ser",
        deterministic_seed=42,
    )
    score = TestQualityScore(total_score=0.92)
    return GeneratedTest(
        test_id=test_id,
        name=f"test_{test_id}",
        strategy=GenerationStrategy.FAILURE_DRIVEN,
        input="Sample serialization query",
        expected_output="Sample output",
        expected_criteria=["criteria A", "criteria B"],
        reference_answer="Sample output",
        has_ground_truth=True,
        provenance=prov,
        quality_score=score,
    )


def test_json_and_jsonl_round_trips(tmp_path: Path) -> None:
    """Verify lossless serialization and deserialization across JSON and JSONL."""
    t1 = _make_sample_test("t1")
    t2 = _make_sample_test("t2")

    # 1. JSON
    json_path = tmp_path / "tests.json"
    export_tests_json([t1, t2], json_path)
    loaded_json = import_tests_json(json_path)

    assert len(loaded_json) == 2
    assert loaded_json[0].test_id == "t1"
    assert loaded_json[0].fingerprint == t1.fingerprint
    assert loaded_json[0].provenance.source_id == "f_ser"
    assert loaded_json[0].quality_score.total_score == 0.92

    # 2. JSONL
    jsonl_path = tmp_path / "tests.jsonl"
    export_tests_jsonl([t1, t2], jsonl_path)
    loaded_jsonl = import_tests_jsonl(jsonl_path)

    assert len(loaded_jsonl) == 2
    assert loaded_jsonl[1].test_id == "t2"


def test_csv_markdown_and_junit_exports() -> None:
    """Verify CSV, Markdown, and JUnit XML report outputs."""
    t = _make_sample_test("t_rep")

    # CSV
    csv_str = export_tests_csv([t])
    assert "test_id,name,strategy" in csv_str
    assert "t_rep" in csv_str

    # JUnit XML
    junit_str = export_junit_xml([t])
    assert "<testsuite" in junit_str
    assert 'name="test_t_rep"' in junit_str

    # Markdown
    engine = TestGenerationEngine()
    res = engine.generate(TestGenerationRequest(sources=[]))
    md_str = export_markdown_report(res)
    assert "# Automated AI Test Generation Report" in md_str


def test_edge_case_zero_failures() -> None:
    """Verify graceful handling when zero evidence sources are provided."""
    engine = TestGenerationEngine()
    req = TestGenerationRequest(sources=[])
    res = engine.generate(req)

    # Defaults to core synthetic edge/adversarial strategies
    assert res.total_generated > 0
    assert res.total_rejected == 0
    assert len(res.errors) == 0


def test_edge_case_duplicate_and_many_failures() -> None:
    """Verify engine handles batches with hundreds of duplicate failures."""
    f = FailureReport(
        failure_id="f_batch",
        trace_id="tr_batch",
        category="output_hallucination",
        message="hallucination error",
    )
    many_failures = [f for _ in range(50)]

    engine = TestGenerationEngine()
    config = TestGenerationConfig(max_candidates=10)
    req = TestGenerationRequest(
        sources=many_failures,
        strategies=[GenerationStrategy.FAILURE_DRIVEN],
        config=config,
    )
    res = engine.generate(req)

    # Deduplication and candidate limit prevent explosion
    assert res.total_validated <= 10
    assert res.duplicate_count >= 1


def test_edge_case_seeded_reproducibility() -> None:
    """Verify identical deterministic seeds produce identical fingerprints and outputs."""
    fail = FailureReport(
        failure_id="f_seed",
        trace_id="tr_seed",
        category="tool_failure",
        message="tool execution failed",
    )
    engine = TestGenerationEngine()

    req1 = TestGenerationRequest(
        sources=[fail],
        strategies=[GenerationStrategy.FAILURE_DRIVEN],
        config=TestGenerationConfig(deterministic_seed=123),
    )
    req2 = TestGenerationRequest(
        sources=[fail],
        strategies=[GenerationStrategy.FAILURE_DRIVEN],
        config=TestGenerationConfig(deterministic_seed=123),
    )

    res1 = engine.generate(req1)
    res2 = engine.generate(req2)

    assert len(res1.validated_tests) == len(res2.validated_tests)
    assert res1.validated_tests[0].fingerprint == res2.validated_tests[0].fingerprint
