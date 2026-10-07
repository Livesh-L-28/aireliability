"""Unit tests for TestValidator and TestQualityScorer (Phase 36)."""

from __future__ import annotations

from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    TestGenerationStatus,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
)
from aireliability.generation.scoring import TestQualityScorer
from aireliability.generation.validators import TestValidator


def test_validator_passes_valid_test() -> None:
    """Verify that a well-formed test candidate transitions to VALIDATED."""
    prov = TestProvenance(
        source_type=GenerationSourceType.FAILURE_REPORT,
        source_id="fail_1",
        source_failure_id="fail_1",
    )
    test = GeneratedTest(
        test_id="test_good",
        name="good_test",
        input="Valid input query",
        expected_criteria=["response must be non-empty"],
        provenance=prov,
    )
    validator = TestValidator()
    validated = validator.validate(test)
    assert validated.status == TestGenerationStatus.VALIDATED
    assert validated.fingerprint != ""


def test_validator_rejects_missing_assertions() -> None:
    """Verify rejection when no evaluable targets exist."""
    prov = TestProvenance(source_type=GenerationSourceType.SYNTHETIC, source_id="s1")
    test = GeneratedTest(
        test_id="t_empty",
        name="test_no_assertions",
        input="some input",
        expected_output=None,
        expected_criteria=[],
        provenance=prov,
    )
    validator = TestValidator()
    val = validator.validate(test)
    assert val.status == TestGenerationStatus.REJECTED
    assert any("no verifiable assertions" in r for r in val.validation_reasons)


def test_validator_rejects_conflicting_criteria() -> None:
    """Verify detection of conflicting criteria."""
    prov = TestProvenance(source_type=GenerationSourceType.SYNTHETIC, source_id="s1")
    test = GeneratedTest(
        test_id="t_conflict",
        name="test_conflict",
        input="query",
        expected_criteria=["must output json", "must not output json"],
        provenance=prov,
    )
    validator = TestValidator()
    val = validator.validate(test)
    assert val.status == TestGenerationStatus.REJECTED
    assert any("Conflicting criteria" in r for r in val.validation_reasons)


def test_validator_detects_unredacted_secrets() -> None:
    """Verify that unredacted API key patterns trigger safety rejection."""
    prov = TestProvenance(source_type=GenerationSourceType.SYNTHETIC, source_id="s1")
    test = GeneratedTest(
        test_id="t_secret",
        name="test_leak",
        input="Use key sk-abcdef12345678901234567890 to call API",
        expected_criteria=["must authenticate"],
        provenance=prov,
    )
    validator = TestValidator(enforce_safety=True)
    val = validator.validate(test)
    assert val.status == TestGenerationStatus.REJECTED
    assert any("secret pattern" in r for r in val.validation_reasons)


def test_validator_flags_high_risk_for_review() -> None:
    """Verify that high-risk tests transition to NEEDS_REVIEW."""
    prov = TestProvenance(source_type=GenerationSourceType.SYNTHETIC, source_id="s1")
    test = GeneratedTest(
        test_id="t_risk",
        name="test_high_risk",
        input="Safe query with high risk classification",
        expected_criteria=["criteria A"],
        risk_level=TestRiskLevel.HIGH,
        provenance=prov,
    )
    validator = TestValidator(review_high_risk=True)
    val = validator.validate(test)
    assert val.status == TestGenerationStatus.NEEDS_REVIEW


def test_validator_null_input_tag_handling() -> None:
    """Verify null input without tag is rejected, but with null_input tag passes."""
    prov = TestProvenance(source_type=GenerationSourceType.SYNTHETIC, source_id="s1")
    t_bad = GeneratedTest(
        test_id="t_null_bad",
        name="t_null",
        input=None,
        expected_criteria=["handle null"],
        provenance=prov,
    )
    val_bad = TestValidator().validate(t_bad)
    assert val_bad.status == TestGenerationStatus.REJECTED

    t_good = GeneratedTest(
        test_id="t_null_good",
        name="t_null",
        input=None,
        expected_criteria=["handle null"],
        tags=["null_input", "edge_case"],
        provenance=prov,
    )
    val_good = TestValidator().validate(t_good)
    assert val_good.status == TestGenerationStatus.VALIDATED


def test_quality_scorer_dimensions() -> None:
    """Verify quality scoring across dimensions and composite calculation."""
    prov = TestProvenance(
        source_type=GenerationSourceType.FAILURE_REPORT,
        source_id="fail_1",
        source_failure_id="fail_1",
        deterministic_seed=42,
    )
    test = GeneratedTest(
        test_id="test_score",
        name="score_test",
        input="What is the total revenue?",
        expected_output="10 million",
        expected_criteria=["must state 10 million", "must format as USD currency"],
        reference_answer="10 million",
        has_ground_truth=True,
        context="Company revenue is 10 million USD.",
        provenance=prov,
        confidence=0.95,
        risk_level=TestRiskLevel.MEDIUM,
        priority=TestPriority.HIGH,
    )
    scorer = TestQualityScorer()
    score = scorer.score(test)

    assert 0.0 <= score.total_score <= 1.0
    assert score.provenance_strength == 1.0
    assert score.failure_relevance == 1.0
    assert score.correctness_confidence == 1.0
    assert score.reproducibility_score == 1.0
    assert "Quality score" in score.explanation
    assert len(score.factors) > 5
