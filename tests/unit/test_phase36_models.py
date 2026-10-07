"""Unit tests for Phase 36 Automated AI Test Generation data models."""

from __future__ import annotations

import pytest

from aireliability.core.models import RegressionTest, TestCase
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
    TestGenerationResult,
    TestGenerationStatus,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
)


def test_generation_strategy_enums() -> None:
    """Verify all 14 generation strategies are defined."""
    assert len(GenerationStrategy) == 14
    expected = {
        "failure_driven",
        "regression_driven",
        "graph_driven",
        "pattern_driven",
        "incident_driven",
        "production_trace_driven",
        "edge_case",
        "mutation_based",
        "adversarial",
        "safety_security_privacy",
        "rag_focused",
        "agent_trajectory",
        "robustness",
        "consistency",
    }
    actual = {s.value for s in GenerationStrategy}
    assert actual == expected


def test_provenance_model() -> None:
    """Verify TestProvenance model properties and immutability."""
    prov = TestProvenance(
        source_type=GenerationSourceType.FAILURE_REPORT,
        source_id="fail_123",
        source_failure_id="fail_123",
        generator_name="FailureTestGenerator",
        rationale="Guarding against output hallucination",
    )
    assert prov.source_id == "fail_123"
    assert prov.source_type == GenerationSourceType.FAILURE_REPORT
    assert prov.generator_version == "0.5.0"
    with pytest.raises((ValueError, TypeError)):
        prov.source_id = "fail_456"  # type: ignore[misc]


def test_generated_test_lifecycle_transitions() -> None:
    """Verify valid and invalid state transitions for GeneratedTest."""
    prov = TestProvenance(
        source_type=GenerationSourceType.SYNTHETIC,
        source_id="test_src_1",
    )
    test = GeneratedTest(
        name="test_case_1",
        input="Hello world",
        expected_criteria=["must respond politely"],
        provenance=prov,
    )
    assert test.status == TestGenerationStatus.CANDIDATE

    # CANDIDATE -> VALIDATING
    t_val = test.transition_to(TestGenerationStatus.VALIDATING, "Beginning validation")
    assert t_val.status == TestGenerationStatus.VALIDATING
    assert "Beginning validation" in t_val.validation_reasons

    # VALIDATING -> VALIDATED
    t_validated = t_val.transition_to(
        TestGenerationStatus.VALIDATED, "Passed all checks"
    )
    assert t_validated.status == TestGenerationStatus.VALIDATED

    # VALIDATED -> PROMOTED
    t_prom = t_validated.transition_to(
        TestGenerationStatus.PROMOTED, "Promoted to golden dataset"
    )
    assert t_prom.status == TestGenerationStatus.PROMOTED

    # PROMOTED is terminal
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        t_prom.transition_to(TestGenerationStatus.VALIDATED)

    # REJECTED is terminal
    t_rej = test.transition_to(TestGenerationStatus.REJECTED, "Fatal error")
    assert t_rej.status == TestGenerationStatus.REJECTED
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        t_rej.transition_to(TestGenerationStatus.PROMOTED)


def test_generated_test_ground_truth_flag() -> None:
    """Verify explicit ground truth handling."""
    prov = TestProvenance(source_type=GenerationSourceType.SYNTHETIC, source_id="s1")
    # No reference answer
    t1 = GeneratedTest(
        name="t1",
        input="q",
        expected_criteria=["c"],
        provenance=prov,
    )
    assert not t1.has_ground_truth
    assert t1.reference_answer is None

    # Reference answer provided sets ground truth True
    t2 = GeneratedTest(
        name="t2",
        input="q",
        expected_criteria=["c"],
        reference_answer="truth answer",
        provenance=prov,
    )
    assert t2.has_ground_truth
    assert t2.reference_answer == "truth answer"


def test_conversion_to_platform_models() -> None:
    """Verify conversion to TestCase and RegressionTest."""
    prov = TestProvenance(
        source_type=GenerationSourceType.FAILURE_REPORT,
        source_id="fail_abc",
        source_failure_id="fail_abc",
    )
    gen_test = GeneratedTest(
        name="guard_fail_abc",
        strategy=GenerationStrategy.FAILURE_DRIVEN,
        input="Test query input",
        expected_criteria=["must pass"],
        provenance=prov,
        risk_level=TestRiskLevel.HIGH,
        priority=TestPriority.CRITICAL,
    )

    tc = gen_test.to_test_case()
    assert isinstance(tc, TestCase)
    assert tc.input == "Test query input"
    assert "generated" in tc.tags
    assert "strategy:failure_driven" in tc.tags
    assert tc.metadata["generated_test_id"] == gen_test.test_id
    assert tc.metadata["risk_level"] == "high"

    reg = gen_test.to_regression_test()
    assert isinstance(reg, RegressionTest)
    assert reg.source_failure_id == "fail_abc"
    assert reg.name == f"reg_{gen_test.name}"
    assert "regression" in reg.test_case.tags


def test_config_defaults_and_validation() -> None:
    """Verify default generation config values."""
    config = TestGenerationConfig()
    assert config.max_candidates == 100
    assert config.min_quality_threshold == 0.50
    assert config.promotion_threshold == 0.75
    assert not config.auto_promote  # Conservative default
    assert config.deterministic_seed == 42


def test_generation_request_and_result() -> None:
    """Verify request and result data structures."""
    req = TestGenerationRequest(
        sources=["hello"],
        strategies=[GenerationStrategy.EDGE_CASE],
    )
    assert len(req.sources) == 1
    assert req.strategies == [GenerationStrategy.EDGE_CASE]

    res = TestGenerationResult(
        total_generated=10,
        total_validated=8,
        total_rejected=2,
    )
    assert res.total_generated == 10
    assert res.generator_version == "0.5.0"
