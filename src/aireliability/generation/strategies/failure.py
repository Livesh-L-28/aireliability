"""Failure-driven test generation converting FailureReports and EvaluationReports into test cases."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import FailureReport
from aireliability.evaluation.models import EvaluationReport
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


class FailureTestGenerator:
    """Generates targeted test cases reproducing or guarding against detected failures."""

    strategy = GenerationStrategy.FAILURE_DRIVEN

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        failures: list[FailureReport] = []

        if isinstance(source, FailureReport):
            failures = [source]
        elif isinstance(source, EvaluationReport):
            failures = list(source.failures)
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, FailureReport):
                    failures.append(item)
                elif isinstance(item, EvaluationReport):
                    failures.extend(item.failures)
        elif hasattr(source, "failures") and isinstance(source.failures, list):
            failures = [f for f in source.failures if isinstance(f, FailureReport)]

        tests: list[GeneratedTest] = []
        for fail in failures[: config.max_candidates]:
            t = self._convert_failure(fail, config)
            if t:
                tests.append(t)

        return tests

    def _convert_failure(
        self,
        failure: FailureReport,
        config: TestGenerationConfig,
    ) -> GeneratedTest:
        cat = failure.category.lower()
        fail_type = failure.type.lower()
        evidence_dict = (
            failure.evidence
            if isinstance(failure.evidence, dict)
            else {"raw_evidence": str(failure.evidence)}
            if failure.evidence is not None
            else {}
        )

        # Extract input if present in evidence or metadata
        test_input = (
            evidence_dict.get("input")
            or failure.metadata.get("input")
            or f"Regression prompt guarding against {failure.category}:{failure.type}"
        )

        expected_criteria: list[str] = [
            f"must not trigger {failure.category} failure",
            f"error message must not contain '{failure.type}'",
        ]

        test_type = TestType.REGRESSION
        risk_level = TestRiskLevel.MEDIUM
        priority = TestPriority.HIGH

        if "security" in cat or "safety" in cat or "leak" in fail_type:
            risk_level = TestRiskLevel.CRITICAL
            priority = TestPriority.CRITICAL
            test_type = TestType.SAFETY
            expected_criteria.append(
                "must strictly enforce security and sanitization boundaries"
            )
        elif "tool" in cat:
            test_type = TestType.AGENT
            expected_criteria.append(
                "must invoke tools with valid schema and arguments"
            )
        elif "retriev" in cat or "rag" in cat:
            test_type = TestType.RAG
            expected_criteria.append("retrieved context must be relevant and grounded")
        elif "latency" in cat or "timeout" in cat or "performance" in cat:
            test_type = TestType.UNIT
            expected_criteria.append(
                "execution duration must remain bounded within threshold"
            )

        tool_defs: list[dict[str, Any]] = []
        if "tool" in cat and "tool_definition" in evidence_dict:
            tool_defs.append(evidence_dict["tool_definition"])
        elif "tool" in cat and "tool_name" in evidence_dict:
            tool_defs.append(
                {"name": str(evidence_dict["tool_name"]), "type": "function"}
            )

        expected_tools: list[dict[str, Any]] = []
        if "expected_tool" in evidence_dict:
            expected_tools.append({"name": str(evidence_dict["expected_tool"])})

        provenance = TestProvenance(
            source_type=GenerationSourceType.FAILURE_REPORT,
            source_id=failure.failure_id,
            source_failure_id=failure.failure_id,
            source_trace_id=failure.trace_id,
            generator_name="FailureTestGenerator",
            deterministic_seed=config.deterministic_seed,
            rationale=f"Generated from failure {failure.failure_id} ({failure.category}:{failure.type}): {failure.message}",
            metadata={
                "severity": str(failure.severity),
                "confidence": failure.confidence,
            },
        )

        return GeneratedTest(
            name=f"guard_{failure.category}_{failure.type}_{failure.failure_id[:8]}",
            test_type=test_type,
            strategy=self.strategy,
            input=test_input,
            expected_output=None,
            expected_criteria=expected_criteria,
            reference_answer=None,
            has_ground_truth=False,
            tool_definitions=tool_defs,
            expected_tool_calls=expected_tools,
            provenance=provenance,
            confidence=failure.confidence,
            risk_level=risk_level,
            priority=priority,
            tags=[
                "failure_driven",
                f"category:{failure.category}",
                f"type:{failure.type}",
            ],
            metadata=dict(failure.metadata),
            deterministic_seed=config.deterministic_seed,
        )
