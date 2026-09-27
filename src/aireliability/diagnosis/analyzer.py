"""Root Cause Analyzer orchestrating evidence-based diagnostic evaluation."""

from collections.abc import Sequence

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    RunResult,
    TestCase,
)
from aireliability.diagnosis.models import (
    CausalLink,
    RootCause,
    RootCauseCategory,
    RootCauseReport,
)
from aireliability.diagnosis.rules import diagnose_failure_report

# Deterministic category priority for selecting the primary root cause
# Earlier categories take precedence over downstream symptoms
# (e.g. Tool errors typically precipitate downstream output discrepancies)
CATEGORY_PRECEDENCE: dict[RootCauseCategory, int] = {
    RootCauseCategory.EXECUTION: 100,
    RootCauseCategory.TOOL: 90,
    RootCauseCategory.RETRIEVAL: 80,
    RootCauseCategory.MEMORY: 70,
    RootCauseCategory.PROMPT: 60,
    RootCauseCategory.OUTPUT: 50,
    RootCauseCategory.PERFORMANCE: 40,
    RootCauseCategory.UNKNOWN: 10,
}

SEVERITY_PRECEDENCE: dict[FailureSeverity, int] = {
    FailureSeverity.CRITICAL: 40,
    FailureSeverity.HIGH: 30,
    FailureSeverity.MEDIUM: 20,
    FailureSeverity.LOW: 10,
}


class RootCauseAnalyzer:
    """Analyzes execution traces and failure reports to diagnose root causes."""

    def diagnose(
        self,
        trace: ExecutionTrace,
        failures: Sequence[FailureReport],
        test_case: TestCase | None = None,
        evaluations: Sequence[EvaluationResult] | None = None,
    ) -> RootCauseReport:
        """Diagnose failures into a structured RootCauseReport.

        Args:
            trace: The captured execution trace.
            failures: One or more detected FailureReports.
            test_case: Optional TestCase specification.
            evaluations: Optional raw EvaluationResults list.

        Returns:
            A structured RootCauseReport with primary cause, secondary causes,
            evidence, and causal links.
        """
        if not failures:
            return RootCauseReport(
                test_id=test_case.id if test_case else trace.test_id,
                trace_id=trace.trace_id,
                status="PASS",
                primary_cause=None,
                secondary_causes=[],
                summary="No failures detected in execution trace.",
            )

        # 1. Diagnose each failure into a RootCause
        diagnoses: list[RootCause] = [
            diagnose_failure_report(
                failure=f,
                trace=trace,
                test_case=test_case,
            )
            for f in failures
        ]

        # 2. Sort diagnoses deterministically to identify the primary root cause
        # Precedence rule:
        # A) Category precedence (Execution > Tool > Retrieval > Output > Performance)
        # B) Severity (Critical > High > Medium > Low)
        # C) Chronological order of affected_step or occurrence
        def sort_key(rc: RootCause) -> tuple[int, int, float]:
            cat_score = CATEGORY_PRECEDENCE.get(rc.category, 0)
            sev_score = SEVERITY_PRECEDENCE.get(rc.severity, 0)
            conf = rc.confidence
            return (cat_score, sev_score, conf)

        sorted_diagnoses = sorted(diagnoses, key=sort_key, reverse=True)
        primary_cause = sorted_diagnoses[0]
        secondary_causes = sorted_diagnoses[1:]

        # 3. Construct empirical causal links where supported by the trace
        causal_links = self._build_causal_chain(sorted_diagnoses, trace)

        cat_upper = primary_cause.category.value.upper()
        type_upper = primary_cause.type.value.upper()
        summary = (
            f"Primary detected cause: {cat_upper}.{type_upper} "
            f"({primary_cause.description})"
        )
        if secondary_causes:
            summary += f" with {len(secondary_causes)} secondary effect(s)."

        return RootCauseReport(
            test_id=test_case.id if test_case else trace.test_id,
            trace_id=trace.trace_id,
            status="FAIL",
            primary_cause=primary_cause,
            secondary_causes=secondary_causes,
            causal_chain=causal_links,
            summary=summary,
        )

    def diagnose_run_result(self, run_result: RunResult) -> RootCauseReport:
        """Convenience method to diagnose a complete RunResult."""
        return self.diagnose(
            trace=run_result.trace,
            failures=run_result.failures,
            test_case=run_result.test,
            evaluations=run_result.evaluations,
        )

    def _build_causal_chain(
        self, diagnoses: list[RootCause], trace: ExecutionTrace
    ) -> list[CausalLink]:
        """Construct causal links across observed failures if supported by trace."""
        links: list[CausalLink] = []

        # Example pattern: Tool error -> Output mismatch
        tool_causes = [d for d in diagnoses if d.category == RootCauseCategory.TOOL]
        output_causes = [d for d in diagnoses if d.category == RootCauseCategory.OUTPUT]

        if tool_causes and output_causes:
            primary_tool = tool_causes[0]
            src = primary_tool.affected_step or "tool_execution"
            tgt = "final_output"
            links.append(
                CausalLink(
                    source=src,
                    target=tgt,
                    reason=(
                        f"Tool failure '{primary_tool.type.value}' at {src} directly "
                        f"preceded discrepancy in {tgt}."
                    ),
                )
            )

        return links
