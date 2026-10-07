"""Regression-driven test generation from RegressionTest models and EvaluationComparisonResults."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import RegressionTest
from aireliability.evaluation.governance.baselines import EvaluationComparisonResult
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
    TestType,
)


class RegressionTestGenerator:
    """Generates tests guarding against identified baseline regressions and metric degradations."""

    strategy = GenerationStrategy.REGRESSION_DRIVEN

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        tests: list[GeneratedTest] = []

        if isinstance(source, RegressionTest):
            tests.append(self._from_regression_test(source, config))
        elif isinstance(source, EvaluationComparisonResult):
            tests.extend(self._from_comparison_result(source, config))
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, RegressionTest):
                    tests.append(self._from_regression_test(item, config))
                elif isinstance(item, EvaluationComparisonResult):
                    tests.extend(self._from_comparison_result(item, config))

        return tests[: config.max_candidates]

    def _from_regression_test(
        self,
        reg: RegressionTest,
        config: TestGenerationConfig,
    ) -> GeneratedTest:
        tc = reg.test_case
        prov = TestProvenance(
            source_type=GenerationSourceType.REGRESSION_TEST,
            source_id=reg.id,
            source_failure_id=reg.source_failure_id,
            generator_name="RegressionTestGenerator",
            deterministic_seed=config.deterministic_seed,
            rationale=f"Derived from regression test '{reg.name}' linking to failure {reg.source_failure_id}",
            metadata=dict(reg.metadata),
        )

        has_ground_truth = tc.expected_output is not None
        ref_ans = str(tc.expected_output) if has_ground_truth else None
        criteria = list(tc.expectations)
        if not criteria:
            criteria = [f"must prevent regression of {reg.name}"]

        return GeneratedTest(
            name=f"gen_{reg.name}",
            test_type=TestType.REGRESSION,
            strategy=self.strategy,
            input=tc.input,
            expected_output=tc.expected_output,
            expected_criteria=criteria,
            reference_answer=ref_ans,
            has_ground_truth=has_ground_truth,
            provenance=prov,
            confidence=0.95,
            risk_level=TestRiskLevel.MEDIUM,
            priority=TestPriority.HIGH,
            tags=list(tc.tags) + ["regression_driven"],
            metadata=dict(tc.metadata),
            deterministic_seed=config.deterministic_seed,
        )

    def _from_comparison_result(
        self,
        cmp: EvaluationComparisonResult,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        tests: list[GeneratedTest] = []
        for reg_desc in cmp.regressions:
            prov = TestProvenance(
                source_type=GenerationSourceType.REGRESSION_TEST,
                source_id=cmp.current_report_id,
                generator_name="RegressionTestGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"Regression detected relative to baseline {cmp.baseline_name} v{cmp.baseline_version}: {reg_desc}",
            )
            criteria = [
                f"must recover metric performance for: {reg_desc}",
                "must not exhibit score degradation relative to baseline",
            ]
            t = GeneratedTest(
                name=f"reg_guard_{cmp.baseline_name}_{len(tests)}",
                test_type=TestType.REGRESSION,
                strategy=self.strategy,
                input=f"Evaluation query under baseline {cmp.baseline_name} guarding against {reg_desc}",
                expected_output=None,
                expected_criteria=criteria,
                reference_answer=None,
                has_ground_truth=False,
                provenance=prov,
                confidence=0.90,
                risk_level=TestRiskLevel.HIGH,
                priority=TestPriority.HIGH,
                tags=["baseline_regression", f"baseline:{cmp.baseline_name}"],
                metadata={
                    "baseline_version": cmp.baseline_version,
                    "summary": cmp.summary,
                },
                deterministic_seed=config.deterministic_seed,
            )
            tests.append(t)
        return tests
