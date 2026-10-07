"""Multidimensional regression detection and end-to-end provenance synthesis."""

from __future__ import annotations

from aireliability.core.models import (
    EvaluationResult,
    FailureReport,
    FailureSeverity,
    RunResult,
)
from aireliability.diagnosis.analyzer import RootCauseAnalyzer
from aireliability.evaluation.regression.models import (
    ComprehensiveRegressionSummary,
    DimensionalRegression,
    RegressionDimension,
)
from aireliability.failures.taxonomy import FailureCategory, FailureType
from aireliability.regression.baseline import BaselineEntry
from aireliability.regression.generator import RegressionGenerator


def _score_for_dimension(res: RunResult, dim: RegressionDimension) -> float:
    """Extract a representative score [0.0, 1.0] for a given dimension from RunResult."""
    if dim == RegressionDimension.LATENCY:
        # Lower latency is better: invert or evaluate boundary
        lat = res.trace.latency_ms or 0.0
        # Normalization heuristic: 1000ms is 0.5, 0ms is 1.0
        return max(0.0, min(1.0, 1.0 - (lat / 2000.0)))

    if dim == RegressionDimension.COST:
        cost = res.trace.cost or 0.0
        return max(0.0, min(1.0, 1.0 - (cost / 0.10)))

    # Look through evaluation results
    matching_evals: list[EvaluationResult] = []
    for ev in res.evaluations:
        ev_name = ev.evaluator.lower()
        metric_name = (ev.metric or "").lower()

        if (
            dim == RegressionDimension.RETRIEVAL
            and ("retriev" in ev_name or "ndcg" in metric_name)
            or dim == RegressionDimension.SAFETY
            and ("safety" in ev_name or "security" in ev_name)
            or dim == RegressionDimension.TOOL
            and ("tool" in ev_name)
            or dim == RegressionDimension.HALLUCINATION
            and ("hallucinat" in ev_name or "hallucinat" in metric_name)
            or dim == RegressionDimension.GROUNDEDNESS
            and ("ground" in ev_name or "ground" in metric_name)
            or dim == RegressionDimension.FAITHFULNESS
            and ("faith" in ev_name or "faith" in metric_name)
            or dim == RegressionDimension.QUALITY
        ):
            matching_evals.append(ev)

    if not matching_evals:
        return 1.0 if res.passed else 0.0

    scores = [ev.score for ev in matching_evals if ev.score is not None]
    if not scores:
        return 1.0 if all(ev.passed for ev in matching_evals) else 0.0
    return sum(scores) / len(scores)


class EvaluationRegressionDetector:
    """Detects multidimensional regressions between baseline and current evaluation suites."""

    def __init__(
        self,
        *,
        max_allowed_score_drop: float = 0.05,
        min_score_drop: float | None = None,
        root_cause_analyzer: RootCauseAnalyzer | None = None,
        regression_generator: RegressionGenerator | None = None,
    ) -> None:
        self.max_allowed_score_drop = (
            min_score_drop if min_score_drop is not None else max_allowed_score_drop
        )
        self.root_cause_analyzer = root_cause_analyzer or RootCauseAnalyzer()
        self.regression_generator = regression_generator or RegressionGenerator()

    def compare_runs(
        self,
        baseline_results: list[RunResult] | dict[str, BaselineEntry],
        current_results: list[RunResult],
        dimensions: list[RegressionDimension] | None = None,
    ) -> ComprehensiveRegressionSummary:
        """Compare current run results against baseline across specified dimensions."""
        dims = dimensions or [
            RegressionDimension.QUALITY,
            RegressionDimension.RETRIEVAL,
            RegressionDimension.SAFETY,
            RegressionDimension.LATENCY,
            RegressionDimension.COST,
            RegressionDimension.TOOL,
            RegressionDimension.HALLUCINATION,
            RegressionDimension.GROUNDEDNESS,
            RegressionDimension.FAITHFULNESS,
        ]

        # Normalize baseline lookup map
        baseline_map: dict[str, RunResult] = {}
        if isinstance(baseline_results, dict):
            for k, entry in baseline_results.items():
                baseline_map[k] = entry.run_result
        else:
            for r in baseline_results:
                baseline_map[r.test.id] = r

        regressions: list[DimensionalRegression] = []
        dim_breakdown: dict[str, int] = {d.value: 0 for d in dims}
        passing_count = 0
        fixed_count = 0

        for cur in current_results:
            base = baseline_map.get(cur.test.id)
            if not base:
                if cur.passed:
                    passing_count += 1
                continue

            # Standard pass/fail baseline checks
            if not base.passed and cur.passed:
                fixed_count += 1
            elif cur.passed:
                passing_count += 1

            # Check each dimension for drop
            for dim in dims:
                base_score = _score_for_dimension(base, dim)
                cur_score = _score_for_dimension(cur, dim)
                delta = cur_score - base_score

                # Drop exceeds threshold
                if delta < -self.max_allowed_score_drop:
                    dim_breakdown[dim.value] += 1
                    msg = (
                        f"Regression detected in {dim.value.upper()}: score dropped from "
                        f"{base_score:.3f} to {cur_score:.3f} (delta: {delta:+.3f}, max allowed: {-self.max_allowed_score_drop:.3f})."
                    )

                    # Synthesize failure report
                    fail_cat = FailureCategory.TASK.value
                    fail_type = FailureType.TASK_INCORRECT.value
                    if dim == RegressionDimension.RETRIEVAL:
                        fail_cat = FailureCategory.RETRIEVAL.value
                        fail_type = FailureType.MISSING_CONTEXT.value
                    elif dim == RegressionDimension.SAFETY:
                        fail_cat = FailureCategory.SAFETY.value
                        fail_type = FailureType.SAFETY_VIOLATION.value
                    elif dim == RegressionDimension.TOOL:
                        fail_cat = FailureCategory.TOOL.value
                        fail_type = FailureType.WRONG_TOOL.value
                    elif dim in (
                        RegressionDimension.HALLUCINATION,
                        RegressionDimension.GROUNDEDNESS,
                    ):
                        fail_cat = FailureCategory.OUTPUT.value
                        fail_type = FailureType.HALLUCINATION.value
                    elif dim == RegressionDimension.LATENCY:
                        fail_cat = FailureCategory.PERFORMANCE.value
                        fail_type = FailureType.LATENCY.value
                    elif dim == RegressionDimension.COST:
                        fail_cat = FailureCategory.PERFORMANCE.value
                        fail_type = FailureType.COST.value

                    evidence_payload = {
                        "baseline_score": base_score,
                        "current_score": cur_score,
                        "delta": delta,
                        "max_latency_ms": 1000.0,
                        "actual_latency_ms": cur.trace.latency_ms or 0.0,
                    }
                    f_report = FailureReport(
                        trace_id=cur.trace.trace_id,
                        test_id=cur.test.id,
                        category=fail_cat,
                        type=fail_type,
                        severity=FailureSeverity.HIGH,
                        message=msg,
                        evidence=evidence_payload,
                    )

                    # Perform root-cause diagnosis
                    rc_report = self.root_cause_analyzer.diagnose(
                        cur.trace, failures=[f_report]
                    )

                    # Synthesize regression test test case
                    reg_test = self.regression_generator.generate(f_report, cur.test)

                    regressions.append(
                        DimensionalRegression(
                            test_id=cur.test.id,
                            test_name=cur.test.name,
                            dimension=dim,
                            baseline_score=round(base_score, 4),
                            current_score=round(cur_score, 4),
                            delta=round(delta, 4),
                            message=msg,
                            failure_report=f_report,
                            root_cause=rc_report,
                            regression_test=reg_test,
                        )
                    )

        regressed_tests = len({r.test_id for r in regressions})

        return ComprehensiveRegressionSummary(
            total_tests=len(current_results),
            passing_tests=passing_count,
            regressed_tests=regressed_tests,
            fixed_tests=fixed_count,
            regressions=regressions,
            dimension_breakdown=dim_breakdown,
        )
