"""Consistency test generation creating groups of semantically equivalent tests expecting stable outputs."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

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


class ConsistencyTestGenerator:
    """Generates test clusters to evaluate output stability and variance across equivalent inputs."""

    strategy = GenerationStrategy.CONSISTENCY

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        base_query = "What is the speed of light in vacuum?"
        expected_ans = "299,792,458 m/s"
        source_id = "consistency_seed"
        source_type = GenerationSourceType.SYNTHETIC

        if isinstance(source, TestCase):
            base_query = str(source.input)
            source_id = source.id
            source_type = GenerationSourceType.EXISTING_TEST
            if source.expected_output:
                expected_ans = str(source.expected_output)
        elif isinstance(source, GeneratedTest):
            base_query = str(source.input)
            source_id = source.test_id
            source_type = GenerationSourceType.EXISTING_TEST
            if source.expected_output:
                expected_ans = str(source.expected_output)
        elif isinstance(source, str):
            base_query = source

        group_id = f"const_grp_{uuid4().hex[:8]}"

        phrasings = [
            f"{base_query}",
            f"State clearly: {base_query}",
            f"Tell me {base_query.lower()}",
            f"Could you specify the answer to: '{base_query}'?",
        ]

        tests: list[GeneratedTest] = []
        for idx, phrasing in enumerate(phrasings):
            if len(tests) >= config.max_candidates:
                break

            prov = TestProvenance(
                source_type=source_type,
                source_id=source_id,
                parent_test_id=source_id
                if source_type == GenerationSourceType.EXISTING_TEST
                else None,
                generator_name="ConsistencyTestGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"Consistency evaluation member {idx + 1}/4 for group {group_id}",
                metadata={"group_id": group_id, "variant_index": idx},
            )

            criteria = [
                f"answer must be semantically equivalent across group '{group_id}'",
                "must demonstrate bounded semantic variance (<0.10)",
            ]

            t = GeneratedTest(
                name=f"const_{group_id}_{idx}",
                test_type=TestType.CONSISTENCY,
                strategy=self.strategy,
                input=phrasing,
                expected_output=expected_ans,
                expected_criteria=criteria,
                reference_answer=expected_ans,
                has_ground_truth=True,
                provenance=prov,
                confidence=1.0,
                risk_level=TestRiskLevel.LOW,
                priority=TestPriority.MEDIUM,
                tags=["consistency", f"group:{group_id}", f"variant:{idx}"],
                metadata={
                    "consistency_group_id": group_id,
                    "group_size": len(phrasings),
                },
                deterministic_seed=config.deterministic_seed,
            )
            tests.append(t)

        return tests
