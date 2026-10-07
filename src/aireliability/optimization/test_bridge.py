"""Integration bridge requesting Phase 36 test generation for parameter edge cases."""

from __future__ import annotations

import logging

from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.models import GeneratedTest, TestGenerationRequest
from aireliability.optimization.models import (
    OptimizationCandidate,
    OptimizationProblem,
)

logger = logging.getLogger(__name__)


class OptimizationTestBridge:
    """Couples optimization with Phase 36 TestGenerationEngine for validation suites."""

    def __init__(
        self, test_generation_engine: TestGenerationEngine | None = None
    ) -> None:
        self.test_generation_engine = test_generation_engine or TestGenerationEngine()

    def request_validation_tests(
        self,
        candidate: OptimizationCandidate,
        problem: OptimizationProblem,
        max_tests: int = 3,
    ) -> list[GeneratedTest]:
        """Synthesize targeted edge-case tests reflecting parameter modifications."""
        modified_keys = []
        base_vals = problem.baseline_config.values
        cand_vals = candidate.configuration.values

        for k, v in cand_vals.items():
            if k not in base_vals or base_vals[k] != v:
                modified_keys.append(k)

        # Build focused request
        focus_desc = f"Parameter optimization modification: {', '.join(modified_keys) or 'general config'}"

        try:
            req = TestGenerationRequest(
                max_tests=max_tests,
                tags=["phase38", "optimization_validation"] + modified_keys[:3],
                metadata={
                    "candidate_id": candidate.candidate_id,
                    "problem_id": problem.problem_id,
                    "focus": focus_desc,
                },
            )
            report = self.test_generation_engine.generate(req)
            logger.info(
                "Phase 36 synthesized %d validation tests for candidate %s",
                len(report.tests),
                candidate.candidate_id,
            )
            return report.tests
        except Exception as exc:
            logger.warning(
                "Phase 36 test synthesis encountered exception, returning empty suite: %s",
                exc,
            )
            return []
