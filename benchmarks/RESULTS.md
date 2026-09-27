# Real-World Reliability Benchmark Results (`RESULTS.md`)

This document records the empirical results of the **Phase 14 Real-World Reliability Benchmark** for `aireliability`.

> **Methodology & Integrity**: All measurements reported below are reproducible, empirical outcomes executed directly on the local test workstation without network calls or external LLM API dependencies. No values are manufactured, estimated, or extrapolated.

---

## 1. Environment & Hardware Specifications

| Component | Specification |
| :--- | :--- |
| **Processor** | Apple M1 Pro (8 cores: 6 performance + 2 efficiency) |
| **Architecture** | `arm64` |
| **Operating System** | macOS Darwin 23.3.0 |
| **Python Version** | 3.12.1 (CPython, 64-bit) |
| **Test Date** | 2026-09-26 |
| **Nature of Benchmark**| **Deterministic Synthetic Scenarios** (Simulated AI agent tool workflows) |

---

## 2. Core Scenarios & Detection Matrix

The central claim of the project is:
> *AI execution failures can be detected, classified, converted into regression tests, and detected again after a behavioral regression.*

The table below demonstrates empirical verification across all 6 required benchmark scenarios:

| Scenario ID & Name | Expected Failure Type | Detected? | Actual Failure Type(s) Detected | Regression Test Generated? | Regression Re-Detected on Bug Reintroduction? |
| :--- | :--- | :---: | :--- | :---: | :---: |
| **Scenario A**<br>`Tool Ordering` | `TOOL.WRONG_ORDER` | **YES** | `wrong_order` | **YES** | **YES** (`REGRESSION`) |
| **Scenario B**<br>`Wrong Tool` | `TOOL.WRONG_TOOL` | **YES** | `wrong_tool`, `unnecessary_tool` | **YES** | **YES** (`REGRESSION`) |
| **Scenario C**<br>`Wrong Arguments` | `TOOL.WRONG_ARGUMENT` | **YES** | `wrong_argument` | **YES** | **YES** (`REGRESSION`) |
| **Scenario D**<br>`Missing Required Tool` | `TOOL.WRONG_TOOL` | **YES** | `wrong_tool` | **YES** | **YES** (`REGRESSION`) |
| **Scenario E**<br>`Output Regression` | `TASK.TASK_INCORRECT` | **YES** | `task_incorrect` | **YES** | **YES** (`REGRESSION`) |
| **Scenario F**<br>`Latency Regression` | `PERFORMANCE.LATENCY` | **YES** | `latency` | **YES** | **YES** (`REGRESSION`) |

---

## 3. Failure $\longrightarrow$ Regression Test Lifecycle Verification

The full lifecycle was empirically tested and verified:

```text
Faulty Agent Logic
       ↓
ExecutionTrace captured
       ↓
Evaluators execute
       ↓
FailureReport generated (category: TOOL, type: WRONG_ORDER)
       ↓
RegressionTest synthesized (preserves source_failure_id)
       ↓
Agent logic fixed
       ↓
Regression test executed against fixed agent
       ↓
PASS (recorded in baseline snapshot)
       ↓
Bug intentionally reintroduced
       ↓
Regression test re-executed
       ↓
REGRESSION DETECTED (Blocks baseline comparison)
```

**Outcome**: Confirmed. When the bug is reintroduced, `BaselineManager.compare()` identifies the state transition from passing in reference baseline to failing in the current run, classifying it as `REGRESSION`.

---

## 4. Baseline Classification States Verification

All four baseline states were verified:

| Historical State | Current State | Classified Status | Verified in Suite? | Meaning |
| :--- | :--- | :--- | :---: | :--- |
| **PASS** | **FAIL** | `REGRESSION` | **YES** | New failure introduced; breaks deployment gate. |
| **FAIL** | **FAIL** | `KNOWN_FAILURE` | **YES** | Pre-existing failure; does not block progress. |
| **FAIL** | **PASS** | `FIXED` | **YES** | Defect resolved; passing reference recorded. |
| **PASS** | **PASS** | `PASSING` (Unchanged) | **YES** | Stable success; invariant preserved. |

---

## 5. Audit Traceability Chain

Every synthesized regression test preserves complete provenance:

$$\mathbf{RegressionTest} \xrightarrow{\text{source\_failure\_id}} \mathbf{FailureReport} \xrightarrow{\text{trace\_id}} \mathbf{ExecutionTrace} \xrightarrow{\text{test\_id}} \mathbf{TestCase}$$

### Empirical Verification Sample
- **Regression Test ID**: `reg_a171dd6cddc54458bac82fa4d9d121a6`
- **Source Failure ID**: `fail_7dd6ddd193cc4787b613a7e5cc7b0b3f`
- **Trace ID**: `trace_b9a12b5a416f447dbad2313f22a5c10b`
- **Originating Test ID**: `tc_root`
- **Chain Intact**: **True**

A developer can inspect `reg_test.test_case.metadata` and immediately answer:
> *"Why does this regression test exist?"*  
> Reason: Failure `fail_7dd6...` (`PERFORMANCE.LATENCY`) observed during execution of `tc_root`.

---

## 6. Execution Overhead Measurements

Measured over **1,000 repeated local executions** comparing raw agent execution against wrapped execution (`ReliabilityRunner` + `ExecutionTrace` + `ToolOrder` evaluation + `FailureAnalyzer`):

| Metric | Raw Agent Execution | With `aireliability` | Added Engine Overhead |
| :--- | :--- | :--- | :--- |
| **Mean** | 0.060 µs | 8.442 µs | **8.382 µs** (~0.0084 ms) |
| **Median** | 0.042 µs | 8.084 µs | **8.041 µs** (~0.0080 ms) |
| **Minimum** | 0.041 µs | 7.583 µs | **7.459 µs** (~0.0075 ms) |
| **Maximum** | 0.250 µs | 105.041 µs | **104.999 µs** (~0.1050 ms) |

> **Contextual Note**: In real-world AI applications, network round-trips to LLM providers typically take between 200 ms and 3,000 ms. An engine overhead of ~0.008 ms represents less than **0.004%** of invocation time.

---

## 7. How to Reproduce

Execute the standalone benchmark runner:

```bash
# Activate your environment
source .venv/bin/activate

# Execute Phase 14 benchmark runner
python benchmarks/run_benchmarks.py

# Run benchmark test suite
pytest tests/unit/test_phase14_benchmarks.py
```
