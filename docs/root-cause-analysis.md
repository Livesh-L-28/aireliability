# Evidence-Based Root Cause Analysis Specification

The **Evidence-Based Root Cause Analysis** subsystem (`aireliability.diagnosis`) determines the most likely operational cause of an AI agent failure using observable execution telemetry.

Rather than prompting an external LLM to guess "Why did this agent fail?", `RootCauseAnalyzer` inspects:
- `ExecutionTrace` (chronological steps, inputs, outputs, timestamps, errors)
- `TestCase` (expected behavior and constraints)
- `EvaluationResult` (assertion records, semantic judge rationales, criteria checks)
- `FailureReport` (classified failure categories and types)

and constructs a structured, evidence-backed diagnosis.

---

## 1. Core Principle: Evidence Over Speculation

> **Core Axiom**: Root-cause analysis identifies the most strongly supported failure explanation from observable execution evidence. It does not speculate on hidden model intentions or internal neural weights.

Every diagnosis is backed by explicit `Evidence` records:
- **Traceable to actual data**: Links directly to a trace step ID, property, expected value, and observed value.
- **Calibrated confidence**:
  - Deterministic violations (e.g. wrong tool, incorrect argument, sequence reversal): `confidence = 1.0`.
  - Semantic judge violations (e.g. relevance or similarity scores below threshold): preserves judge confidence (e.g. `0.85`).
  - Heuristic or fallback classifications: lower or explicit confidence values.

---

## 2. Architecture & Data Flow

```text
Agent Execution
       │
       ▼
ExecutionTrace (discrete TraceSteps)
       │
       ▼
Evaluators (Deterministic & Semantic)
       │
       ▼
FailureReport (FailureAnalyzer)
       │
       ▼
RootCauseAnalyzer (Deterministic Rules & Precedence)
       │
       ▼
RootCauseReport (Primary Cause, Secondary Causes, Causal Links)
       │
       ▼
RegressionGenerator (synthesizes RegressionTest preserving root_cause_id & evidence)
```

---

## 3. Data Models

### `Evidence`
Represents an individual verifiable observation:

```python
class Evidence(BaseModel):
    source: str  # 'execution_trace', 'evaluator_result', 'semantic_evaluator'
    trace_id: str | None  # Associated ExecutionTrace ID
    step_id: str | None  # Associated TraceStep ID
    field: str  # Attribute examined ('tool_name', 'tool_order', 'arguments')
    expected: Any  # Expected invariant or value
    actual: Any  # Observed actual value
    explanation: str  # Factual explanation of discrepancy
    metadata: dict[str, Any]  # Non-speculative telemetry
```

### `RootCause`
Structured diagnostic outcome:

```python
class RootCause(BaseModel):
    id: str
    category: (
        RootCauseCategory  # TOOL, OUTPUT, RETRIEVAL, MEMORY, PERFORMANCE, EXECUTION
    )
    type: RootCauseType  # WRONG_TOOL, WRONG_ARGUMENT, WRONG_ORDER, MISSING_TOOL, etc.
    description: str  # Concise summary of failure cause
    confidence: float  # 1.0 for deterministic, <=0.95 for semantic
    evidence: list[Evidence]  # Supporting evidence items
    affected_step: str | None  # Identifier of step triggering failure
    severity: FailureSeverity  # CRITICAL, HIGH, MEDIUM, LOW
    causal_links: list[CausalLink]  # Linked downstream effects
```

### `RootCauseReport`
Consolidated report detailing primary vs. secondary causes and terminal formatting:

```python
class RootCauseReport(BaseModel):
    id: str
    test_id: str | None
    trace_id: str | None
    status: str  # 'PASS' or 'FAIL'
    primary_cause: RootCause | None
    secondary_causes: list[RootCause]
    causal_chain: list[CausalLink]
    summary: str
```

---

## 4. Deterministic Precedence Rules for Multi-Failure Handling

When multiple failures co-occur in a single trace (e.g. wrong tool called, leading to schema validation failure and output mismatch), the engine does not collapse them into a vague error.

It evaluates deterministic precedence:
1. **Execution Crashes (`EXECUTION.EXCEPTION`)**: Unhandled exceptions immediately take highest precedence.
2. **Tool Selection & Invariants (`TOOL.*`)**: Upstream tool errors take precedence over downstream output discrepancies.
3. **Context & Retrieval (`RETRIEVAL.*`)**: Context deficiencies take precedence over resulting generation errors.
4. **Output Discrepancies (`OUTPUT.*`)**: Format and semantic violations.
5. **Resource Constraints (`PERFORMANCE.*`)**: Latency and token overruns.

---

## 5. Causal Links

Where the trace supports sequential dependency, causal links are constructed:

```text
Step 2: delete_order called instead of get_order
                   │
                   ▼ (causal link)
Final Output: Schema validation error / missing order summary
```

Represented as:
```python
CausalLink(
    source="step_delete_order",
    target="final_output",
    reason="Tool failure 'wrong_tool' at step_delete_order directly preceded discrepancy in final_output.",
)
```

---

## 6. Provenance & Regression Test Integration

When `RegressionGenerator` synthesizes a `RegressionTest`, it records the complete root-cause provenance:

$$\mathbf{RegressionTest} \xrightarrow{\text{root\_cause\_id}} \mathbf{RootCause} \xrightarrow{\text{evidence}} \mathbf{ExecutionTrace}$$

A developer can inspect `reg_test.metadata["root_cause_id"]` and `reg_test.metadata["root_cause_evidence"]` to understand exactly why the test exists without manually parsing historical logs.

---

## 7. Example Terminal Output

Running `airel failures --explain`:

```text
AI Reliability Root Cause Analysis
──────────────────────────────────
Test:    refund_flow
Status:  FAIL

Primary Detected Cause: TOOL.WRONG_ORDER
Confidence:             1.00
Description:            Tool sequence ordering violation: expected 'get_order → cancel_order → refund_order', observed 'get_order → refund_order → cancel_order'.
Affected Step:          step_2

Evidence:
  Expected: get_order → cancel_order → refund_order
  Actual:   get_order → refund_order → cancel_order
  Note:     Tools were executed in order 'get_order → refund_order → cancel_order' violating expected sequence 'get_order → cancel_order → refund_order'.
```

---

## 8. Current Limitations

1. **Observable Telemetry Only**: Root-cause analysis only reflects observable trace steps, inputs, outputs, and evaluator assertions. It cannot diagnose latent defects inside proprietary remote LLM weights.
2. **Heuristic Causal Chains**: In the absence of explicit DAG orchestration telemetry, causal links establish temporal and structural correlation rather than strict philosophical causation.
