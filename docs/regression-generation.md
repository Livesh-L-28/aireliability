# Intelligent Regression Generation

`aireliability` provides an intelligent, evidence-based regression synthesis pipeline that converts detected failures into **minimal, explainable, and reproducible regression test cases** without using an LLM.

---

## 1. Core Architecture

The synthesis pipeline operates downstream of root-cause analysis and directly upstream of regression execution:

```text
Faulty Agent Execution
          ↓
   ExecutionTrace
          ↓
  Evaluation Engine (Deterministic + Semantic)
          ↓
    FailureReport
          ↓
  RootCauseAnalyzer
          ↓
   RootCauseReport
          ↓
RegressionSynthesizer
    ├── RegressionMinimizer (Conservative Input & Trace Pruning)
    ├── Specific Assertion Formulator (Failure-Type-Aware)
    └── Quality & Duplicate Validator
          ↓
 Validated RegressionCandidate (or DUPLICATE / INSUFFICIENT_EVIDENCE)
          ↓
    RegressionTest
          ↓
   RegressionRunner (Validation against Baselines)
```

---

## 2. Minimal Regression Principle

A failure in an AI workflow often occurs within a long trajectory of unrelated background steps (telemetry, greetings, session caching, metrics). Retaining the entire original execution trace bloats regression suites and obscures the essential bug.

The **minimal regression principle** dictates:
* The regression test must contain the smallest useful representation necessary to reproduce the failure.
* Retain the critical tool sequences, arguments, outputs, or semantic criteria.
* Prune unreferenced input fields and extraneous trace steps.
* **Safety First**: Minimization is conservative. If dependency between input fields or steps cannot be proven from observable execution evidence or test specifications, the system preserves the original data.

---

## 3. Failure-Type-Aware Generation

Regression synthesis constructs assertions specifically tailored to the diagnosed failure category and type:

| Failure Type | Synthesized Expectations & Metadata | Provenance & Invariants |
| :--- | :--- | :--- |
| **`TOOL.WRONG_TOOL`** | `ToolCalled:<expected_tool>` | Asserts required tool invocation; rejects substitutions |
| **`TOOL.WRONG_ARGUMENT`** | `ToolArguments:<tool>` + `expected_arguments` | Asserts target parameters without asserting unrelated metadata |
| **`TOOL.WRONG_ORDER`** | `ToolOrder:<seq_1>,<seq_2>,...` | Captures sequence order without requiring exact match on irrelevant intermediate tools |
| **`TOOL.MISSING_TOOL`** | `ToolCalled:<required_tool>` | Asserts omitted tool was invoked |
| **`OUTPUT.UNEXPECTED_OUTPUT`** | `OutputEquals:<expected_output>` | Exact or structural output match |
| **`OUTPUT.SEMANTIC_MISMATCH`** | `SemanticMatch:threshold=<t>` + `criteria` + `reference` | Preserves semantic criteria, judge rationale, and threshold without coercing to string equality |
| **`PERFORMANCE.LATENCY_REGRESSION`** | `MaxLatency:<target_ms>` | Retains performance budget constraints |

---

## 4. Conservative Minimization

### Input Minimization
When an input dictionary contains multiple attributes:
```python
original_input = {
    "order_id": "ORD-123",
    "session_id": "sess_98234",
    "user_agent": "Mozilla/5.0",
    "debug_trace": True,
}
```
If the diagnosed root cause evidence only references `order_id`:
```python
minimized_input = {"order_id": "ORD-123"}
```
If no specific key can be established from evidence, the minimizer retains the full input payload safely.

### Trace Step Minimization
Steps in an `ExecutionTrace` are filtered by checking:
1. Did the step trigger an `affected_step` in the root cause?
2. Did the step call a relevant tool identified in root cause evidence?
3. Is the step part of an established causal sequence (`CausalLink`)?

If pruning would remove all steps or no tools are identified, the complete step history is preserved.

---

## 5. Regression Quality Validation

Before a synthesized candidate is accepted into the regression suite, `RegressionValidator` enforces quality invariants:

* **Identity**: Requires a unique candidate ID and existing `source_failure_id`.
* **Reproducibility**: Verifies the candidate has non-empty executable input and testable expectations.
* **Specificity**: Rejects trivial assertions (e.g., `assert output != ""`).
* **Traceability**: Validates full provenance links back to failure reports and root cause IDs.
* **Duplicate Detection**: Computes equivalence across failure types, inputs, and expectations to prevent bloating suites with redundant regression tests.

Validation results are structured:
```python
RegressionValidation(
    valid=True,
    minimal=True,
    reproducible=True,
    specific=True,
    traceable=True,
    duplicate=False,
    reasons=[],
)
```

---

## 6. Duplicate Detection

If an equivalent regression test already exists in the test repository, synthesis halts with status `GenerationStatus.DUPLICATE`:
* Matches identical failure types.
* Matches identical (or equivalent minimized) inputs.
* Matches identical expectation rules and metadata assertions.

This guarantees that running repeated evaluation cycles on recurring bugs does not generate unbounded duplicate test cases.

---

## 7. Provenance Tracking

Every generated `RegressionTest` records provenance:
```python
RegressionTest(
    id="reg_tool_wrong_order_refund_flow",
    source_failure_id="fail_a81b2c...",
    metadata={
        "root_cause_id": "rc_f93a1d...",
        "source_trace_id": "trace_817e0b...",
        "generation_method": "deterministic_trace_synthesis",
        "minimized": True,
        "validation": {...},
    },
)
```
Engineers can answer *"Why does this regression test exist?"* by inspecting its `source_failure_id` and `root_cause_id`.

---

## 8. CLI Integration

Inspect synthesized regression tests and their provenance using `airel regressions`:

```bash
# Standard view
airel regressions

# Detailed provenance, minimization, and validation breakdown
airel regressions --details
```

Sample output:
```text
Generated Regression Tests (1):
------------------------------------------------------------
ID:               reg_tool_wrong_order_refund_flow
Name:             reg_tool_wrong_order_refund_flow
Source Failure:   fail_44130ac...
Test Input:       {'order_id': '123'}
Expected Output:  None
Tags:             regression, failure:tool, type:wrong_order, minimized
Method:           deterministic_trace_synthesis
Root Cause:       rc_98a72b...
Minimized:        True
Validation:       valid=True minimal=True reproducible=True
------------------------------------------------------------
```

---

## 9. Limitations

1. **Conservative Pruning**: Minimization only prunes dictionary keys or trace steps explicitly isolated by evidence. Unstructured string inputs are never pruned heuristically.
2. **Deterministic Rules**: Assertion generation is driven by structured taxonomy and evaluation evidence. It does not synthesize arbitrary novel Python assertion code outside registered evaluator protocols.
3. **No Speculation**: If a failure lacks sufficient evidence, the generator safely flags `INSUFFICIENT_EVIDENCE` rather than fabricating expected values.
