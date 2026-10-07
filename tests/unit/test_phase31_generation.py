"""Unit tests for Phase 31 Generation checks and semantic evaluators."""

from __future__ import annotations

from uuid import uuid4

from aireliability.core.models import ExecutionTrace
from aireliability.evaluation.generation.checks import (
    CitationPresence,
    CitationValidation,
    FormatValidation,
    JsonValid,
    RegexMatch,
    RequiredFields,
    TypeValidation,
)
from aireliability.evaluation.generation.evaluators import (
    CoherenceEvaluator,
    CompletenessEvaluator,
    CorrectnessEvaluator,
    HelpfulnessEvaluator,
    InstructionFollowingEvaluator,
    RelevanceEvaluator,
)
from aireliability.evaluation.semantic.mock_judge import MockSemanticJudge


def _make_trace(output: str | dict | list | int | float | None) -> ExecutionTrace:
    return ExecutionTrace(
        test_case_id=uuid4(),
        input="Tell me about Paris",
        output=output,
        latency_ms=45.0,
        token_count=100,
        cost_usd=0.002,
    )


def test_regex_match():
    trace_pass = _make_trace("Order status is COMPLETED successfully.")
    trace_fail = _make_trace("Order status is PENDING.")

    check = RegexMatch(r"status is (COMPLETED|SHIPPED)")
    res_pass = check.evaluate(trace_pass)
    assert res_pass.passed is True
    assert res_pass.score == 1.0

    res_fail = check.evaluate(trace_fail)
    assert res_fail.passed is False
    assert res_fail.score == 0.0


def test_json_valid():
    trace_json_str = _make_trace('{"city": "Paris", "population": 2161000}')
    trace_dict = _make_trace({"city": "Paris"})
    trace_invalid = _make_trace("Not a valid json {broken")

    check = JsonValid()
    assert check.evaluate(trace_json_str).passed is True
    assert check.evaluate(trace_dict).passed is True
    assert check.evaluate(trace_invalid).passed is False


def test_required_fields():
    trace_valid = _make_trace('{"name": "Alice", "role": "admin", "id": 1}')
    trace_missing = _make_trace('{"name": "Alice"}')
    trace_not_dict = _make_trace("plain text")

    check = RequiredFields(["name", "role"])
    assert check.evaluate(trace_valid).passed is True
    assert check.evaluate(trace_missing).passed is False
    assert "role" in check.evaluate(trace_missing).evidence.get("missing", [])
    assert check.evaluate(trace_not_dict).passed is False


def test_type_validation():
    check_dict = TypeValidation(expected_types={"name": str, "age": int})
    trace_valid = _make_trace({"name": "Bob", "age": 30})
    trace_invalid_type = _make_trace({"name": "Bob", "age": "thirty"})
    trace_malformed = _make_trace("not dict")

    assert check_dict.evaluate(trace_valid).passed is True
    assert check_dict.evaluate(trace_invalid_type).passed is False
    assert check_dict.evaluate(trace_malformed).passed is False

    # Also test single standard type
    check_int = TypeValidation(expected_types=int)
    assert check_int.evaluate(_make_trace(42)).passed is True
    assert check_int.evaluate(_make_trace("hello")).passed is False


def test_format_validation():
    check_email = FormatValidation(format_name="email")
    assert check_email.evaluate(_make_trace("user@example.com")).passed is True
    assert check_email.evaluate(_make_trace("user@@example..com")).passed is False

    check_url = FormatValidation(format_name="url")
    assert (
        check_url.evaluate(_make_trace("https://aireliability.org/docs")).passed is True
    )
    assert check_url.evaluate(_make_trace("invalid url")).passed is False

    check_uuid = FormatValidation(format_name="uuid")
    assert check_uuid.evaluate(_make_trace(str(uuid4()))).passed is True
    assert check_uuid.evaluate(_make_trace("123-abc")).passed is False

    check_iso = FormatValidation(format_name="datetime_iso")
    assert check_iso.evaluate(_make_trace("2026-10-06T06:00:00Z")).passed is True
    assert check_iso.evaluate(_make_trace("yesterday")).passed is False


def test_citation_presence_and_validation():
    trace_with_citations = _make_trace(
        "According to source [1] and report [source_2], Paris is France's capital."
    )
    trace_no_citations = _make_trace("Paris is France's capital.")

    presence_check = CitationPresence(min_citations=2)
    assert presence_check.evaluate(trace_with_citations).passed is True
    assert presence_check.evaluate(trace_no_citations).passed is False

    # Validation against allowed whitelist
    val_check = CitationValidation(valid_sources=["1", "source_2"])
    assert val_check.evaluate(trace_with_citations).passed is True

    val_strict = CitationValidation(valid_sources=["verified_only"])
    assert val_strict.evaluate(trace_with_citations).passed is False


def test_generative_evaluators_with_mock_judge():
    passing_judge = MockSemanticJudge(default_score=0.95, default_passed=True)
    failing_judge = MockSemanticJudge(default_score=0.40, default_passed=False)

    trace = _make_trace("Paris is the capital and largest city of France.")

    # Correctness
    corr_eval = CorrectnessEvaluator(
        reference="Capital of France is Paris.", judge=passing_judge
    )
    res = corr_eval.evaluate(trace)
    assert res.passed is True
    assert res.score >= 0.8

    # Relevance
    rel_eval = RelevanceEvaluator(judge=passing_judge)
    assert rel_eval.evaluate(trace).passed is True

    # Completeness
    comp_eval = CompletenessEvaluator(
        required_topics=["history", "geography"], judge=failing_judge
    )
    res_fail = comp_eval.evaluate(trace)
    assert res_fail.passed is False
    assert res_fail.score < 0.75

    # Coherence
    coh_eval = CoherenceEvaluator(judge=passing_judge)
    assert coh_eval.evaluate(trace).passed is True

    # Helpfulness
    help_eval = HelpfulnessEvaluator(judge=passing_judge)
    assert help_eval.evaluate(trace).passed is True

    # Instruction Following
    inst_eval = InstructionFollowingEvaluator(judge=passing_judge)
    assert inst_eval.evaluate(trace).passed is True
