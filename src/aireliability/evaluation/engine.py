"""Unified evaluation engine orchestrating datasets, evaluators, and reporting."""

from __future__ import annotations

from aireliability.core.models import (
    EvaluationResult,
    FailureReport,
    RunResult,
)
from aireliability.core.protocols import Evaluator
from aireliability.diagnosis.analyzer import RootCauseAnalyzer
from aireliability.diagnosis.models import RootCauseReport
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.evaluation.models import (
    EvaluationReport,
    EvaluationRequest,
    MetricResult,
)
from aireliability.evaluation.registry import EvaluatorRegistry
from aireliability.execution.runner import ReliabilityRunner
from aireliability.failures.analyzer import FailureAnalyzer


class EvaluationEngine:
    """Unified evaluation engine orchestrating suites, evaluators, and metrics."""

    def __init__(
        self,
        failure_analyzer: FailureAnalyzer | None = None,
        root_cause_analyzer: RootCauseAnalyzer | None = None,
    ) -> None:
        self.failure_analyzer = failure_analyzer or FailureAnalyzer()
        self.root_cause_analyzer = root_cause_analyzer or RootCauseAnalyzer()

    def resolve_evaluators(
        self, evaluator_specs: list[str | Evaluator]
    ) -> list[Evaluator]:
        """Resolve string names or return already instantiated evaluators."""
        resolved: list[Evaluator] = []
        for spec in evaluator_specs:
            if isinstance(spec, str):
                resolved.append(EvaluatorRegistry.get(spec))
            else:
                resolved.append(spec)
        return resolved

    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        """Execute complete evaluation request and generate an EvaluationReport."""
        dataset = (
            request.dataset
            if isinstance(request.dataset, EvaluationDataset)
            else EvaluationDataset(name="Ad-hoc Dataset", test_cases=[])
        )

        evaluators = self.resolve_evaluators(request.evaluators)
        if getattr(request, "profile", None):
            from aireliability.evaluation.profiles import (
                EvaluationProfile,
                EvaluationProfileRegistry,
            )

            prof = request.profile
            if isinstance(prof, str) and EvaluationProfileRegistry.is_registered(prof):
                eval_prof = EvaluationProfileRegistry.get(prof)
                evaluators.extend(eval_prof.resolve_evaluators())
            elif isinstance(prof, EvaluationProfile):
                evaluators.extend(prof.resolve_evaluators())

        all_eval_results: list[EvaluationResult] = []
        all_failures: list[FailureReport] = []
        all_root_causes: list[RootCauseReport] = []
        passed_test_cases = 0
        failed_test_cases = 0

        # Case 1: Evaluate agent against test cases
        if request.target.agent is not None:
            runner = ReliabilityRunner(
                agent=request.target.agent,
                evaluators=evaluators,
                failure_analyzer=self.failure_analyzer,
                suppress_agent_exceptions=True,
            )
            for tc in dataset.test_cases:
                run_res: RunResult = runner.run(tc)
                all_eval_results.extend(run_res.evaluations)
                all_failures.extend(run_res.failures)

                if run_res.failures:
                    rc_report = self.root_cause_analyzer.diagnose(
                        run_res.trace, failures=run_res.failures, test_case=tc
                    )
                    all_root_causes.append(rc_report)

                if run_res.passed:
                    passed_test_cases += 1
                else:
                    failed_test_cases += 1

        # Case 2: Evaluate pre-recorded traces
        elif request.target.traces:
            trace_map = {t.test_id: t for t in request.target.traces if t.test_id}
            for tc in dataset.test_cases:
                trace = trace_map.get(tc.id, request.target.traces[0])
                case_passed = True
                for ev in evaluators:
                    res = ev.evaluate(trace, tc)
                    all_eval_results.append(res)
                    if not res.passed:
                        case_passed = False
                        f_report = self.failure_analyzer.analyze(trace, res, tc.id)
                        all_failures.append(f_report)
                        rc_report = self.root_cause_analyzer.diagnose(
                            trace, failures=[f_report], test_case=tc
                        )
                        all_root_causes.append(rc_report)

                if case_passed:
                    passed_test_cases += 1
                else:
                    failed_test_cases += 1

        # Compute metric aggregates
        metrics: dict[str, MetricResult] = {}
        metric_scores: dict[str, list[float]] = {}
        for ev in all_eval_results:
            m_name = ev.metric or ev.evaluator
            if ev.score is not None:
                metric_scores.setdefault(m_name, []).append(ev.score)

        for m_name, scores in metric_scores.items():
            avg_score = sum(scores) / len(scores)
            metrics[m_name] = MetricResult(
                name=m_name,
                value=round(avg_score, 4),
                sample_count=len(scores),
            )

        recommendations: list[str] = []
        if failed_test_cases > 0:
            recommendations.append(
                f"{failed_test_cases} test cases failed. Review attached root causes for remediation."
            )

        return EvaluationReport(
            request_id=request.request_id,
            target_name=request.target.name,
            dataset_id=dataset.id,
            total_test_cases=len(dataset.test_cases),
            passed_test_cases=passed_test_cases,
            failed_test_cases=failed_test_cases,
            evaluations=all_eval_results,
            metrics=metrics,
            failures=all_failures,
            root_causes=all_root_causes,
            recommendations=recommendations,
        )
