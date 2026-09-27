# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 1: Foundation & Setup**
  - Package structure, `pyproject.toml` configuration with Hatchling build backend.
  - Python 3.11+ requirement, Pydantic runtime dependency.
  - Development tools (`pytest`, `ruff`).
- **Phase 2: Core Data Models**
  - Implemented immutable Pydantic models: `TestCase`, `TraceStep`, `ExecutionTrace`, `EvaluationResult`, `FailureReport`, `RegressionTest`, and `RunResult`.
  - Added enums: `StepType`, `ExecutionStatus`, and `FailureSeverity`.
- **Phase 3: Core Protocols & Interfaces**
  - Added `runtime_checkable` protocols: `Traceable`, `ExecutionAdapter`, `Evaluator`, and `Expectation`.
- **Phase 4: Deterministic Assertions**
  - Implemented non-LLM, microsecond-level assertions: `ToolCalled`, `ToolNotCalled`, `ToolOrder`, `ToolArguments`, `OutputEquals`, `OutputContains`, `SchemaMatch`, `MaxLatency`, and `MaxCost`.
- **Phase 5: Execution Engine**
  - Implemented `ReliabilityRunner` orchestrating agent invocation, trace capture, evaluator execution, and failure compilation.
- **Phase 6: Failure Taxonomy & Analysis**
  - Implemented `FailureTaxonomy` across 6 categories (`TASK`, `TOOL`, `RETRIEVAL`, `OUTPUT`, `SAFETY`, `PERFORMANCE`).
  - Implemented deterministic `FailureAnalyzer` mapping evaluation outcomes into structured `FailureReports`.
- **Phase 7: Regression Generator & Baseline Management**
  - Implemented `RegressionGenerator` creating reproducible `RegressionTest` cases preserving provenance (`source_failure_id`).
  - Implemented `BaselineManager` with 5-state comparison logic (`PASSING`, `REGRESSION`, `KNOWN_FAILURE`, `FIXED`, `NEW`).
- **Phase 8: SQLite Storage Subsystem**
  - Implemented serverless, transactional `SQLiteStorage` implementing `StorageBackend`.
  - Added index optimization and safe schema initialization.
- **Phase 9: Command-Line Interface (`airel`)**
  - Implemented CLI commands: `airel init`, `airel test`, `airel failures`, `airel regressions`, and `airel compare`.
- **Phase 10: CI/CD Workflows & Packaging**
  - Added GitHub Actions workflow (`.github/workflows/ci.yml`) testing Python 3.11, 3.12, 3.13, Ruff linting, and package builds.
  - Implemented `--ci` strict exit code flag (`airel test --ci`).
  - Added executable CI script `examples/ci_pipeline.sh`.
- **Phase 11: Reproducible Benchmarks**
  - Created reproducible benchmark runner `benchmarks/run_benchmarks.py` and scenario definitions `benchmarks/scenarios.py`.
  - Empirical overhead verification (< 0.04 ms added per agent run; 500k–700k ops/sec assertion throughput).
- **Phase 12 (Documentation & Community Readiness)**
  - Comprehensive `README.md` covering architecture, deterministic vs semantic evaluation, CI/CD, and extension points.
  - Added `docs/architecture.md`, `docs/evaluation_concepts.md`, and `docs/README.md`.
  - Added practical runnable examples: `examples/end_to_end_workflow.py` and `examples/custom_evaluator_and_adapter.py`.
