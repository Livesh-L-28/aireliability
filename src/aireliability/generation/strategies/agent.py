"""Agent trajectory test generation evaluating tool selection, ordering, and loop boundaries."""

from __future__ import annotations

from typing import Any

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


class AgentTestGenerator:
    """Generates tests for agent tool selection, call sequencing, recovery, and recursion bounds."""

    strategy = GenerationStrategy.AGENT_TRAJECTORY

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        agent_scenarios = [
            (
                "tool_selection_and_call",
                "Lookup weather in Tokyo and then book flight if clear.",
                [
                    {"name": "get_weather", "description": "Fetches current weather"},
                    {"name": "book_flight", "description": "Books flight reservation"},
                ],
                [{"name": "get_weather", "arguments": {"city": "Tokyo"}}],
                ["tool_order:get_weather->book_flight", "max_steps:3"],
                [
                    "must invoke get_weather before deciding flight booking",
                    "must pass city='Tokyo'",
                ],
            ),
            (
                "excessive_tool_call_loop",
                "Keep searching until you find an exact mathematical proof of P=NP.",
                [
                    {"name": "search_arxiv", "description": "Searches paper archive"},
                ],
                [],
                ["max_tool_calls:5"],
                [
                    "must terminate within loop bound",
                    "must report inconclusive result rather than infinite loop",
                ],
            ),
            (
                "invalid_argument_recovery",
                "Calculate discount with rate=-0.50.",
                [
                    {
                        "name": "calculate_discount",
                        "description": "Calculates percentage discount",
                    },
                ],
                [{"name": "calculate_discount", "arguments": {"rate": -0.50}}],
                ["must_recover_from_error"],
                [
                    "must catch tool validation exception and provide explanatory feedback"
                ],
            ),
        ]

        tests: list[GeneratedTest] = []
        for name, goal, tools, exp_calls, constraints, criteria in agent_scenarios:
            if len(tests) >= config.max_candidates:
                break

            prov = TestProvenance(
                source_type=GenerationSourceType.SYNTHETIC,
                source_id=f"agent_spec_{name}",
                generator_name="AgentTestGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"Agent trajectory evaluation: {name}",
            )

            t = GeneratedTest(
                name=f"agent_{name}",
                test_type=TestType.AGENT,
                strategy=self.strategy,
                input=goal,
                expected_output=None,
                expected_criteria=criteria,
                reference_answer=None,
                has_ground_truth=False,
                tool_definitions=tools,
                expected_tool_calls=exp_calls,
                expected_trajectory_constraints=constraints,
                provenance=prov,
                confidence=1.0,
                risk_level=TestRiskLevel.MEDIUM,
                priority=TestPriority.HIGH,
                tags=["agent_trajectory", f"scenario:{name}"],
                metadata={"max_trajectory_steps": len(constraints)},
                deterministic_seed=config.deterministic_seed,
            )
            tests.append(t)

        return tests
