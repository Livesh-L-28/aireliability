"""Deterministic synthesizer for intelligent regression test generation.

Transforms FailureReports, RootCauseReports, and ExecutionTraces into minimal,
explainable, and reproducible RegressionTests without using an LLM.
"""

from collections.abc import Sequence
from typing import Any

from aireliability.core.models import (
    ExecutionTrace,
    FailureReport,
    RegressionTest,
    TestCase,
)
from aireliability.diagnosis.models import (
    RootCause,
    RootCauseCategory,
    RootCauseReport,
    RootCauseType,
)
from aireliability.regression.minimizer import RegressionMinimizer
from aireliability.regression.models import (
    GenerationMethod,
    GenerationStatus,
    RegressionCandidate,
)
from aireliability.regression.validator import RegressionValidator


class RegressionSynthesizer:
    """Synthesizes minimal, validated regression tests from failure evidence."""

    def __init__(
        self,
        minimizer: RegressionMinimizer | None = None,
        validator: RegressionValidator | None = None,
    ) -> None:
        self.minimizer = minimizer or RegressionMinimizer()
        self.validator = validator or RegressionValidator()

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
        """Synthesize a minimal, explainable RegressionCandidate from failure evidence.

        Args:
            failure: The detected failure report.
            test_case: Original test case that produced the failure.
            trace: Optional observed execution trace.
            root_cause: Optional specific RootCause diagnosis.
            root_cause_report: Optional comprehensive RootCauseReport.
            existing_tests: Optional suite of existing regression tests for
                duplicate check.
            name: Optional explicit name override.

        Returns:
            A populated and validated RegressionCandidate.
        """
        # Resolve effective root cause
        effective_rc = root_cause
        if effective_rc is None and root_cause_report is not None:
            effective_rc = root_cause_report.primary_cause

        # Safety Check: Insufficient Evidence verification
        if not failure.message and not effective_rc and not failure.evidence:
            empty_tc = test_case.model_copy(
                update={
                    "tags": list(test_case.tags)
                    + ["regression", "insufficient_evidence"]
                }
            )
            cand = RegressionCandidate(
                name=name or f"reg_unknown_{test_case.name}",
                source_failure_id=failure.failure_id,
                test_case=empty_tc,
                status=GenerationStatus.INSUFFICIENT_EVIDENCE,
                minimized=False,
            )
            val = self.validator.validate(cand, existing_tests)
            return cand.model_copy(update={"validation": val})

        # 1. Determine GenerationMethod
        is_semantic = (
            effective_rc is not None
            and effective_rc.type == RootCauseType.SEMANTIC_MISMATCH
        ) or "semantic" in failure.type.lower()
        method = (
            GenerationMethod.SEMANTIC_FAILURE_CAPTURE
            if is_semantic
            else GenerationMethod.DETERMINISTIC_TRACE_SYNTHESIS
        )

        # 2. Conservative Input Minimization
        minimized_input, input_was_min = self.minimizer.minimize_input(
            original_input=test_case.input,
            root_cause=effective_rc,
            test_case=test_case,
        )

        # 3. Construct specific assertions/expectations based on failure type
        synth_expectations, synth_expected_output, updated_metadata = (
            self._synthesize_assertions(
                failure=failure,
                test_case=test_case,
                root_cause=effective_rc,
                trace=trace,
            )
        )

        # 4. Formulate Tag Set
        tags = list(test_case.tags)
        if "regression" not in tags:
            tags.append("regression")
        cat_tag = f"failure:{failure.category}"
        if cat_tag not in tags:
            tags.append(cat_tag)
        type_tag = f"type:{failure.type}"
        if type_tag not in tags:
            tags.append(type_tag)
        if input_was_min and "minimized" not in tags:
            tags.append("minimized")

        # 5. Build Synthesized TestCase
        combined_tc_meta = dict(test_case.metadata)
        combined_tc_meta.update(updated_metadata)
        combined_tc_meta["source_failure_id"] = failure.failure_id
        combined_tc_meta["source_trace_id"] = failure.trace_id
        combined_tc_meta["failure_category"] = failure.category
        combined_tc_meta["failure_type"] = failure.type
        combined_tc_meta["generation_method"] = str(method)
        if effective_rc:
            combined_tc_meta["root_cause_id"] = effective_rc.id

        synthesized_tc = test_case.model_copy(
            update={
                "input": minimized_input,
                "expected_output": synth_expected_output,
                "expectations": synth_expectations,
                "tags": tags,
                "metadata": combined_tc_meta,
            }
        )

        # 6. Build Candidate Object
        reg_name = name or f"reg_{failure.category}_{failure.type}_{test_case.name}"
        evidence_summary: list[dict[str, Any]] = []
        if effective_rc and effective_rc.evidence:
            evidence_summary = [
                ev.model_dump() if hasattr(ev, "model_dump") else str(ev)
                for ev in effective_rc.evidence
            ]
        elif isinstance(failure.evidence, dict):
            evidence_summary = [failure.evidence]

        candidate = RegressionCandidate(
            name=reg_name,
            source_failure_id=failure.failure_id,
            root_cause_id=effective_rc.id if effective_rc else None,
            trace_id=failure.trace_id,
            generation_method=method,
            status=GenerationStatus.SUCCESS,
            test_case=synthesized_tc,
            minimized=input_was_min,
            evidence_summary=evidence_summary,
            metadata={
                "failure_severity": str(failure.severity),
                "failure_confidence": failure.confidence,
            },
        )

        # 7. Quality Validation & Duplicate Check
        validation = self.validator.validate(candidate, existing_tests)
        status = GenerationStatus.SUCCESS
        if validation.duplicate:
            status = GenerationStatus.DUPLICATE
        elif not validation.valid:
            status = GenerationStatus.VALIDATION_FAILED

        return candidate.model_copy(update={"validation": validation, "status": status})

    def _synthesize_assertions(
        self,
        failure: FailureReport,
        test_case: TestCase,
        root_cause: RootCause | None,
        trace: ExecutionTrace | None,
    ) -> tuple[list[str], Any, dict[str, Any]]:
        """Synthesize expectations and expected outputs based on failure type."""
        expectations = list(test_case.expectations)
        expected_output = test_case.expected_output
        metadata: dict[str, Any] = {}

        ev_dict = failure.evidence if isinstance(failure.evidence, dict) else {}
        rc_type = root_cause.type if root_cause else None
        rc_cat = root_cause.category if root_cause else None

        # --- A. TOOL FAILURES ---
        if rc_cat == RootCauseCategory.TOOL or failure.category == "tool":
            if rc_type == RootCauseType.WRONG_ORDER or failure.type == "wrong_order":
                exp_order = ev_dict.get("expected_order")
                if not exp_order and root_cause:
                    for ev in root_cause.evidence:
                        if ev.field == "tool_order" and ev.expected:
                            if isinstance(ev.expected, list):
                                exp_order = ev.expected
                            elif isinstance(ev.expected, str) and " → " in ev.expected:
                                exp_order = ev.expected.split(" → ")
                if exp_order:
                    rule = f"ToolOrder:{','.join(exp_order)}"
                    if rule not in expectations:
                        expectations.append(rule)
                    metadata["expected_order"] = exp_order

            elif (
                rc_type == RootCauseType.WRONG_ARGUMENT
                or failure.type == "wrong_argument"
            ):
                tool_name = ev_dict.get("tool_name")
                expected_args = ev_dict.get("expected_arguments")
                if not tool_name and root_cause:
                    for ev in root_cause.evidence:
                        if ev.field == "arguments" and isinstance(ev.expected, dict):
                            expected_args = ev.expected
                if tool_name:
                    metadata["expected_tool"] = tool_name
                    if expected_args:
                        metadata["expected_arguments"] = expected_args
                        rule = f"ToolArguments:{tool_name}"
                        if rule not in expectations:
                            expectations.append(rule)

            elif rc_type in (
                RootCauseType.WRONG_TOOL,
                RootCauseType.MISSING_TOOL,
            ) or failure.type in ("wrong_tool", "missing_tool"):
                req_tool = ev_dict.get("expected_tool")
                if not req_tool and root_cause:
                    for ev in root_cause.evidence:
                        if ev.field in ("tool_name", "tool_called") and ev.expected:
                            req_tool = str(ev.expected)
                if req_tool:
                    rule = f"ToolCalled:{req_tool}"
                    if rule not in expectations:
                        expectations.append(rule)
                    metadata["expected_tool"] = req_tool

        # --- B. OUTPUT & SEMANTIC FAILURES ---
        elif rc_cat == RootCauseCategory.OUTPUT or failure.category in (
            "output",
            "task",
        ):
            is_semantic = (
                rc_type == RootCauseType.SEMANTIC_MISMATCH
                or "semantic" in failure.type.lower()
            )
            if is_semantic:
                # Preserve semantic evaluation criteria and threshold
                threshold = ev_dict.get("threshold", 0.70)
                criteria = ev_dict.get("criteria", [])
                reference = ev_dict.get("reference") or (
                    str(expected_output) if expected_output is not None else None
                )
                metadata["semantic_criteria"] = criteria
                metadata["semantic_threshold"] = threshold
                metadata["semantic_reference"] = reference
                metadata["semantic_evaluator"] = ev_dict.get(
                    "evaluator", "SemanticExpectation"
                )
                rule = f"SemanticMatch:threshold={threshold}"
                if rule not in expectations:
                    expectations.append(rule)
            else:
                # Deterministic output mismatch
                if expected_output is not None:
                    rule = f"OutputEquals:{expected_output}"
                    if rule not in expectations:
                        expectations.append(rule)

        # --- C. PERFORMANCE FAILURES ---
        elif (
            rc_cat == RootCauseCategory.PERFORMANCE or failure.category == "performance"
        ):
            max_lat = ev_dict.get("max_latency_ms")
            if max_lat is not None:
                metadata["max_latency_ms"] = float(max_lat)
                rule = f"MaxLatency:{max_lat}"
                if rule not in expectations:
                    expectations.append(rule)

        return expectations, expected_output, metadata


__all__ = ["RegressionSynthesizer"]
