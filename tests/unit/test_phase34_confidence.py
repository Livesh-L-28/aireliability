"""Unit tests for Phase 34 deterministic ConfidenceEngine."""

from __future__ import annotations

from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.models import ConfidenceLevel


def test_confidence_high_certainty() -> None:
    conf = ConfidenceEngine.calculate(
        evidence_count=10,
        sample_size=100,
        agreement_rate=0.95,
        data_completeness=1.0,
    )
    assert conf.score >= 0.85
    assert conf.level == ConfidenceLevel.VERY_HIGH
    assert "evidence_factor" in conf.factors
    assert "agreement_factor" in conf.factors
    assert "completeness_factor" in conf.factors
    assert conf.evidence_count == 10
    assert conf.sample_size == 100


def test_confidence_low_evidence() -> None:
    conf = ConfidenceEngine.calculate(
        evidence_count=1,
        sample_size=2,
        agreement_rate=0.50,
        data_completeness=0.5,
    )
    assert conf.score < 0.70
    assert conf.level in (
        ConfidenceLevel.LOW,
        ConfidenceLevel.VERY_LOW,
        ConfidenceLevel.MEDIUM,
    )


def test_confidence_zero_sample_size() -> None:
    conf = ConfidenceEngine.calculate(
        evidence_count=0,
        sample_size=0,
        agreement_rate=0.0,
        data_completeness=0.0,
    )
    assert 0.0 <= conf.score <= 1.0
    assert conf.level in (ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW)


def test_confidence_categorical_levels() -> None:
    assert ConfidenceEngine.score_to_level(0.95) == ConfidenceLevel.VERY_HIGH
    assert ConfidenceEngine.score_to_level(0.85) == ConfidenceLevel.VERY_HIGH
    assert ConfidenceEngine.score_to_level(0.75) == ConfidenceLevel.HIGH
    assert ConfidenceEngine.score_to_level(0.55) == ConfidenceLevel.MEDIUM
    assert ConfidenceEngine.score_to_level(0.35) == ConfidenceLevel.LOW
    assert ConfidenceEngine.score_to_level(0.15) == ConfidenceLevel.VERY_LOW


def test_confidence_factors_audit() -> None:
    conf = ConfidenceEngine.calculate(
        evidence_count=4,
        sample_size=10,
        agreement_rate=0.8,
        data_completeness=0.9,
    )
    assert "sample_factor" in conf.factors
    assert 0.0 <= conf.factors["evidence_factor"] <= 1.0
    assert len(conf.rationale) > 0
