# CI/CD and Pull Request Reliability Architecture

This document describes the continuous integration (CI) architecture for `aireliability`, detailing how every pull request and push to `main` verifies correctness, packaging, deterministic reliability, and regression protection without external network dependencies or API keys.

---

## 1. High-Level CI Architecture

```text
Code Change / Pull Request
            │
    ┌───────┴────────────────────────┐
    ▼                                ▼
[ci.yml: Core CI]         [reliability.yml: Reliability CI]
  ├── Ruff Lint/Format      ├── Deterministic Scenarios
  ├── Python 3.11, 3.12, 3.13 ├── Baseline Comparison
  ├── Pytest + JUnit XML    ├── Step Summary ($GITHUB_STEP_SUMMARY)
  ├── Build sdist & wheel   └── Artifact Upload (report.json/md)
  └── Clean Wheel Install
            │
            ▼
[integration.yml: Framework Integrations] (Optional)
  ├── Python 3.11, 3.12
  └── LangGraph & LangChain Tests
```

---

## 2. Core CI Workflow (`ci.yml`)

The Core CI workflow runs on all pull requests and pushes to `main`. It contains three decoupled jobs:

1. **`lint`**:
   - Executes `ruff check .` and `ruff format --check .`.
   - Validates that code adheres to formatting style (88-character maximum length, import ordering).

2. **`tests` (Python Matrix)**:
   - Matrix testing across supported versions: **Python 3.11, 3.12, and 3.13**.
   - Caches `pip` packages.
   - Installs package with development dependencies (`pip install -e ".[dev]"`).
   - Runs `pytest --junitxml=junit-results-${{ matrix.python-version }}.xml`.
   - Uploads JUnit test results as artifacts for 7-day retention.

3. **`package` (Build & Clean Installation)**:
   - Verifies packaging tools: `python -m build` and `twine check dist/*`.
   - Validates that the generated wheel can be installed in a clean environment outside the repository tree:
     ```bash
     python -m venv /tmp/aireliability-clean
     pip install dist/*.whl
     python -c "import aireliability; print(aireliability.__version__)"
     airel --help
     ```

---

## 3. Dedicated Reliability Workflow (`reliability.yml`)

The Reliability workflow executes deterministic AI reliability scenarios, performance smoke tests, and baseline comparison.

### Key Objectives:
- **Zero External API Dependency**: No OpenAI, Anthropic, or external LLM API keys required.
- **Zero GPU Requirement**: CPU-only deterministic evaluation.
- **Deterministic Reliability Lifecycle**:
  ```text
  Expected Failure
        ↓
  Failure Detected
        ↓
  Root Cause Identified
        ↓
  Regression Synthesized
        ↓
  Fixed Behavior Passes
        ↓
  Reintroduced Bug Fails (REGRESSION)
  ```

### Deterministic Scenarios Evaluated:
- Tool ordering mismatches (`WRONG_ORDER`)
- Tool selection errors (`WRONG_TOOL`)
- Argument mismatches (`WRONG_ARGUMENT`)
- Missing required tools (`MISSING_TOOL`)
- Output regressions (exact and substring matches)
- Performance / latency threshold regressions
- Evidence-based root-cause diagnosis
- Minimal regression test synthesis and re-detection

---

## 4. Baseline Management & Regression Policies

The reliability job verifies changes against active baselines using `BaselineManager`.

### Transition Classifications:
| Transition | Baseline State | Current Run | CI Action | Description |
| :--- | :--- | :--- | :--- | :--- |
| **`PASSING`** | PASS | PASS | Pass | Test passed previously and continues to pass. |
| **`FIXED`** | FAIL | PASS | Pass | Previously failing test is now resolved. |
| **`KNOWN_FAILURE`** | FAIL | FAIL | Pass | Existing known failure; does not fail CI. |
| **`REGRESSION`** | PASS | FAIL | **Fail** | A previously working feature broke. CI exits with `1`. |
| **`NEW`** | N/A | PASS / FAIL | Evaluated | Newly introduced test case. |

> **Critical Rule**: Only genuine `REGRESSION` transitions (`PASS → FAIL`) cause the baseline comparison gate to fail. `KNOWN_FAILURE` transitions (`FAIL → FAIL`) do not fail the baseline comparison step.

---

## 5. Performance Regression & Smoke Test Policy

- **Smoke Benchmark**: CI runs `python benchmarks/run_benchmarks.py --smoke`, which executes 100 iterations of overhead measurements across synthetic scenarios.
- **Timing Fluctuation Policy**: CI does **NOT** use unstable microsecond execution timing (e.g. 7.8 µs vs 8.3 µs) as a hard gating check.
- **Purpose**: Performance smoke tests ensure functional correctness and guard against extreme multi-millisecond regressions, rather than microbenchmark noise on shared CI runners.

---

## 6. PR Reporting and Step Summary

When the reliability job runs in GitHub Actions, it writes structured Markdown diagnostics directly to `$GITHUB_STEP_SUMMARY`:

```markdown
# aireliability Reliability Report

## Test Status
Core Tests: PASS
- Total tests: 206
- Passed: 206
- Failed: 0

## Reliability
- Scenarios: 6
- Failures: 0
- Regressions: 0
```

When a regression occurs, the report details:
- **Test ID & Name**
- **Failure Category & Type**
- **Expected vs Actual Behavior**
- **Diagnosed Root Cause Hypothesis & Evidence**
- **Synthesized Regression Test ID**

Machine-readable JSON reports (`reliability-report.json`) and Markdown summaries (`reliability-report.md`) are uploaded as CI build artifacts.

---

## 7. Optional Framework CI (`integration.yml`)

Integrations with optional agent frameworks (LangGraph and LangChain) are tested in an isolated workflow on Python 3.11 and 3.12:
- Runs with `pip install -e ".[dev,langgraph,langchain]"`.
- Ensures framework integrations do not contaminate or add requirements to the core package.
- Ensures graceful fallback warnings when optional framework dependencies are omitted.

---

## 8. Security & Permissions

All workflows enforce conservative permissions:
```yaml
permissions:
  contents: read
```
- No write permissions are granted to CI jobs.
- No repository secrets, credentials, or API keys are exposed to test jobs.

---

## 9. Local Reproduction Guide

Developers can reproduce every CI check locally using standard tools:

```bash
# 1. Run all unit and integration tests
pytest

# 2. Run Ruff check and format check
ruff check .
ruff format --check .

# 3. Run reliability benchmark scenarios
pytest tests/unit/test_phase14_benchmarks.py \
       tests/unit/test_phase18_regression.py \
       tests/unit/test_phase20_ci_reliability.py

# 4. Run smoke benchmark
python benchmarks/run_benchmarks.py --smoke

# 5. Build and validate distribution
python -m build
twine check dist/*
```
