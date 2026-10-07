"""Robustness test generation probing resilience against paraphrasing, formatting, and perturbations."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import TestCase
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


class RobustnessTestGenerator:
    """Generates tests ensuring model stability against formatting, casing, and syntactic perturbations."""

    strategy = GenerationStrategy.ROBUSTNESS

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        base_query = "What is the capital of France?"
        source_id = "robust_synthetic"
        source_type = GenerationSourceType.SYNTHETIC
        expected_ans = "Paris"

        if isinstance(source, TestCase):
            base_query = str(source.input)
            source_id = source.id
            source_type = GenerationSourceType.EXISTING_TEST
            expected_ans = (
                str(source.expected_output) if source.expected_output else "Paris"
            )
        elif isinstance(source, GeneratedTest):
            base_query = str(source.input)
            source_id = source.test_id
            source_type = GenerationSourceType.EXISTING_TEST
            expected_ans = (
                str(source.expected_output) if source.expected_output else "Paris"
            )
        elif isinstance(source, str):
            base_query = source

        perturbations = [
            (
                "case_mutation",
                base_query.upper(),
                [
                    "must produce identical semantic answer regardless of upper/lower case"
                ],
            ),
            (
                "punctuation_variation",
                f"{base_query}?!...",
                ["must produce stable answer despite irregular punctuation"],
            ),
            (
                "syntactic_paraphrase",
                f"Kindly state: {base_query}",
                ["must maintain factual consistency under polite paraphrasing"],
            ),
            (
                "irrelevant_prefix_padding",
                f"Note: This is an automated prompt test. {base_query}",
                ["must ignore irrelevant preface and address core query"],
            ),
        ]

        tests: list[GeneratedTest] = []
        for p_name, p_input, criteria in perturbations:
            if len(tests) >= config.max_candidates:
                break

            prov = TestProvenance(
                source_type=source_type,
                source_id=source_id,
                parent_test_id=source_id
                if source_type == GenerationSourceType.EXISTING_TEST
                else None,
                generator_name="RobustnessTestGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"Robustness perturbation: {p_name} on '{source_id}'",
            )

            t = GeneratedTest(
                name=f"robust_{p_name}_{source_id[:8]}",
                test_type=TestType.ROBUSTNESS,
                strategy=self.strategy,
                input=p_input,
                expected_output=expected_ans,
                expected_criteria=criteria,
                reference_answer=expected_ans,
                has_ground_truth=True,
                provenance=prov,
                confidence=0.95,
                risk_level=TestRiskLevel.LOW,
                priority=TestPriority.MEDIUM,
                tags=["robustness", f"perturbation:{p_name}"],
                metadata={"original_query": base_query},
                deterministic_seed=config.deterministic_seed,
            )
            tests.append(t)

        return tests
