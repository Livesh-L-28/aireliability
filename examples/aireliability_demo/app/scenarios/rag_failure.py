"""RAG failure scenarios (grounding failure, stale documents, conflicting context)."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import FailureReport, FailureSeverity
from aireliability_demo.app.rag.pipeline import RAGPipeline


def run_rag_failure_scenario(scenario: str = "GROUNDING_FAILURE") -> dict[str, Any]:
    """Execute controlled RAG failure scenario."""
    pipeline = RAGPipeline()
    rag_result = pipeline.run(
        "Explain the hard safety veto rule in AI reliability.",
        scenario=scenario,
    )

    failures: list[FailureReport] = []
    sc_upper = scenario.upper()

    if sc_upper == "GROUNDING_FAILURE":
        failures.append(
            FailureReport(
                failure_id="fail_rag_ground_01",
                trace_id="tr_rag_ground",
                category="rag",
                type="grounding_failure",
                message="Answer cited unsupported historical assertions not present in evidence",
                severity=FailureSeverity.HIGH,
                metadata={"component": "rag:grounding_evaluator"},
            )
        )
    elif sc_upper == "CONFLICTING_DOCUMENT":
        failures.append(
            FailureReport(
                failure_id="fail_rag_conf_01",
                trace_id="tr_rag_conf",
                category="rag",
                type="context_conflict",
                message="Retrieved documents present contradictory statements regarding safety veto rules",
                severity=FailureSeverity.HIGH,
                metadata={"component": "rag:context_analyzer"},
            )
        )
    elif sc_upper == "STALE_DOCUMENT":
        failures.append(
            FailureReport(
                failure_id="fail_rag_stale_01",
                trace_id="tr_rag_stale",
                category="rag",
                type="stale_knowledge",
                message="Retrieved document timestamps exceed maximum staleness threshold of 365 days",
                severity=FailureSeverity.MEDIUM,
                metadata={"component": "rag:freshness_tracker"},
            )
        )
    elif sc_upper == "MISSING_DOCUMENT":
        failures.append(
            FailureReport(
                failure_id="fail_rag_miss_01",
                trace_id="tr_rag_miss",
                category="rag",
                type="retrieval_empty",
                message="Knowledge base search yielded 0 documents for required query topic",
                severity=FailureSeverity.HIGH,
                metadata={"component": "rag:retriever"},
            )
        )

    return {
        "scenario": sc_upper,
        "rag_result": rag_result,
        "failures": failures,
    }
