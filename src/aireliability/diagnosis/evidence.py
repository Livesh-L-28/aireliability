"""Evidence representation and models for root-cause diagnosis."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    """Structured, traceable piece of evidence supporting a root cause diagnosis.

    Attributes:
        source: Origin of evidence ('execution_trace', 'evaluator_result', etc.).
        trace_id: Identifier of the associated ExecutionTrace if available.
        step_id: Identifier of the discrete TraceStep where the anomaly occurred.
        field: Specific attribute examined (e.g. 'tool_name', 'latency_ms').
        expected: Expected value or invariant constraint.
        actual: Observed actual value or output.
        explanation: Human-readable factual explanation of the observed discrepancy.
        metadata: Arbitrary additional context without speculative inferences.
    """

    model_config = ConfigDict(frozen=True)

    source: str = "execution_trace"
    trace_id: str | None = None
    step_id: str | None = None
    field: str = ""
    expected: Any = None
    actual: Any = None
    explanation: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
