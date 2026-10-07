# AI Reliability Platform v1.4.0 — Production Performance Benchmarks

Comprehensive, deterministic performance, latency, memory, throughput, and scalability validation framework for `aireliability` v1.4.0.

## Overview

This benchmark suite validates production performance across all 46 system phases without paid cloud dependencies, GPUs, or external credentials. All workloads execute deterministically and generate both machine-readable JSON artifacts and human-readable Markdown reports.

## Directory Structure

```
benchmarks/
├── README.md                      # Documentation & benchmark guidelines
├── benchmark_config.py            # Dataset constants, modes, and performance budgets
├── benchmark_utils.py             # High-precision timer, percentiles, RSS memory profiling
├── benchmark_results.py           # Serialization, environment capture, markdown formatter
├── dataset_generator.py           # Deterministic synthetic dataset generator
├── run_benchmarks.py              # Master benchmark orchestrator
├── compare.py                     # Baseline vs performance regression comparator
│
├── benchmark_llm.py               # Phase 30: DeterministicLLM generation & validation
├── benchmark_evaluation.py        # Phase 31: Single, batch, semantic, regression evals
├── benchmark_rag.py               # Phase 39: 11-stage pipeline, retrieval & context
├── benchmark_agent.py             # Phase 40: Multi-step trajectories & loop detection
├── benchmark_safety.py            # Phase 41: Red-teaming campaigns & hard safety vetoes
├── benchmark_intelligence.py      # Phase 34: Fingerprinting, clustering & recommendations
├── benchmark_graph.py             # Phase 35: Graph insertion, indexed lookup, traversal
├── benchmark_test_generation.py   # Phase 36: Failure-to-test synthesis & deduplication
├── benchmark_healing.py           # Phase 37: Self-healing proposals, gates, and rollouts
├── benchmark_optimization.py      # Phase 38: Multi-strategy search & Pareto evaluation
├── benchmark_prediction.py        # Phase 42: Time-series forecasting & drift calibration
├── benchmark_policy.py            # Phase 44: Policy precedence & hard security vetoes
├── benchmark_multitenancy.py      # Phase 45: Context switching, RBAC, and isolation checks
├── benchmark_dashboard.py         # Phase 43: Health summary & panel aggregations
├── benchmark_api.py               # Phase 46: REST API local endpoints & concurrency
├── benchmark_sdk.py               # Phase 46: Synchronous and Asynchronous SDK clients
│
├── datasets/                      # Deterministic pre-generated test datasets
│   ├── small/                     # 10 evaluations, 10 documents, 10 failures, 10 steps
│   ├── medium/                    # 100 evaluations, 100 documents, 100 failures, 100 steps
│   └── large/                     # 1,000 evaluations, 1,000 documents, 1,000 failures
│
└── results/                       # Generated benchmark outputs
    ├── baseline.json              # Historical performance baseline
    ├── performance.json           # Latest run results
    └── PERFORMANCE_REPORT.md      # Human-readable comparison & tabular breakdown
```

## Workload Scales

- **SMALL**: 10 evaluations, 10 documents, 10 failures, 10 agent steps
- **MEDIUM**: 100 evaluations, 100 documents, 100 failures, 100 agent steps
- **LARGE**: 1,000 evaluations, 1,000 documents, 1,000 failures, 100 agent steps
- **XLARGE**: 10,000 items (for stress tests, forecasting, and graph indexing)

## Running Benchmarks

### Quick Mode (Local dev check)
```bash
python3 benchmarks/run_benchmarks.py --mode quick
```

### Smoke Mode (Lightweight CI check)
```bash
python3 benchmarks/run_benchmarks.py --mode smoke
```

### Full Mode (Production Release Validation)
```bash
python3 benchmarks/run_benchmarks.py --mode full
```

### Generate & Save Baseline
```bash
python3 benchmarks/run_benchmarks.py --mode quick --save-baseline
```

### Compare Against Baseline
```bash
python3 benchmarks/compare.py \
    benchmarks/results/baseline.json \
    benchmarks/results/performance.json
```

## Performance Budgets & Categories

- **PASS**: Latency and throughput strictly within budget thresholds.
- **WATCH**: Correct execution, but latency or memory growth requires attention.
- **REGRESSION**: Material degradation exceeding tolerance thresholds without architectural justification.
