"""Deterministic edge-case test generation covering structural and boundary variations."""

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


class EdgeCaseGenerator:
    """Generates bounded, deterministic edge cases testing input limits, unicode, and structure."""

    strategy = GenerationStrategy.EDGE_CASE

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        base_input: str = "Standard prompt query"
        source_id: str = "synthetic_edge"
        source_type = GenerationSourceType.SYNTHETIC

        if isinstance(source, TestCase):
            base_input = str(source.input)
            source_id = source.id
            source_type = GenerationSourceType.EXISTING_TEST
        elif isinstance(source, GeneratedTest):
            base_input = str(source.input)
            source_id = source.test_id
            source_type = GenerationSourceType.EXISTING_TEST
        elif isinstance(source, str):
            base_input = source

        # Deterministic boundary variations
        variations: list[tuple[str, Any, list[str], str]] = [
            (
                "empty_input",
                "",
                ["must handle empty input gracefully without crash"],
                "Empty input boundary",
            ),
            (
                "null_input",
                None,
                ["must handle null/missing input gracefully"],
                "Null input boundary",
            ),
            (
                "whitespace_only",
                "   \n\t   ",
                ["must handle whitespace-only input gracefully"],
                "Whitespace boundary",
            ),
            (
                "single_char",
                "a",
                ["must process minimal character query"],
                "Minimal character boundary",
            ),
            (
                "extreme_length",
                base_input + (" " + base_input) * 50,
                ["must handle large context without buffer overrun"],
                "Extreme length boundary",
            ),
            (
                "unicode_emoji",
                f"🚀🔥 {base_input} ⚡️🌟 [한국어, 日本語, العربية]",
                ["must parse non-ASCII Unicode and emojis properly"],
                "Unicode boundary",
            ),
            (
                "malformed_json",
                '{"query": "' + base_input + '", unclosed_json:',
                ["must reject or recover from malformed JSON payload"],
                "Malformed JSON boundary",
            ),
            (
                "zero_retrieval",
                base_input,
                ["must handle zero retrieved documents with appropriate fallback"],
                "Zero retrieval boundary",
            ),
            (
                "duplicated_context",
                base_input,
                ["must not duplicate answers when context is repeated"],
                "Duplicated context boundary",
            ),
            (
                "conflicting_context",
                base_input,
                ["must reconcile or flag conflicting context"],
                "Conflicting context boundary",
            ),
        ]

        tests: list[GeneratedTest] = []
        for name_suffix, val, criteria, desc in variations:
            if len(tests) >= config.max_candidates:
                break

            prov = TestProvenance(
                source_type=source_type,
                source_id=source_id,
                generator_name="EdgeCaseGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"Deterministic edge case: {desc}",
            )

            tags = ["edge_case", f"edge_type:{name_suffix}"]
            if val is None:
                tags.append("null_input")

            ctx = None
            if name_suffix == "zero_retrieval":
                ctx = ""
            elif name_suffix == "duplicated_context":
                ctx = "Context fact A.\nContext fact A."
            elif name_suffix == "conflicting_context":
                ctx = "Fact: The temperature is 100 degrees.\nFact: The temperature is -10 degrees."

            t = GeneratedTest(
                name=f"edge_{name_suffix}_{source_id[:8]}",
                test_type=TestType.EDGE_CASE,
                strategy=self.strategy,
                input=val,
                expected_output=None,
                expected_criteria=criteria,
                reference_answer=None,
                has_ground_truth=False,
                context=ctx,
                provenance=prov,
                confidence=1.0,
                risk_level=TestRiskLevel.MEDIUM
                if name_suffix in ("malformed_json", "extreme_length")
                else TestRiskLevel.LOW,
                priority=TestPriority.MEDIUM,
                tags=tags,
                metadata={"edge_description": desc},
                deterministic_seed=config.deterministic_seed,
            )
            tests.append(t)

        return tests
