# Contributing to AI Reliability Engine

Thank you for your interest in contributing to `aireliability`! We welcome community contributions, bug reports, documentation improvements, and architectural suggestions.

---

## 1. Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for all contributors. Please treat all community members with respect.

---

## 2. Technical Philosophy & Design Invariants

Before contributing code, please keep our core architectural rules in mind:
- **Zero Heavy External Dependencies**: The core package relies only on Python standard libraries and `pydantic`. External frameworks (e.g. LangChain, LangGraph) are strictly optional adapters.
- **Provider & Framework Agnostic**: Never couple internal models or runners to a specific LLM vendor or agent framework. Use standard protocols.
- **Deterministic Confidence**: Never report confidence `1.0` on failure analyses unless backed by verifiable, deterministic evidence.
- **Zero API Key Requirement in CI**: All CI and local test suites run deterministically without API keys, GPUs, or network access.
- **Microsecond Overhead**: Evaluators and tracing logic must remain lightweight (< 0.1 ms overhead).

---

## 3. Development Setup

### Prerequisites
- Python 3.11, 3.12, or 3.13
- `git`

### Installation
1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/aireliability/aireliability.git
   cd aireliability
   ```

2. **Set up a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies in editable mode:**
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   pip install build twine
   ```

4. **Install optional frameworks (if testing integrations):**
   ```bash
   pip install -e ".[langgraph,langchain]"
   ```

---

## 4. Running Checks Locally

All contributions must pass local linting, formatting, tests, and packaging checks before opening a pull request.

### 1. Running Unit & Integration Tests
```bash
# Run all unit tests
pytest

# Run tests with verbose output
pytest -v

# Run with JUnit XML generation (same as CI)
pytest --junitxml=test-results.xml
```

### 2. Running Reliability Scenarios & Distributed Tests
```bash
# Run deterministic reliability benchmark scenarios
pytest tests/unit/test_phase14_benchmarks.py \
       tests/unit/test_phase18_regression.py \
       tests/unit/test_phase20_ci_reliability.py

# Run Phase 23-29 distributed, resilience, tenancy, security, & observability tests
pytest tests/unit/test_phase23_distributed.py \
       tests/unit/test_phase24_persistence.py \
       tests/unit/test_phase25_control_plane.py \
       tests/unit/test_phase26_resilience.py \
       tests/unit/test_phase27_multitenancy.py \
       tests/unit/test_phase28_security.py \
       tests/unit/test_phase29_observability.py
```

### 3. Running Benchmarks
```bash
python benchmarks/run_benchmarks.py --smoke
python benchmarks/run_phase28_benchmarks.py
python benchmarks/run_phase29_benchmarks.py
```

### 4. Running Optional Framework Tests
If you have `langgraph` and `langchain` installed:
```bash
pytest tests/unit/test_phase19_integrations.py
```

### 5. Running Ruff (Linter & Formatter)
We enforce clean code via `ruff` with an 88-character line length:
```bash
# Check for lint violations
ruff check .

# Check code formatting
ruff format --check .

# Automatically apply safe lint fixes and formatting
ruff check --fix .
ruff format .
```

### 6. Validating Package Distribution
Ensure the project builds cleanly and installs in an isolated clean environment:
```bash
# Build distribution
python -m build
twine check dist/*

# Test clean wheel installation
python -m venv /tmp/airel-clean
source /tmp/airel-clean/bin/activate
pip install dist/*.whl
python -c "import aireliability; print(aireliability.__version__)"
airel --help
deactivate
rm -rf /tmp/airel-clean
```

---

## 5. Pull Request Expectations & Handling Reliability Regressions

1. **Deterministic Test Execution**:
   - Tests in CI do not use network access or external LLM API keys. Do not add tests that require external network access.
2. **Baseline Comparison Policy**:
   - The reliability CI job compares execution against established baselines using `BaselineManager`.
   - `PASSING` (previously passing, still passing): Allowed.
   - `FIXED` (previously failing, now passing): Allowed.
   - `KNOWN_FAILURE` (previously failing, still failing): Allowed (does not fail CI).
   - `REGRESSION` (previously passing, now failing): **Strict CI failure**.
3. **Diagnosing a Reliability Regression**:
   - If CI flags a regression, inspect the step summary and generated `reliability-report.json` / `reliability-report.md` artifacts.
   - The report pinpoints the test ID, failure category (`tool`, `output`, `performance`), root cause diagnosis, and synthesized regression test.
   - Run the scenario locally using `airel test` or `airel compare` to reproduce and resolve the regression before requesting review.
