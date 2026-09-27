# AI Reliability Engine (`aireliability`) - Benchmark Report

This document records reproducible benchmarks evaluating the execution overhead, trace processing throughput, regression detection efficiency, assertion evaluation latency, and persistence performance of the `aireliability` engine.

> **Integrity Note**: All measurements reported below are actual empirical results obtained on the test machine described under [Hardware & Environment](#hardware--environment). No performance claims are manufactured or artificially scaled.

---

## 1. Hardware & Environment

The benchmark suite was executed on a commodity workstation without any GPU acceleration or external database servers.

| Component | Specification |
| :--- | :--- |
| **Processor (CPU)** | Apple M1 Pro (8 cores: 6 performance + 2 efficiency) |
| **Architecture** | `arm64` |
| **Operating System** | macOS Darwin 23.3.0 |
| **Python Version** | 3.12.1 (CPython, 64-bit) |
| **GPU Requirement** | **None** (100% CPU deterministic execution) |
| **Dependencies** | `pydantic>=2.0`, standard library `sqlite3` |

---

## 2. Methodology & Scenarios

### Evaluation Overhead: Raw Agent vs Wrapped Execution
To measure the exact CPU overhead introduced by the reliability engine, three synthetic agent scenarios with deterministic tasks and known mutation modes were evaluated:

1. **Customer Support Agent (`support_agent_baseline`)**:
   - Executes multi-step tool calls (`lookup_order` → `verify_eligibility` → `issue_refund` → `send_email`).
   - Evaluated against 4 assertions: `ToolCalled`, `ToolOrder`, `OutputContains`, and `MaxLatency`.
   - Simulates realistic tool orchestration workflows.
2. **Invoice Extraction Agent (`extraction_agent_baseline`)**:
   - Parses document metadata into structured JSON.
   - Evaluated against a strict JSON schema (`SchemaMatch`) with nested required keys and types.
3. **Code Assistant Agent (`code_assistant_baseline`)**:
   - Produces code implementations and algorithm explanations.
   - Evaluated against string containment (`OutputContains`) assertions.

Each scenario was run 1,000 times comparing:
- **Baseline execution**: Raw Python callable invocation without tracing or assertions.
- **Execution + aireliability**: Invocation wrapped in `ReliabilityRunner` with full trace lifecycle capture, evaluation against expectations, and root-cause failure analysis.

### Deterministic Assertion Performance
10,000 iterations per assertion type to measure microsecond-level overhead and operations-per-second throughput across:
- `ToolCalled`
- `ToolOrder`
- `ToolArguments`
- `OutputContains`
- `OutputEquals`
- `MaxLatency`
- `MaxCost`
- `SchemaMatch`

### Trace Processing & Failure Analysis
5,000 synthetic multi-step execution traces with tool invocations, token accounting, and timestamps were constructed, validated via Pydantic models, and evaluated through the `FailureAnalyzer`.

### Regression Detection Across Test Suite Scales
`BaselineManager.compare()` evaluated against full test suites of sizes **50, 200, 1,000, and 5,000 test cases**, tracking state transitions:
$$\text{Previously Passing} + \text{Currently Failing} \longrightarrow \text{REGRESSION}$$
Tested with intentional mutations and known failures to verify detection accuracy and sub-linear comparison latency.

### SQLite Storage Throughput
Atomic storage operations benchmarked over 1,000 test cases, traces, evaluation records, and baseline snapshots on a local file-backed SQLite database.

---

## 3. Empirical Results

### A. Evaluation Overhead (`ReliabilityRunner`)

| Scenario | Raw Agent Time | With `aireliability` | Added Overhead | Added Overhead (ms) |
| :--- | :--- | :--- | :--- | :--- |
| **Customer Support** (4 assertions, tool order) | 0.44 µs | 39.44 µs | **39.01 µs** | **0.0390 ms** |
| **Invoice Extraction** (JSON Schema check) | 0.21 µs | 15.71 µs | **15.50 µs** | **0.0155 ms** |
| **Code Assistant** (Substring check) | 0.06 µs | 8.93 µs | **8.87 µs** | **0.0089 ms** |

> **Key Finding**: The entire tracing, evaluation, and failure taxonomy pipeline adds **less than 0.04 milliseconds** of overhead per agent call. In real-world LLM workloads where API latencies range between 200 ms and 5,000 ms, `aireliability` introduces negligible execution latency (< 0.02%).

---

### B. Deterministic Assertion Latency & Throughput

Measured across 10,000 iterations:

| Assertion | Average Latency | p95 Latency | Throughput (ops/sec) |
| :--- | :--- | :--- | :--- |
| **`OutputEquals`** | 1.36 µs | 1.57 µs | **737,898 ops/s** |
| **`OutputContains`** | 1.38 µs | 1.47 µs | **725,998 ops/s** |
| **`MaxCost`** | 1.53 µs | 1.70 µs | **653,974 ops/s** |
| **`MaxLatency`** | 1.56 µs | 1.80 µs | **642,322 ops/s** |
| **`ToolArguments`** | 1.60 µs | 1.80 µs | **626,890 ops/s** |
| **`ToolCalled`** | 1.74 µs | 1.82 µs | **575,306 ops/s** |
| **`ToolOrder`** | 2.07 µs | 2.19 µs | **484,329 ops/s** |
| **`SchemaMatch`** | 4.70 µs | 4.88 µs | **212,642 ops/s** |

---

### C. Trace Processing Performance

- **Evaluated Volume**: 5,000 execution traces with multiple tool steps.
- **Total Duration**: 0.0835 seconds.
- **Average Time per Trace**: **16.69 µs**.
- **Processing Throughput**: **59,907 traces/sec**.

---

### D. Regression Detection Latency Across Test Suite Sizes

| Test Suite Size | Regressions Injected & Detected | Mean Comparison Time | p95 Latency | Comparison Throughput |
| :--- | :--- | :--- | :--- | :--- |
| **50 tests** | 0 regressions (clean) | 0.064 ms | 0.072 ms | 777,332 tests/s |
| **200 tests** | 2 regressions | 0.264 ms | 0.348 ms | 758,826 tests/s |
| **1,000 tests** | 10 regressions | 1.533 ms | 1.806 ms | 652,432 tests/s |
| **5,000 tests** | 50 regressions | 9.772 ms | 20.017 ms | 511,691 tests/s |

> **Key Finding**: Comparing a massive suite of 5,000 test results against historical baselines and isolating regressions takes **under 10 milliseconds**.

---

### E. Local SQLite Storage Engine Performance

Persistence measured on local disk (`benchmark.db`):

| Operation | Metric / Throughput |
| :--- | :--- |
| **Test Case Write Throughput** | **2,193 ops/sec** |
| **Test Case Read / List Throughput** | **146,982 ops/sec** |
| **Trace + Evaluation Write Throughput** | **1,125 ops/sec** |
| **Baseline Snapshot Save (1,000 tests)** | **11.05 ms** |
| **Baseline Snapshot Load (1,000 tests)** | **11.78 ms** |

---

## 4. Reproducing the Benchmarks

You can reproduce all benchmarks locally without special hardware or external services:

```bash
# Activate virtual environment
source .venv/bin/activate

# Execute benchmark runner
python benchmarks/run_benchmarks.py
```

The script will re-run all 5 benchmark suites and write fresh results to `benchmarks/benchmark_results.json`.

---

## 5. Limitations

1. **Synthetic In-Memory Agents**:
   - The benchmarks utilize deterministic in-memory mock agents to precisely measure `aireliability` CPU overhead rather than measuring network jitter of external LLM endpoints (e.g., OpenAI or Anthropic).
2. **Local Disk I/O**:
   - SQLite write performance reflects local SSD NVMe speeds with standard filesystem sync barriers. Production environments using in-memory databases (`:memory:`) or dedicated pooled connections will observe even higher throughput.
3. **Deterministic Expectations**:
   - Measurements cover deterministic assertions (`ToolCalled`, `ToolOrder`, `SchemaMatch`, etc.). LLM-as-a-judge or semantic embedding evaluators (planned for future phases) will be constrained by remote inference latencies rather than framework CPU time.
