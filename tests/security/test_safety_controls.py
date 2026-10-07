"""Safety control, hard veto gate, and non-compensatory scoring tests."""

from __future__ import annotations

from aireliability.safety.engine import SafetyEngine
from aireliability.safety.models import (
    SafetyCampaign,
    SafetyCategory,
    SafetyFinding,
    SafetyInput,
    SafetyRisk,
    SafetySeverity,
    SafetyStrategy,
    SafetyTarget,
    SafetyTest,
    SafetyVerdict,
)
from aireliability.safety.scorer import SafetyScorer


def _make_safety_test(category: SafetyCategory, name: str = "test") -> SafetyTest:
    target = SafetyTarget(target_id="target_llm")
    inp = SafetyInput(
        content="probe content",
        category=category,
        strategy=SafetyStrategy.TEMPLATE,
    )
    return SafetyTest(
        category=category,
        strategy=SafetyStrategy.TEMPLATE,
        target=target,
        safety_input=inp,
        metadata={"name": name},
    )


def test_critical_safety_finding_triggers_hard_veto():
    """Verify that even a single CRITICAL finding triggers hard veto and caps reliability."""
    scorer = SafetyScorer()

    test1 = _make_safety_test(SafetyCategory.INSTRUCTION_BOUNDARY, "Injection Test")
    test2 = _make_safety_test(SafetyCategory.UNSAFE_REQUEST, "Normal Test 1")
    test3 = _make_safety_test(SafetyCategory.PRIVACY_PROTECTION, "Normal Test 2")

    # 1 critical finding out of 3 tests
    finding = SafetyFinding(
        test_id=test1.test_id,
        category=SafetyCategory.INSTRUCTION_BOUNDARY,
        risk_dimension=SafetyRisk.SECURITY,
        severity=SafetySeverity.CRITICAL,
        verdict=SafetyVerdict.UNSAFE,
        message="Critical instruction boundary bypass detected.",
    )

    score, coverage = scorer.compute_score([test1, test2, test3], [finding])

    # Base safety would normally be 2/3 = 0.67, but hard veto must cap it to <= 0.30
    assert score.hard_veto_applied is True
    assert score.safety_score <= 0.30
    assert score.reliability_cap <= 0.30
    assert score.risk_score >= 0.70
    assert score.severity_max == SafetySeverity.CRITICAL


def test_critical_safety_cannot_be_masked_by_averaging_or_weights():
    """Verify high quantity of benign tests cannot dilute or mask a CRITICAL safety finding."""
    scorer = SafetyScorer()

    # 100 safe tests
    tests = [
        _make_safety_test(SafetyCategory.UNSAFE_REQUEST, f"Safe Test {i}")
        for i in range(100)
    ]
    # 1 critical finding
    critical_test = _make_safety_test(
        SafetyCategory.PRIVACY_PROTECTION, "Vulnerable Test"
    )
    tests.append(critical_test)

    finding = SafetyFinding(
        test_id=critical_test.test_id,
        category=SafetyCategory.PRIVACY_PROTECTION,
        risk_dimension=SafetyRisk.PRIVACY,
        severity=SafetySeverity.CRITICAL,
        verdict=SafetyVerdict.UNSAFE,
        message="PII leakage observed.",
    )

    score, _ = scorer.compute_score(tests, [finding])

    # Even though 100/101 tests passed (>99%), safety_score CANNOT exceed 0.30 due to hard veto
    assert score.hard_veto_applied is True
    assert score.safety_score <= 0.30
    assert score.reliability_cap <= 0.30


def test_safety_campaign_controlled_execution_and_evidence():
    """Verify safety campaign executes in controlled manner and records verifiable evidence."""
    engine = SafetyEngine()
    target = SafetyTarget(target_id="test_llm_agent", name="Protected Agent")
    campaign = SafetyCampaign(target=target, max_tests=6)

    result = engine.run_campaign(campaign)

    assert result.campaign_id == campaign.campaign_id
    assert result.total_tests <= 6
    assert result.score is not None
    assert result.coverage is not None

    # Ensure evidence is properly attached to findings
    for finding in result.findings:
        assert finding.test_id is not None
        assert finding.severity in (
            SafetySeverity.INFO,
            SafetySeverity.LOW,
            SafetySeverity.MEDIUM,
            SafetySeverity.HIGH,
            SafetySeverity.CRITICAL,
        )
