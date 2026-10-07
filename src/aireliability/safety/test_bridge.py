"""Test Generation Bridge for AI Safety Validation (Phase 41 -> Phase 36)."""

from __future__ import annotations

import logging

from aireliability.core.models import FailureReport
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.models import (
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
    TestGenerationResult,
)
from aireliability.safety.models import SafetyFinding, SafetyVerdict

logger = logging.getLogger(__name__)


class SafetyTestBridge:
    """Bridges diagnosed safety findings to the Phase 36 automated test generator."""

    def __init__(self, engine: TestGenerationEngine | None = None) -> None:
        self.engine = engine or TestGenerationEngine()

    def generate_safety_tests(
        self,
        findings: list[SafetyFinding],
        max_tests: int = 5,
        seed: int = 42,
    ) -> TestGenerationResult:
        """Synthesize regression test cases from diagnosed safety findings."""
        reports: list[FailureReport] = []

        for f in findings:
            if f.verdict == SafetyVerdict.UNSAFE:
                reports.append(
                    FailureReport(
                        failure_id=f.finding_id,
                        trace_id=f.test_id,
                        run_id=f.test_id,
                        test_case_id=f.test_id,
                        category=f.category.value,
                        error_message=f.message,
                        details={
                            "severity": f.severity.value,
                            "risk": f.risk_dimension.value,
                        },
                    )
                )

        if not reports:
            reports.append(
                FailureReport(
                    failure_id="safe_baseline",
                    trace_id="safe_baseline",
                    run_id="safe_baseline",
                    test_case_id="safe_baseline",
                    category="INSTRUCTION_BOUNDARY",
                    error_message="Proactive boundary validation probe",
                )
            )

        config = TestGenerationConfig(
            strategy=GenerationStrategy.BOUNDARY_VALUE,
            max_tests=max_tests,
            random_seed=seed,
            target_framework="pytest",
        )
        request = TestGenerationRequest(
            failure_reports=reports,
            config=config,
        )
        return self.engine.generate(request)
