"""Continuous reliability monitoring and automated regression harvesting pipeline."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence
from pathlib import Path

from aireliability.core.models import (
    EvaluationResult,
    ExecutionTrace,
    FailureReport,
    RegressionTest,
    TestCase,
)
from aireliability.diagnosis.analyzer import RootCauseAnalyzer
from aireliability.evaluation.datasets.manager import DatasetManager
from aireliability.evaluation.datasets.models import EvaluationDataset
from aireliability.evaluation.governance.scoring import (
    ReliabilityScoringEngine,
    UnifiedReliabilityScore,
)
from aireliability.evaluation.models import EvaluationReport
from aireliability.observability.incidents import IncidentManager, IncidentRecord
from aireliability.regression.generator import RegressionGenerator


class ContinuousReliabilityMonitor:
    """Sliding-window continuous reliability scoring from live execution traces and results."""

    def __init__(
        self,
        window_size: int = 100,
        max_age_seconds: float = 3600.0,
        scoring_engine: ReliabilityScoringEngine | None = None,
        incident_manager: IncidentManager | None = None,
    ) -> None:
        self.window_size = window_size
        self.max_age_seconds = max_age_seconds
        self.scoring_engine = scoring_engine or ReliabilityScoringEngine()
        self.incident_manager = incident_manager
        self._history: deque[tuple[float, EvaluationResult]] = deque()

    def record(self, results: Sequence[EvaluationResult]) -> None:
        """Record batch of evaluation results with current timestamp."""
        now = time.time()
        for res in results:
            self._history.append((now, res))
        self._prune(now)

    def _prune(self, current_time: float) -> None:
        """Prune items exceeding window size or max age."""
        cutoff = current_time - self.max_age_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()
        while len(self._history) > self.window_size:
            self._history.popleft()

    @property
    def current_results(self) -> list[EvaluationResult]:
        """Return all active results within the current sliding window."""
        self._prune(time.time())
        return [res for _, res in self._history]

    def current_score(self) -> UnifiedReliabilityScore:
        """Compute the unified reliability score over the current sliding window."""
        results = self.current_results
        report = EvaluationReport(
            target_name="ProductionStream",
            dataset_id="live_window",
            evaluations=results,
            passed=all(r.passed for r in results) if results else True,
            passed_test_cases=sum(1 for r in results if r.passed),
            failed_test_cases=sum(1 for r in results if not r.passed),
            total_test_cases=len(results),
        )
        return self.scoring_engine.calculate(report)

    def is_healthy(self, min_score: float = 0.8) -> bool:
        """Check if current continuous score meets reliability threshold without veto."""
        score = self.current_score()
        return not score.veto_triggered and score.composite_score >= min_score


class ProductionRegressionHarvester:
    """Automated pipeline from production failures to golden regression dataset.

    Flow:
    Production Trace -> Failure Detection -> Root Cause Diagnosis ->
    Regression Test Synthesis -> Golden Dataset Insertion.
    """

    def __init__(
        self,
        golden_dataset: EvaluationDataset | Path | str | None = None,
        analyzer: RootCauseAnalyzer | None = None,
        generator: RegressionGenerator | None = None,
        auto_save_path: Path | str | None = None,
        incident_manager: IncidentManager | None = None,
    ) -> None:
        if isinstance(golden_dataset, (Path, str)):
            self.golden_dataset = DatasetManager.load(golden_dataset)
            self.auto_save_path = Path(golden_dataset)
        elif isinstance(golden_dataset, EvaluationDataset):
            self.golden_dataset = golden_dataset
            self.auto_save_path = Path(auto_save_path) if auto_save_path else None
        else:
            self.golden_dataset = EvaluationDataset(
                id="golden_regressions",
                name="Production Golden Regressions",
                description="Automatically harvested regression test cases from production failures.",
            )
            self.auto_save_path = Path(auto_save_path) if auto_save_path else None

        self.analyzer = analyzer or RootCauseAnalyzer()
        self.generator = generator or RegressionGenerator()
        self.incident_manager = incident_manager
        self.harvested_cases: list[TestCase] = []
        self.created_incidents: list[IncidentRecord] = []

    def harvest_from_trace(
        self,
        trace: ExecutionTrace,
        failures: list[FailureReport],
        test_case: TestCase | None = None,
        evaluations: Sequence[EvaluationResult] | None = None,
        dataset_split: str = "test",
        create_incidents: bool = True,
    ) -> list[TestCase]:
        """Process a production failure, diagnose root cause, synthesize regression tests, and store."""
        if not failures:
            return []

        base_tc = test_case or TestCase(
            id=trace.test_id or f"trace_{trace.trace_id[:8]}",
            name=f"prod_case_{trace.trace_id[:8]}",
            input=trace.input,
            expected_output=None,
        )

        # 1. Diagnose Root Causes
        root_cause_report = self.analyzer.diagnose(
            trace=trace,
            failures=failures,
            test_case=base_tc,
            evaluations=evaluations,
        )

        primary_cause = root_cause_report.primary_cause
        added_cases: list[TestCase] = []

        # 2. Synthesize Regression Tests
        for failure in failures:
            reg_test: RegressionTest = self.generator.generate(
                failure=failure,
                test_case=base_tc,
                root_cause=primary_cause,
                additional_tags=[
                    "production_harvest",
                    f"failure:{getattr(failure.category, 'value', failure.category)}",
                ],
                metadata={
                    "trace_id": trace.trace_id,
                    "failure_id": failure.failure_id,
                    "root_cause_summary": (
                        getattr(
                            primary_cause,
                            "description",
                            getattr(primary_cause, "summary", "Unclassified"),
                        )
                        if primary_cause
                        else "Unclassified"
                    ),
                },
            )

            # Convert RegressionTest to TestCase suitable for EvaluationDataset
            underlying_tc = reg_test.test_case
            harvested_tc = TestCase(
                id=f"harvest_{reg_test.id}",
                name=f"Regression: {reg_test.name}",
                input=underlying_tc.input,
                expected_output=underlying_tc.expected_output,
                expectations=list(underlying_tc.expectations),
                tags=list(set(underlying_tc.tags + ["production_regression"])),
                metadata={
                    "provenance": reg_test.metadata,
                    "source_trace_id": trace.trace_id,
                    "harvested_at": time.time(),
                },
            )

            # Check duplication in existing golden dataset
            existing_ids = {tc.id for tc in self.golden_dataset.test_cases}
            if harvested_tc.id not in existing_ids:
                self.golden_dataset = self.golden_dataset.add_test_case(harvested_tc)
                self.harvested_cases.append(harvested_tc)
                added_cases.append(harvested_tc)

            # 3. If IncidentManager configured, register operational incident
            if self.incident_manager and create_incidents:
                cat_val = getattr(
                    failure.category, "value", str(failure.category)
                ).lower()
                sev = "CRITICAL" if cat_val in ("safety", "security") else "HIGH"
                inc = self.incident_manager.create_incident(
                    title=f"Production Evaluation Failure: {cat_val.upper()}",
                    description=failure.message
                    or f"Failure detected on trace {trace.trace_id}",
                    severity=sev,
                    trace_ids=[trace.trace_id],
                    execution_ids=[trace.test_id] if trace.test_id else [],
                    metadata={
                        "failure_id": failure.failure_id,
                        "category": cat_val,
                        "root_cause": (
                            getattr(
                                primary_cause,
                                "description",
                                getattr(primary_cause, "summary", "Unclassified"),
                            )
                            if primary_cause
                            else "Unclassified"
                        ),
                    },
                )
                self.created_incidents.append(inc)

        # 4. Persist dataset if path configured
        if self.auto_save_path and added_cases:
            DatasetManager.save(self.golden_dataset, self.auto_save_path)

        return added_cases

    def get_dataset(self) -> EvaluationDataset:
        """Return the accumulated golden dataset."""
        return self.golden_dataset
