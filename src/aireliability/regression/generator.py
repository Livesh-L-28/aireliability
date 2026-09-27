"""Regression test generation from detected failures.

Supports both direct regression wrapping and intelligent synthesis with
minimization, duplicate detection, and quality validation.
"""

from collections.abc import Sequence
from typing import Any

from aireliability.core.models import (
    ExecutionTrace,
    FailureReport,
    RegressionTest,
    TestCase,
)
from aireliability.diagnosis.models import RootCause, RootCauseReport
from aireliability.regression.models import (
    GenerationMethod,
    RegressionCandidate,
)
from aireliability.regression.synthesizer import RegressionSynthesizer
from aireliability.regression.validator import RegressionValidator


class RegressionGenerator:
    """Generates reproducible RegressionTest cases from FailureReports and TestCases.

    Preserves the full provenance chain:
    RegressionTest -> source_failure_id -> FailureReport -> trace_id.
    """

    def __init__(
        self,
        synthesizer: RegressionSynthesizer | None = None,
        validator: RegressionValidator | None = None,
    ) -> None:
        self.synthesizer = synthesizer or RegressionSynthesizer()
        self.validator = validator or RegressionValidator()

    def generate(
        self,
        failure: FailureReport,
        test_case: TestCase,
        *,
        name: str | None = None,
        root_cause: Any | None = None,
        additional_tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RegressionTest:
        """Generate a RegressionTest from a FailureReport and its originating TestCase.

        Preserves full backward compatibility with Phase 1–17 callers.

        Args:
            failure: The detected failure report.
            test_case: The original test case that produced the failure.
            name: Optional name for the regression test. If omitted, synthesized from
                failure category and test name.
            root_cause: Optional RootCause diagnosis object to enrich provenance.
            additional_tags: Optional extra tags to append to the test case tags.
            metadata: Optional additional metadata for the regression test.

        Returns:
            A populated RegressionTest linking to source_failure_id.
        """
        reg_name = name or f"reg_{failure.category}_{failure.type}_{test_case.name}"

        tags = list(test_case.tags)
        if "regression" not in tags:
            tags.append("regression")
        category_tag = f"failure:{failure.category}"
        if category_tag not in tags:
            tags.append(category_tag)
        type_tag = f"type:{failure.type}"
        if type_tag not in tags:
            tags.append(type_tag)
        if additional_tags:
            for t in additional_tags:
                if t not in tags:
                    tags.append(t)

        combined_tc_metadata = dict(test_case.metadata)
        combined_tc_metadata["source_failure_id"] = failure.failure_id
        combined_tc_metadata["source_trace_id"] = failure.trace_id
        combined_tc_metadata["failure_category"] = failure.category
        combined_tc_metadata["failure_type"] = failure.type
        combined_tc_metadata["failure_message"] = failure.message
        if root_cause is not None:
            rc_id = getattr(root_cause, "id", str(root_cause))
            combined_tc_metadata["root_cause_id"] = rc_id

        regression_tc = test_case.model_copy(
            update={
                "tags": tags,
                "metadata": combined_tc_metadata,
            }
        )

        combined_reg_meta = dict(metadata or {})
        combined_reg_meta["failure_severity"] = str(failure.severity)
        combined_reg_meta["failure_confidence"] = failure.confidence
        if failure.evidence is not None:
            combined_reg_meta["failure_evidence"] = failure.evidence
        if root_cause is not None:
            rc_id = getattr(root_cause, "id", str(root_cause))
            combined_reg_meta["root_cause_id"] = rc_id
            if hasattr(root_cause, "evidence"):
                combined_reg_meta["root_cause_evidence"] = [
                    ev.model_dump() if hasattr(ev, "model_dump") else str(ev)
                    for ev in root_cause.evidence
                ]

        return RegressionTest(
            name=reg_name,
            source_failure_id=failure.failure_id,
            test_case=regression_tc,
            metadata=combined_reg_meta,
        )

    def synthesize(
        self,
        failure: FailureReport,
        test_case: TestCase,
        *,
        trace: ExecutionTrace | None = None,
        root_cause: RootCause | None = None,
        root_cause_report: RootCauseReport | None = None,
        existing_tests: Sequence[RegressionTest] | None = None,
        name: str | None = None,
    ) -> RegressionCandidate:
        """Synthesize a minimal, validated regression candidate.

        Applies failure-type-specific logic, input minimization, quality validation,
        and duplicate detection.

        Args:
            failure: The FailureReport.
            test_case: The source TestCase.
            trace: Optional ExecutionTrace for step/latency telemetry.
            root_cause: Optional diagnosed RootCause.
            root_cause_report: Optional full RootCauseReport.
            existing_tests: Optional suite of existing regression tests for
                duplicate check.
            name: Optional name for the synthesized regression test.

        Returns:
            A validated RegressionCandidate containing quality metrics and
            minimized payload.
        """
        return self.synthesizer.synthesize(
            failure=failure,
            test_case=test_case,
            trace=trace,
            root_cause=root_cause,
            root_cause_report=root_cause_report,
            existing_tests=existing_tests,
            name=name,
        )

    def generate_all(
        self,
        failures: list[FailureReport],
        test_case: TestCase,
    ) -> list[RegressionTest]:
        """Generate a list of RegressionTests for multiple failures on a test case."""
        return [self.generate(f, test_case) for f in failures]


__all__ = [
    "GenerationMethod",
    "RegressionCandidate",
    "RegressionGenerator",
]
