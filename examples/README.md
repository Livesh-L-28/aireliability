# AI Reliability Engine Examples

This directory provides runnable, end-to-end examples demonstrating the features and extension patterns of `aireliability`.

---

## Example 1: End-to-End Reliability & Regression Workflow

**File**: [`end_to_end_workflow.py`](end_to_end_workflow.py)

Demonstrates the core differentiator of `aireliability`:
$$\text{Execution} \longrightarrow \text{Failure} \longrightarrow \text{Baseline Comparison} \longrightarrow \text{Regression Test Generation}$$

### What it shows:
1. Defining a `TestCase` with multi-dimensional expectations (`OutputContains`, `ToolCalled`, `ToolOrder`, `MaxLatency`).
2. Executing a working agent (V1) using `ReliabilityRunner` and saving the passing result as a reference baseline snapshot with `BaselineManager`.
3. Executing a mutated/regressed agent (V2) where tool call sequences and outputs are broken.
4. Automatic failure detection and taxonomy classification (`FailureCategory.TASK`, `FailureType.TASK_INCORRECT`, `FailureCategory.TOOL`, `FailureType.WRONG_ORDER`).
5. Detecting regression: recognizing that the test was previously passing in the baseline and is now failing.
6. Generating a reproducible `RegressionTest` via `RegressionGenerator`, preserving end-to-end audit provenance (`source_failure_id`).

### Running the example:
```bash
python examples/end_to_end_workflow.py
```

---

## Example 2: Custom Evaluators & Custom Execution Adapters

**File**: [`custom_evaluator_and_adapter.py`](custom_evaluator_and_adapter.py)

Demonstrates how external developers can extend `aireliability` without touching framework internals.

### What it shows:
1. **Implementing `Evaluator`**: Creating a custom `BannedKeywordsEvaluator` that checks for compliance/safety violations and generates evidence payloads.
2. **Implementing `ExecutionAdapter`**: Wrapping an external agent framework (e.g. LangChain, LlamaIndex, DSPy, or a REST API) using `ExecutionAdapter.execute(agent, test_case)` to produce standard `ExecutionTrace` objects with tool steps and token accounting.
3. Passing custom adapters and evaluators to `ReliabilityRunner`.

### Running the example:
```bash
python examples/custom_evaluator_and_adapter.py
```

---

## Example 3: CI/CD Pipeline Gate Script

**File**: [`ci_pipeline.sh`](ci_pipeline.sh)

Demonstrates using the `airel` command-line interface in continuous integration pipelines:

```bash
./examples/ci_pipeline.sh
```

### Key behaviors demonstrated:
- Project initialization: `airel init`
- Baseline recording: `airel test --save-baseline`
- CI execution gate: `airel test --ci` (exits with code `0` on clean runs, and returns non-zero code `1` when regressions or failures are detected).
