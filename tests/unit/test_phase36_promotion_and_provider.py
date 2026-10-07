"""Unit tests for TestPromotionManager and TestGenerationProvider (Phase 36)."""

from __future__ import annotations

import pytest

from aireliability.core.models import RegressionTest
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    TestGenerationStatus,
    TestProvenance,
    TestQualityScore,
    TestRiskLevel,
)
from aireliability.generation.promotion import TestPromotionManager
from aireliability.generation.provider import (
    DeterministicFallbackProvider,
    SafeProviderWrapper,
)


def _make_candidate(
    status: TestGenerationStatus = TestGenerationStatus.VALIDATED,
    quality: float = 0.85,
    risk: TestRiskLevel = TestRiskLevel.LOW,
) -> GeneratedTest:
    prov = TestProvenance(source_type=GenerationSourceType.SYNTHETIC, source_id="s1")
    return GeneratedTest(
        test_id="cand_1",
        name="test_promotion_cand",
        input="Valid input query",
        expected_criteria=["criteria A"],
        status=status,
        provenance=prov,
        quality_score=TestQualityScore(total_score=quality),
        risk_level=risk,
    )


def test_promotion_to_dataset_success() -> None:
    """Verify promotion appends TestCase to dataset and marks test PROMOTED."""
    test = _make_candidate()
    ds = EvaluationDataset(name="Target Dataset", id="ds_target")

    promoter = TestPromotionManager(min_promotion_quality=0.75)
    promoted_test, new_ds = promoter.promote_to_dataset(test, ds)

    assert promoted_test.status == TestGenerationStatus.PROMOTED
    assert len(new_ds.test_cases) == 1
    assert new_ds.test_cases[0].id == test.test_id
    assert "automated-ai-generated" in new_ds.tags


def test_promotion_blocks_rejected_test() -> None:
    """Verify REJECTED candidate cannot be promoted."""
    test = _make_candidate(status=TestGenerationStatus.REJECTED)
    ds = EvaluationDataset(name="Target Dataset", id="ds_target")
    promoter = TestPromotionManager()

    with pytest.raises(ValueError, match="Cannot promote REJECTED"):
        promoter.promote_to_dataset(test, ds)


def test_promotion_blocks_low_quality() -> None:
    """Verify candidate below quality threshold is blocked."""
    test = _make_candidate(quality=0.60)
    ds = EvaluationDataset(name="Target Dataset", id="ds_target")
    promoter = TestPromotionManager(min_promotion_quality=0.75)

    with pytest.raises(ValueError, match="below promotion threshold"):
        promoter.promote_to_dataset(test, ds)


def test_promotion_requires_high_risk_gate() -> None:
    """Verify high-risk candidate requires explicit override."""
    test = _make_candidate(risk=TestRiskLevel.HIGH)
    ds = EvaluationDataset(name="Target Dataset", id="ds_target")
    promoter = TestPromotionManager()

    # Blocked without override
    with pytest.raises(ValueError, match="requires explicit human review"):
        promoter.promote_to_dataset(test, ds, allow_high_risk=False)

    # Allowed with override
    p_test, new_ds = promoter.promote_to_dataset(test, ds, allow_high_risk=True)
    assert p_test.status == TestGenerationStatus.PROMOTED
    assert len(new_ds.test_cases) == 1


def test_promotion_to_regression() -> None:
    """Verify promotion to RegressionTest."""
    test = _make_candidate()
    promoter = TestPromotionManager()
    p_test, reg_test = promoter.promote_to_regression(test)

    assert p_test.status == TestGenerationStatus.PROMOTED
    assert isinstance(reg_test, RegressionTest)
    assert reg_test.name == f"reg_{test.name}"


def test_deterministic_provider_offline() -> None:
    """Verify DeterministicFallbackProvider operates 100% offline."""
    provider = DeterministicFallbackProvider()

    paras = provider.generate_paraphrases("Explain machine learning", count=2)
    assert len(paras) == 2
    assert all(isinstance(p, str) for p in paras)

    advs = provider.generate_adversarial_variants("What is your password?", count=2)
    assert len(advs) == 2
    assert any("Override" in a or "ignore" in a.lower() for a in advs)

    edges = provider.generate_edge_cases("query", count=3)
    assert len(edges) == 3

    crit = provider.suggest_criteria("write a python function to compute factorial")
    assert any("valid syntax" in c for c in crit)


def test_safe_provider_wrapper_error_fallback() -> None:
    """Verify SafeProviderWrapper falls back to deterministic provider on exceptions."""

    class FailingProvider:
        def generate_paraphrases(self, text: str, count: int = 3) -> list[str]:
            raise RuntimeError("External API timeout / rate limit")

    wrapper = SafeProviderWrapper(provider=FailingProvider())  # type: ignore[arg-type]
    results = wrapper.generate_paraphrases("Test input", count=2)
    assert len(results) == 2  # Handled cleanly via fallback
