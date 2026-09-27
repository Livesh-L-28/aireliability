# Architecture Specification

This document details the system design, core protocols, data flow, failure taxonomy, and storage subsystems of `aireliability`.

---

## 1. System Data Flow

```text
               ┌──────────────┐
               │   TestCase   │
               └──────┬───────┘
                      │
                      ▼
 ┌─────────────┐   ┌──────────────────────┐
 │   Agent     │──▶│  ReliabilityRunner   │
 └─────────────┘   └──────────┬───────────┘
                              │ executes & captures
                              ▼
                      ┌──────────────────────┐
                      │    ExecutionTrace    │
                      └──────────┬───────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼
     ┌──────────────────────┐        ┌──────────────────────┐
     │ Deterministic Assert │        │   Custom Evaluator   │
     └───────────┬──────────┘        └───────────┬──────────┘
                 │                               │
                 └───────────────┬───────────────┘
                                 │ produces
                                 ▼
                     ┌───────────────────────┐
                     │   EvaluationResults   │
                     └───────────┬───────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │    FailureAnalyzer    │
                     └───────────┬───────────┘
                                 │ produces
                                 ▼
                     ┌───────────────────────┐
                     │     FailureReport     │
                     └───────────┬───────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │  RegressionGenerator  │
                     └───────────┬───────────┘
                                 │ generates
                                 ▼
                     ┌───────────────────────┐
                     │    RegressionTest     │
                     │  (preserves provenance)
                     └───────────────────────┘
```

---

## 2. Core Protocols

All extension points use Python standard `typing.Protocol` with `@runtime_checkable`, enabling third-party developers to implement custom components without inheriting from private internal classes.

### A. `Evaluator`
```python
@runtime_checkable
class Evaluator(Protocol):
    name: str

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase,
    ) -> EvaluationResult: ...
```

### B. `ExecutionAdapter`
```python
@runtime_checkable
class ExecutionAdapter(Protocol):
    def execute(
        self,
        agent: Any,
        test_case: TestCase,
    ) -> ExecutionTrace: ...
```

### C. `StorageBackend`
```python
class StorageBackend(ABC):
    def save_test_case(self, test_case: TestCase) -> None: ...
    def save_trace(self, trace: ExecutionTrace) -> None: ...
    def save_evaluations(
        self, trace_id: str, evaluations: list[EvaluationResult]
    ) -> None: ...
    def save_failure(self, failure: FailureReport) -> None: ...
    def save_regression_test(self, regression_test: RegressionTest) -> None: ...
    def save_baseline(self, name: str, entries: list[BaselineEntry]) -> None: ...
    def get_baseline(self, name: str) -> dict[str, BaselineEntry]: ...
```

---

## 3. Failure Taxonomy

The `FailureAnalyzer` uses a two-level structured taxonomy to classify issues deterministically:

### Categories (`FailureCategory`)
- `TASK`: High-level goal achievement.
- `TOOL`: Tool selection, invocation order, and parameter matching.
- `RETRIEVAL`: Context grounding and retrieval quality.
- `OUTPUT`: Structural schema, formatting, and content contracts.
- `SAFETY`: Policy, ethical, or safety invariants.
- `PERFORMANCE`: Latency budgets, token overuse, and financial cost.

### Types (`FailureType`)
- `TASK_INCOMPLETE`, `TASK_INCORRECT`
- `WRONG_TOOL`, `WRONG_ARGUMENT`, `WRONG_ORDER`, `UNNECESSARY_TOOL`
- `MISSING_CONTEXT`, `IRRELEVANT_CONTEXT`, `CONFLICTING_CONTEXT`
- `SCHEMA_ERROR`, `UNSUPPORTED_CLAIM`, `HALLUCINATION`
- `SAFETY_VIOLATION`
- `LATENCY`, `TOKEN_OVERUSE`, `COST`

---

## 4. Provenance Tracking

When a regression test is synthesized by `RegressionGenerator`, it maintains a cryptographic or deterministic provenance chain:

$$\text{RegressionTest} \xrightarrow{\text{source\_failure\_id}} \text{FailureReport} \xrightarrow{\text{trace\_id}} \text{ExecutionTrace} \xrightarrow{\text{test\_id}} \text{TestCase}$$

This enables developers to trace any synthesized test directly back to the original execution failure that prompted its creation.
