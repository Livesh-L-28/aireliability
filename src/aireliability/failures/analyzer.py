"""Deterministic failure analyzer.

Maps execution traces and evaluation results to structured failure reports.
"""

from collections.abc import Callable

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
)
from aireliability.failures.taxonomy import (
    FailureCategory,
    FailureTaxonomy,
    FailureType,
)


class FailureAnalyzer:
    """Deterministic failure analyzer.

    Transforms failed EvaluationResults and ExecutionTraces into structured,
    categorized FailureReports using the FailureTaxonomy with deterministic confidence.
    """

    def __init__(self) -> None:
        self._custom_mappers: list[
            Callable[[EvaluationResult, ExecutionTrace], FailureReport | None]
        ] = []

    def register_mapper(
        self,
        mapper: Callable[[EvaluationResult, ExecutionTrace], FailureReport | None],
    ) -> None:
        """Register a custom deterministic mapping function."""
        self._custom_mappers.insert(0, mapper)

    def analyze(
        self,
        trace: ExecutionTrace,
        evaluation_result: EvaluationResult,
        test_id: str | None = None,
    ) -> FailureReport:
        """Analyze a failed evaluation or trace and produce a FailureReport.

        Args:
            trace: The execution trace being analyzed.
            evaluation_result: The evaluation result (expected to have passed=False).
            test_id: Optional test case identifier.

        Returns:
            A populated FailureReport.
        """
        effective_test_id = test_id or trace.test_id

        # 1. Check custom mappers first
        for mapper in self._custom_mappers:
            custom_report = mapper(evaluation_result, trace)
            if custom_report is not None:
                return custom_report

        # 2. Check metadata on evaluation_result for explicit taxonomy overrides
        meta = evaluation_result.metadata or {}
        if "failure_type" in meta or "failure_category" in meta:
            cat = meta.get(
                "failure_category",
                FailureTaxonomy.get_category_for_type(meta.get("failure_type", ""))
                or FailureCategory.CUSTOM.value,
            )
            f_type = meta.get("failure_type", FailureType.CUSTOM.value)
            sev = meta.get("severity", FailureSeverity.HIGH)
            conf = meta.get("confidence", 1.0)
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=cat,
                type=f_type,
                severity=sev
                if isinstance(sev, FailureSeverity)
                else FailureSeverity(sev),
                message=evaluation_result.message or "Evaluation failed",
                evidence=evaluation_result.evidence,
                confidence=conf,
                metadata=meta,
            )

        # 3. Deterministic classifier based on evaluator name / structure
        evaluator_name = evaluation_result.evaluator.strip()

        # Tool assertions
        if evaluator_name.startswith("ToolCalled"):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.TOOL.value,
                type=FailureType.WRONG_TOOL.value,
                severity=FailureSeverity.HIGH,
                message=evaluation_result.message
                or f"Expected tool not called: {evaluator_name}",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        if evaluator_name.startswith("ToolNotCalled"):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.TOOL.value,
                type=FailureType.UNNECESSARY_TOOL.value,
                severity=FailureSeverity.HIGH,
                message=evaluation_result.message
                or f"Forbidden tool called: {evaluator_name}",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        if evaluator_name.startswith("ToolOrder"):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.TOOL.value,
                type=FailureType.WRONG_ORDER.value,
                severity=FailureSeverity.HIGH,
                message=evaluation_result.message or "Tool execution order violation",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        if evaluator_name.startswith("ToolArguments"):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.TOOL.value,
                type=FailureType.WRONG_ARGUMENT.value,
                severity=FailureSeverity.HIGH,
                message=evaluation_result.message or "Tool argument mismatch",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        # Output assertions
        if evaluator_name.startswith("SchemaMatch"):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.OUTPUT.value,
                type=FailureType.SCHEMA_ERROR.value,
                severity=FailureSeverity.HIGH,
                message=evaluation_result.message or "Output schema validation error",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        if evaluator_name.startswith("OutputEquals") or evaluator_name.startswith(
            "OutputContains"
        ):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.TASK.value,
                type=FailureType.TASK_INCORRECT.value,
                severity=FailureSeverity.MEDIUM,
                message=evaluation_result.message or "Task output assertion failed",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        # Performance assertions
        if evaluator_name.startswith("MaxLatency"):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.PERFORMANCE.value,
                type=FailureType.LATENCY.value,
                severity=FailureSeverity.MEDIUM,
                message=evaluation_result.message or "Max latency threshold exceeded",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        if evaluator_name.startswith("MaxCost"):
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.PERFORMANCE.value,
                type=FailureType.COST.value,
                severity=FailureSeverity.MEDIUM,
                message=evaluation_result.message or "Max cost threshold exceeded",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        # Safety assertions
        if "safety" in evaluator_name.lower():
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.SAFETY.value,
                type=FailureType.SAFETY_VIOLATION.value,
                severity=FailureSeverity.CRITICAL,
                message=evaluation_result.message or "Safety policy violation",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        # Retrieval assertions
        if "retrieval" in evaluator_name.lower() or "context" in evaluator_name.lower():
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.RETRIEVAL.value,
                type=FailureType.MISSING_CONTEXT.value,
                severity=FailureSeverity.MEDIUM,
                message=evaluation_result.message or "Retrieval context deficiency",
                evidence=evaluation_result.evidence,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        # Hallucination / Unsupported claims (confidence < 1.0 if heuristic/semantic)
        if "hallucination" in evaluator_name.lower():
            # If evidence has exact contradiction/proof, confidence is 1.0; else 0.85
            conf = (
                1.0
                if evaluation_result.evidence
                and evaluation_result.evidence.get("deterministic")
                else 0.85
            )
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.OUTPUT.value,
                type=FailureType.HALLUCINATION.value,
                severity=FailureSeverity.HIGH,
                message=evaluation_result.message or "Potential hallucination detected",
                evidence=evaluation_result.evidence,
                confidence=conf,
                metadata={"evaluator": evaluator_name},
            )

        # Semantic evaluators
        if (
            evaluator_name.startswith("Semantic")
            or "semantic" in evaluator_name.lower()
        ):
            conf = (
                evaluation_result.metadata.get("confidence")
                if evaluation_result.metadata
                else 0.85
            ) or 0.85
            sem_type = (
                FailureType.SEMANTIC_RELEVANCE.value
                if "relevance" in evaluator_name.lower()
                else (
                    FailureType.SEMANTIC_SIMILARITY.value
                    if "similarity" in evaluator_name.lower()
                    else FailureType.SEMANTIC_VIOLATION.value
                )
            )
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.OUTPUT.value,
                type=sem_type,
                severity=FailureSeverity.HIGH,
                message=evaluation_result.message or "Semantic evaluation failed",
                evidence=evaluation_result.evidence,
                confidence=float(conf),
                metadata={
                    "evaluator": evaluator_name,
                    **(evaluation_result.metadata or {}),
                },
            )

        # Execution runtime crash fallback
        if trace.status == ExecutionStatus.FAILED:
            return FailureReport(
                trace_id=trace.trace_id,
                test_id=effective_test_id,
                category=FailureCategory.TASK.value,
                type=FailureType.TASK_INCOMPLETE.value,
                severity=FailureSeverity.CRITICAL,
                message=evaluation_result.message
                or "Task execution terminated unexpectedly",
                evidence=evaluation_result.evidence or trace.output,
                confidence=1.0,
                metadata={"evaluator": evaluator_name},
            )

        # Default fallback
        return FailureReport(
            trace_id=trace.trace_id,
            test_id=effective_test_id,
            category=FailureCategory.TASK.value,
            type=FailureType.TASK_INCORRECT.value,
            severity=FailureSeverity.MEDIUM,
            message=evaluation_result.message or f"Evaluation {evaluator_name} failed",
            evidence=evaluation_result.evidence,
            confidence=1.0,
            metadata={"evaluator": evaluator_name},
        )

    def analyze_trace_failures(
        self,
        trace: ExecutionTrace,
        evaluation_results: list[EvaluationResult],
        test_id: str | None = None,
    ) -> list[FailureReport]:
        """Analyze all failures for a trace and its evaluation results."""
        reports: list[FailureReport] = []
        effective_test_id = test_id or trace.test_id

        # 1. Check trace execution failure
        if trace.status == ExecutionStatus.FAILED:
            err_msg = (
                trace.output.get("error")
                if isinstance(trace.output, dict) and "error" in trace.output
                else str(trace.output or "Execution failed")
            )
            reports.append(
                FailureReport(
                    trace_id=trace.trace_id,
                    test_id=effective_test_id,
                    category=FailureCategory.TASK.value,
                    type=FailureType.TASK_INCOMPLETE.value,
                    severity=FailureSeverity.CRITICAL,
                    message=f"Agent execution crashed: {err_msg}",
                    evidence=trace.output,
                    confidence=1.0,
                    metadata={"error": err_msg},
                )
            )

        # 2. Check each failed evaluation
        for ev in evaluation_results:
            if not ev.passed:
                reports.append(self.analyze(trace, ev, test_id=effective_test_id))

        return reports


__all__ = ["FailureAnalyzer"]
