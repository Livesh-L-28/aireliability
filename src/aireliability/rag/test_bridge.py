"""Phase 36 Test Generation Bridge synthesizing targeted RAG edge cases and regression tests."""

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
from aireliability.rag.models import RAGRun

logger = logging.getLogger(__name__)


class RAGTestBridge:
    """Connects RAG failures to Phase 36 Test Generation Engine to synthesize validation suites."""

    def __init__(self, engine: TestGenerationEngine | None = None) -> None:
        self.engine = engine or TestGenerationEngine()

    def generate_rag_tests(
        self,
        run: RAGRun | list[RAGRun],
        max_tests: int = 5,
        seed: int = 42,
    ) -> TestGenerationResult:
        """Synthesize targeted RAG edge case and robustness tests from observed failures."""
        reports: list[FailureReport] = []
        runs_list = run if isinstance(run, list) else [run]

        for r in runs_list:
            for f in r.failures:
                rep = FailureReport(
                    failure_id=f.failure_id,
                    trace_id=r.run_id,
                    category=f"rag_{f.stage.value}",
                    type=f.category.value,
                    message=f.message,
                    metadata={"query": r.query.text},
                )
                reports.append(rep)

            # If no explicit failures, create baseline report from query to synthesize general RAG tests
            if not reports:
                reports.append(
                    FailureReport(
                        failure_id=f"rag_cov_{r.run_id[:8]}",
                        trace_id=r.run_id,
                        category="rag_coverage",
                        type="missing_evidence",
                        message=f"Generate RAG coverage edge cases for query: {r.query.text}",
                        metadata={"query": r.query.text},
                    )
                )

        req = TestGenerationRequest(
            sources=reports,
            strategies=[GenerationStrategy.RAG_FOCUSED, GenerationStrategy.ROBUSTNESS],
            config=TestGenerationConfig(
                max_candidates=max_tests,
                deterministic_seed=seed,
            ),
        )

        return self.engine.generate(req)
