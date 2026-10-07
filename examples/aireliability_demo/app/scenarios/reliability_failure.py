"""LLM reliability failure scenarios (empty response, hallucination, low quality)."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import FailureReport, FailureSeverity
from aireliability_demo.app.llm.deterministic import DeterministicLLM


def run_llm_failure_scenario(failure_type: str = "HALLUCINATION") -> dict[str, Any]:
    """Execute controlled LLM reliability failure and construct FailureReport."""
    llm = DeterministicLLM()
    output = llm.generate("Explain quantum convergence.", scenario=failure_type)

    failures: list[FailureReport] = []
    if failure_type.upper() == "EMPTY_RESPONSE" or not output:
        failures.append(
            FailureReport(
                failure_id="fail_empty_01",
                trace_id="tr_llm_empty",
                category="reliability",
                type="empty_output",
                message="LLM generated zero-length empty response",
                severity=FailureSeverity.HIGH,
                metadata={"component": "llm:generator"},
            )
        )
    elif failure_type.upper() == "HALLUCINATION":
        failures.append(
            FailureReport(
                failure_id="fail_halluc_01",
                trace_id="tr_llm_halluc",
                category="reliability",
                type="hallucination",
                message="Model generated ungrounded historical assertion (1842 quantum convergence)",
                severity=FailureSeverity.HIGH,
                metadata={"component": "llm:generator", "hallucination_score": 0.95},
            )
        )
    else:
        failures.append(
            FailureReport(
                failure_id="fail_qual_01",
                trace_id="tr_llm_qual",
                category="reliability",
                type="low_quality",
                message="Model generated ambiguous response failing coherence threshold",
                severity=FailureSeverity.MEDIUM,
                metadata={"component": "llm:generator"},
            )
        )

    return {
        "scenario": failure_type.upper(),
        "output": output,
        "failures": failures,
    }
