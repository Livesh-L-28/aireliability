"""Safe promotion of validated generated tests into Golden Datasets and Regression Suites."""

from __future__ import annotations

from aireliability.core.models import RegressionTest, TestCase
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.generation.models import (
    GeneratedTest,
    TestGenerationStatus,
    TestRiskLevel,
)


class TestPromotionManager:
    """Safely promotes validated generated tests into evaluation datasets and regression suites."""

    def __init__(
        self,
        min_promotion_quality: float = 0.75,
        min_confidence: float = 0.50,
    ) -> None:
        self.min_promotion_quality = min_promotion_quality
        self.min_confidence = min_confidence

    def can_promote(
        self,
        test: GeneratedTest,
        *,
        allow_high_risk: bool = False,
    ) -> tuple[bool, str]:
        """Check if a test qualifies for safe promotion."""
        if test.status == TestGenerationStatus.REJECTED:
            return False, "Cannot promote REJECTED test candidate."
        if test.status != TestGenerationStatus.VALIDATED:
            return (
                False,
                f"Test must be in VALIDATED state before promotion (current: {test.status.value}).",
            )

        quality = test.quality_score.total_score if test.quality_score else 0.0
        if quality < self.min_promotion_quality:
            return (
                False,
                f"Quality score {quality:.2f} is below promotion threshold {self.min_promotion_quality:.2f}.",
            )

        if test.confidence < self.min_confidence:
            return (
                False,
                f"Confidence {test.confidence:.2f} is below confidence threshold {self.min_confidence:.2f}.",
            )

        if (
            test.risk_level in (TestRiskLevel.HIGH, TestRiskLevel.CRITICAL)
            and not allow_high_risk
        ):
            return (
                False,
                f"High-risk test ({test.risk_level.value}) requires explicit human review / authorization to promote.",
            )

        return True, "Eligible for promotion."

    def promote_to_dataset(
        self,
        test: GeneratedTest,
        dataset: EvaluationDataset,
        *,
        allow_high_risk: bool = False,
    ) -> tuple[GeneratedTest, EvaluationDataset]:
        """Promote a test to an existing EvaluationDataset and transition status to PROMOTED."""
        eligible, reason = self.can_promote(test, allow_high_risk=allow_high_risk)
        if not eligible:
            raise ValueError(f"Promotion rejected: {reason}")

        # Convert to TestCase
        tc: TestCase = test.to_test_case()

        # Update dataset
        updated_cases = list(dataset.test_cases) + [tc]
        updated_tags = sorted(list(set(dataset.tags + ["automated-ai-generated"])))
        updated_meta = dict(dataset.metadata)
        updated_meta["last_promoted_test_id"] = test.test_id

        new_dataset = dataset.model_copy(
            update={
                "test_cases": updated_cases,
                "tags": updated_tags,
                "metadata": updated_meta,
            }
        )

        promoted_test = test.transition_to(
            TestGenerationStatus.PROMOTED,
            reason=f"Promoted to dataset '{dataset.name}' ({dataset.id}).",
        )
        return promoted_test, new_dataset

    def promote_to_regression(
        self,
        test: GeneratedTest,
        *,
        allow_high_risk: bool = False,
    ) -> tuple[GeneratedTest, RegressionTest]:
        """Promote a test to a RegressionTest and transition status to PROMOTED."""
        eligible, reason = self.can_promote(test, allow_high_risk=allow_high_risk)
        if not eligible:
            raise ValueError(f"Promotion rejected: {reason}")

        reg_test = test.to_regression_test()
        promoted_test = test.transition_to(
            TestGenerationStatus.PROMOTED,
            reason=f"Promoted to regression test '{reg_test.name}' ({reg_test.id}).",
        )
        return promoted_test, reg_test

    def batch_promote_to_dataset(
        self,
        tests: list[GeneratedTest],
        dataset: EvaluationDataset,
        *,
        allow_high_risk: bool = False,
    ) -> tuple[list[GeneratedTest], EvaluationDataset]:
        """Batch promote eligible tests to a dataset, skipping ineligible tests."""
        current_dataset = dataset
        promoted_tests: list[GeneratedTest] = []

        for t in tests:
            eligible, _ = self.can_promote(t, allow_high_risk=allow_high_risk)
            if eligible:
                p_test, current_dataset = self.promote_to_dataset(
                    t, current_dataset, allow_high_risk=allow_high_risk
                )
                promoted_tests.append(p_test)

        return promoted_tests, current_dataset
