"""Phase 36 Test Generation Bridge for Phase 40 Advanced Agent Reliability.

Connects agent trajectory failures directly to Phase 36 TestGenerationEngine.
Synthesizes targeted test suites covering:
- tool capability selection tests (from WRONG_TOOL)
- schema boundary tests (from INVALID_ARGUMENTS)
- repeated action regression tests (from LOOP_FAILURE / RUNAWAY_LOOP)
- constraint preservation tests (from GOAL_DRIFT)
- memory consistency tests (from MEMORY_FAILURE)
- multi-agent handoff tests (from AGENT_HANDOFF_FAILURE)
"""

from __future__ import annotations

import logging

from aireliability.agent.models import AgentRun
from aireliability.core.models import FailureReport
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.models import (
    GenerationStrategy,
    TestGenerationConfig,
    TestGenerationRequest,
    TestGenerationResult,
)

logger = logging.getLogger(__name__)


class AgentTestBridge:
    """Bridges diagnosed agent failures to the Phase 36 automated test generator."""

    def __init__(self, engine: TestGenerationEngine | None = None) -> None:
        self.engine = engine or TestGenerationEngine()

    def generate_agent_tests(
        self,
        run: AgentRun | list[AgentRun],
        max_tests: int = 5,
        seed: int = 42,
    ) -> TestGenerationResult:
        """Synthesize test cases from diagnosed agent failures."""
        reports: list[FailureReport] = []
        runs_list = run if isinstance(run, list) else [run]

        for r in runs_list:
            for f in r.failures:
                rep = FailureReport(
                    failure_id=f.failure_id,
                    trace_id=r.run_id,
                    category=f"agent_{f.stage.value}",
                    type=f.category.value,
                    message=f.message,
                    metadata={
                        "task": r.task.request_text,
                        "affected": f.affected_component,
                    },
                )
                reports.append(rep)

            if not reports:
                # Synthesize baseline behavioral regression tests if no failures
                reports.append(
                    FailureReport(
                        failure_id=f"agent_cov_{r.run_id[:8]}",
                        trace_id=r.run_id,
                        category="agent_coverage",
                        type="trajectory_invariant",
                        message=f"Generate agent trajectory invariant tests for task: {r.task.request_text[:80]}",
                        metadata={"task": r.task.request_text},
                    )
                )

        config = TestGenerationConfig(
            strategy=GenerationStrategy.AGENT_TRAJECTORY,
            max_tests=max_tests,
            random_seed=seed,
        )
        request = TestGenerationRequest(
            failure_reports=reports[:10],
            config=config,
            target_metric="agent_reliability",
        )
        return self.engine.generate(request)
