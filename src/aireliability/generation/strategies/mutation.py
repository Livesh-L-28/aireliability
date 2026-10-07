"""Mutation-based test generation applying bounded, controlled perturbations."""

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


class MutationGenerator:
    """Generates controlled mutations targeting prompts, contexts, retrieval, and tools."""

    strategy = GenerationStrategy.MUTATION_BASED

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        parent_tests: list[GeneratedTest | TestCase] = []

        if isinstance(source, (TestCase, GeneratedTest)):
            parent_tests = [source]
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, (TestCase, GeneratedTest)):
                    parent_tests.append(item)

        if not parent_tests:
            # Synthetic default parent
            parent_tests = [
                TestCase(
                    id="base_case_default",
                    name="default_mutation_target",
                    input="Analyze the quarterly revenue figures and summarize the main risks.",
                    expected_output="Summary of revenue figures and identified risks.",
                )
            ]

        mutations: list[GeneratedTest] = []
        limit = min(config.max_mutation_count, config.max_candidates)

        for parent in parent_tests:
            if len(mutations) >= limit:
                break
            p_muts = self._generate_parent_mutations(
                parent, config, remaining=limit - len(mutations)
            )
            mutations.extend(p_muts)

        return mutations[:limit]

    def _generate_parent_mutations(
        self,
        parent: GeneratedTest | TestCase,
        config: TestGenerationConfig,
        remaining: int,
    ) -> list[GeneratedTest]:
        parent_id = parent.test_id if isinstance(parent, GeneratedTest) else parent.id
        parent_name = parent.name
        input_str = str(parent.input)

        mut_specs: list[tuple[str, Any, str, dict[str, Any], list[str]]] = [
            (
                "prompt_remove_instruction",
                " ".join(input_str.split()[1:])
                if len(input_str.split()) > 1
                else input_str,
                "Prompt instruction omission",
                {"target": "prompt", "action": "remove_first_token"},
                ["must infer intent despite truncated instruction"],
            ),
            (
                "prompt_introduce_ambiguity",
                f"{input_str} (or perhaps do something completely different if uncertain)",
                "Prompt ambiguity injection",
                {"target": "prompt", "action": "add_ambiguity_clause"},
                ["must seek clarification or follow primary directive"],
            ),
            (
                "context_inject_irrelevant",
                input_str,
                "Context pollution with irrelevant evidence",
                {"target": "context", "action": "inject_irrelevant"},
                ["must ignore irrelevant evidence and maintain accuracy"],
            ),
            (
                "retrieval_shuffle_rankings",
                input_str,
                "Retrieval ranking permutation",
                {"target": "retrieval", "action": "shuffle_rankings"},
                ["must identify true grounded facts regardless of order"],
            ),
            (
                "tool_missing_definition",
                input_str,
                "Tool removal / unavailability mutation",
                {"target": "tool", "action": "omit_required_tool"},
                ["must fail gracefully when expected tool is absent"],
            ),
        ]

        out: list[GeneratedTest] = []
        for mut_type, mut_input, desc, params, criteria in mut_specs[:remaining]:
            prov = TestProvenance(
                source_type=GenerationSourceType.EXISTING_TEST,
                source_id=parent_id,
                parent_test_id=parent_id,
                mutation_type=mut_type,
                mutation_parameters=params,
                generator_name="MutationGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"Mutation '{mut_type}': {desc} on parent {parent_id}",
            )

            context_val = None
            if mut_type == "context_inject_irrelevant":
                context_val = "Unrelated trivia: Penguins are flightless birds native to the Southern Hemisphere."

            t = GeneratedTest(
                name=f"mut_{mut_type}_{parent_name}",
                test_type=TestType.MUTATION,
                strategy=self.strategy,
                input=mut_input,
                expected_output=None,
                expected_criteria=criteria,
                reference_answer=None,
                has_ground_truth=False,
                context=context_val,
                provenance=prov,
                confidence=0.90,
                risk_level=TestRiskLevel.MEDIUM,
                priority=TestPriority.MEDIUM,
                tags=["mutation_based", f"mutation:{mut_type}", f"parent:{parent_id}"],
                metadata={"mutation_parameters": params, "parent_name": parent_name},
                deterministic_seed=config.deterministic_seed,
            )
            out.append(t)

        return out
