# AI Reliability Engine Documentation Index

Welcome to the technical documentation for `aireliability`.

---

## Documentation Sections

1. **[Architecture Specification](architecture.md)**
   - Complete data flow diagrams.
   - Core Protocols: `Evaluator`, `ExecutionAdapter`, `StorageBackend`.
   - Structured Failure Taxonomy (`FailureCategory` & `FailureType`).
   - Audit provenance linking: `RegressionTest` $\rightarrow$ `FailureReport` $\rightarrow$ `ExecutionTrace`.

2. **[Evaluation Concepts](evaluation_concepts.md)**
   - Deterministic Evaluation vs. Semantic Evaluation.
   - Observability (Production APM) vs. Reliability Testing (Pre-deployment Gates).
   - The AI Regression Taxonomy (`PASSING`, `REGRESSION`, `KNOWN_FAILURE`, `FIXED`, `NEW`).

3. **[Benchmarks Report](../benchmarks/README.md)**
   - Hardware and environment specifications.
   - Evaluation overhead empirical results (< 0.04 ms added per agent run).
   - Assertion performance (200k–700k ops/sec).
   - Storage benchmarks and suite scalability.

4. **[Runnable Examples](../examples/README.md)**
   - End-to-end reliability & regression workflow ([`examples/end_to_end_workflow.py`](../examples/end_to_end_workflow.py)).
   - Custom evaluators and execution adapters ([`examples/custom_evaluator_and_adapter.py`](../examples/custom_evaluator_and_adapter.py)).
   - CI pipeline integration script ([`examples/ci_pipeline.sh`](../examples/ci_pipeline.sh)).
