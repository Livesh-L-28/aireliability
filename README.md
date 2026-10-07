# AI Reliability Engine (`aireliability`)

> An open-source reliability and regression-testing framework for LLM applications and AI agents.

[![CI](https://github.com/aireliability/aireliability/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![Security](https://github.com/aireliability/aireliability/actions/workflows/security.yml/badge.svg)](.github/workflows/security.yml)
[![Benchmarks](https://github.com/aireliability/aireliability/actions/workflows/benchmark.yml/badge.svg)](.github/workflows/benchmark.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![Architecture](https://img.shields.io/badge/architecture-provider--agnostic-green.svg)](docs/architecture.md)

---

## 1. Problem

Building production AI agents and LLM applications is notoriously error-prone. A change to a system prompt, model release, tool definition, retrieval chunking strategy, or orchestration logic often causes silent degradations rather than explicit software crashes.

When traditional software breaks, it throws a `TypeError`, `KeyError`, or `IndexError`. When an AI agent breaks:
- It returns an answer with high confidence, but skips mandatory compliance checks.
- It calls tools out of order (e.g. issues a refund before verifying order eligibility).
- It generates slightly altered JSON keys, silently breaking downstream APIs.
- It consumes 5x more tokens or takes 3x longer to complete tasks.

Without specialized reliability tooling, developers discover these regressions after users complain in production.

---

## 2. Why AI Reliability Testing Is Difficult

Testing AI applications differs fundamentally from traditional software testing:

1. **Non-Determinism & Stochasticity**: The same input prompt can produce diverse phrasings across runs.
2. **Silent Semantic Failure Modes**: Models rarely fail loudly; they fail by subtly deviating from requirements.
3. **Flaky LLM-as-a-Judge Evaluators**: Using an LLM to evaluate an LLM introduces non-deterministic test runners, network latency, high costs, and evaluator drift.
4. **Lack of Automated Regression Capture**: In standard web dev, when a bug is fixed, a developer writes a reproduction unit test. In AI engineering, capturing multi-step agent interactions with tool calls, context chunks, and token usage into a deterministic test case has historically been manual and brittle.

`aireliability` solves this by introducing **deterministic assertion primitives**, **structured failure taxonomy analysis**, and **automated regression test synthesis**.

---

## 3. Architecture

The AI Reliability Engine follows a clean, decoupled pipeline:

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
                                 │ categorizes
                                 ▼
                     ┌───────────────────────┐
                     │     FailureReport     │
                     └───────────┬───────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │  RegressionGenerator  │
                     └───────────┬───────────┘
                                 │ synthesizes
                                 ▼
                     ┌───────────────────────┐
                     │    RegressionTest     │
                     │  (preserves provenance)
                     └───────────────────────┘
```

Core capabilities:
- **Zero Heavy Dependencies**: Pure Python with Pydantic and serverless SQLite.
- **Provider & Framework Agnostic**: Works with raw functions, LangChain, LlamaIndex, DSPy, or custom REST APIs via standard `typing.Protocol` interfaces.
- **Deterministic by Design**: Evaluators and assertions execute locally in microseconds with 100% reproducibility.

---

## 4. Installation

### Requirements
- Python 3.11, 3.12, or 3.13
- Operating Systems: macOS, Linux, Windows

### From Source (Current Status)
```bash
git clone https://github.com/aireliability/aireliability.git
cd aireliability
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

*(PyPI release `pip install aireliability` is scheduled for upcoming Phase releases).*

---

## 5. Quick Start

### Initialize a Project
The `airel` command-line tool initializes configuration, test directories, and storage:

```bash
airel init
```

This creates:
- `aireliability.json`: Project configuration and baseline settings.
- `tests/reliability/`: Directory for JSON/Python reliability test cases.
- `.aireliability/aireliability.db`: Local SQLite database for persistent tracking.
- `agent.py`: Starter agent entrypoint (`agent:app`).

### Run Tests and Establish Baseline
```bash
# Run tests and save the results as the active reference baseline
airel test --save-baseline
```

---

## 6. Test Examples

### A. Python Programmatic API
```python
from aireliability.core.models import TestCase, TraceStep, StepType
from aireliability.execution import ReliabilityRunner
from aireliability.evaluation import ToolCalled, ToolOrder, OutputContains, MaxLatency

# 1. Define a test case
test = TestCase(
    id="tc_order_cancellation",
    name="order_cancellation",
    input={"order_id": "ORD-1234"},
    expected_output="Refund issued",
)

# 2. Configure deterministic assertions
evaluators = [
    ToolCalled("verify_order"),
    ToolOrder(["verify_order", "process_refund"]),
    OutputContains("Refund issued"),
    MaxLatency(1500.0),
]

# 3. Execute agent with ReliabilityRunner
runner = ReliabilityRunner(agent=my_agent, evaluators=evaluators)
result = runner.run(test)

print(f"Passed: {result.passed}")
for evaluation in result.evaluations:
    print(f"  {evaluation.evaluator}: {'PASS' if evaluation.passed else 'FAIL'}")
```

### B. Standard Deterministic Assertions
| Assertion | Verifies |
| :--- | :--- |
| `ToolCalled(name, min_calls=1)` | Tool was executed at least $N$ times. |
| `ToolNotCalled(name)` | Forbidden or dangerous tool was not invoked. |
| `ToolOrder(["tool_a", "tool_b"])` | Tool invocation sequence respects specified order. |
| `ToolArguments(name, expected_args)` | Tool received required keyword parameters. |
| `OutputContains(substring)` | Output contains mandatory string or identifier. |
| `OutputEquals(expected)` | Exact match against expected target value. |
| `SchemaMatch(schema)` | Output validates against a JSON schema or Pydantic model. |
| `MaxLatency(max_ms)` | Total execution latency does not exceed threshold. |
| `MaxCost(max_cost)` | Computed token/API financial cost stays within budget. |

---

## 7. Failure Reports

When an assertion fails, the `FailureAnalyzer` maps the failure into a structured, typed `FailureReport` with confidence scoring and evidence payloads:

```text
========================================
Tests:       1
Passed:      0
Failed:      1
Regressions: 1
========================================
  ✗ FAIL order_cancellation (42.1ms)
      [TOOL] Expected tool order subsequence not satisfied.
             Expected: verify_order → process_refund
             Actual:   process_refund
```

Inspect stored failure reports via the CLI:
```bash
airel failures --limit 10
```

---

## 8. Regression Workflow

The core differentiator of `aireliability` is automated regression handling:

$$\text{Detected Failure} \longrightarrow \text{Synthesize Regression Test} \longrightarrow \text{Gate Future Deployments}$$

### Baseline Comparison States
When running tests against a baseline, outcomes are categorized into five unambiguous states:

1. **`PASSING`**: Previously passing, still passing.
2. **`REGRESSION`**: **Previously passing, now failing**. (Blocks CI).
3. **`KNOWN_FAILURE`**: Previously failing, still failing. (Does not block feature progress).
4. **`FIXED`**: Previously failing, now passing.
5. **`NEW`**: Test not present in baseline.

### Synthesizing Regression Tests
```python
from aireliability.regression import RegressionGenerator

generator = RegressionGenerator()
regression_test = generator.generate(
    failure=result.failures[0],
    test_case=test,
)

print(f"Synthesized: {regression_test.name}")
print(f"Preserved Provenance: {regression_test.source_failure_id}")
```

Inspect synthesized regression tests via CLI:
```bash
airel regressions
```

---

## 9. CI/CD Integration

`aireliability` is built specifically for continuous integration and pull request verification. Every code change automatically verifies linting, multi-Python unit tests, package distribution, clean installation, and deterministic reliability regression testing.

### CI Workflow Architecture

```text
Code Change / PR
        │
  ┌─────┴────────────────────────┐
  ▼                              ▼
ci.yml (Core CI)           reliability.yml (Reliability CI)
  ├── Ruff Lint & Format     ├── Deterministic Scenarios (A–F)
  ├── Python 3.11, 3.12, 3.13 ├── Baseline Comparison (PASS/FIXED/KNOWN/REGRESSION)
  ├── Pytest + JUnit XML     ├── $GITHUB_STEP_SUMMARY Reporting
  ├── Package Build (wheel)  └── Artifact Upload (JSON + Markdown)
  └── Clean Venv Install
```

### CLI Command Gates

```bash
# Strict CI evaluation against baseline
airel test --ci --report-json report.json --report-markdown report.md

# Compare current execution against an established baseline
airel compare default --report-json cmp.json --report-markdown cmp.md
```

- **Exit Code `0`**: Clean run (all tests pass, zero regressions, known failures permitted).
- **Exit Code `1`**: Failure or genuine regression (`PASS → FAIL`) detected.
- **Exit Code `2`**: Configuration or environment error.

See [`docs/ci-reliability.md`](docs/ci-reliability.md) for full architecture details, baseline state semantics, and local reproduction workflows.

---

## 10. Extending Evaluators

Custom evaluators can be created by implementing the `Evaluator` protocol:

```python
from aireliability.core.models import EvaluationResult, ExecutionTrace, TestCase
from aireliability.core.protocols import Evaluator


class NoPIIEvaluator(Evaluator):
    """Custom evaluator to ensure no sensitive email or SSN patterns leak in output."""

    name = "NoPIIEvaluator"

    def evaluate(self, trace: ExecutionTrace, test_case: TestCase) -> EvaluationResult:
        import re

        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        found = re.findall(email_pattern, str(trace.output or ""))

        passed = len(found) == 0
        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message="No PII detected" if passed else f"Found leaked emails: {found}",
            evidence={"leaked_emails": found} if not passed else None,
        )
```

See [`examples/custom_evaluator_and_adapter.py`](examples/custom_evaluator_and_adapter.py) for a complete working implementation.

---

---

## 11. Real Agent Integration

`aireliability` keeps its core dependency-free: it does not force installations of OpenAI, Anthropic, LangChain, or other LLM frameworks. Instead, it observes real AI agents via lightweight **Execution Adapters**.

```text
Real Agent (Python Callable, Class, LangChain, or REST API)
       ↓
ExecutionAdapter (e.g. CallableAdapter)
       ↓
aireliability ExecutionTrace (TraceStep events, tool calls, latency)
       ↓
Evaluators (ToolOrder, SchemaMatch, etc.)
       ↓
FailureReport → RegressionTest
```

### Why Adapters Exist
- **Dependency Isolation**: Prevents dependency conflicts between divergent agent packages.
- **Provider-Agnostic Tracing**: Any agent emitting events or tool executions can be evaluated.
- **Audit Provenance**: Captures exact input, output, start/end timestamps, and tool sequences.

### Using `CallableAdapter`
The built-in `CallableAdapter` works out of the box with ordinary Python functions or custom agent objects:

```python
from aireliability import CallableAdapter, ReliabilityRunner, TestCase, ToolOrder
from examples.local_agent import LocalSupportAgent

agent = LocalSupportAgent(mode="nominal")
adapter = CallableAdapter(agent=agent)

test = TestCase(
    id="refund_flow",
    name="refund_flow",
    input="I want a refund for order 123.",
)

runner = ReliabilityRunner(
    agent=agent,
    adapter=adapter,
    evaluators=[
        ToolOrder(["get_order", "cancel_order", "refund_order"], exact_match=True)
    ],
)

result = runner.run(test)
print(f"Passed: {result.passed}")
```

### How Tool Calls Are Represented
Tool calls are captured as structured, JSON-compatible `TraceStep` records:
- **Tool name** (`name: str`)
- **Arguments** (`input: dict[str, Any]`)
- **Result** (`output: Any`)
- **Timing** (`started_at`, `completed_at`, `duration_ms`)
- **Status & Metadata** (`status: completed|failed`, `metadata: dict`)

See [`docs/adapters.md`](docs/adapters.md) for full architectural details and guides on writing custom adapters for external HTTP services or agent frameworks.

---

## 12. Semantic Evaluation Engine

Alongside deterministic assertions, `aireliability` includes a provider-independent **Semantic Evaluation Engine** for evaluating nuanced natural language outputs, criteria satisfaction, and semantic relevance.

```text
DETERMINISTIC EVALUATION          SEMANTIC EVALUATION
(Invariants, Tool Sequences,     (Quality Criteria, Relevance,
 JSON Schema, Latency Budgets)    Semantic Similarity)
              \                 /
               ▼               ▼
           ReliabilityRunner Composition
                      ↓
          Structured Evaluation Results
```

### Example: Composing Deterministic & Semantic Evaluators

```python
from aireliability import (
    OutputContains,
    ReliabilityRunner,
    SemanticRelevance,
    TestCase,
    ToolOrder,
)

test = TestCase(
    id="support_tc_1",
    name="order_inquiry",
    input="Where is order 123?",
    expected_output="Your order is in transit and arriving tomorrow.",
)

runner = ReliabilityRunner(
    agent=my_agent,
    evaluators=[
        # 1. Deterministic invariant: tool call sequence
        ToolOrder(["lookup_order"], exact_match=False),
        # 2. Deterministic text presence check
        OutputContains("order 123"),
        # 3. Semantic relevance & criteria check (threshold: 0.80)
        SemanticRelevance(threshold=0.80),
    ],
)

result = runner.run(test)
print(f"Passed: {result.passed}")
```

### Extensible Judge Protocol
Semantic evaluators interact with LLM providers through the provider-agnostic `SemanticJudge` protocol. A deterministic `MockSemanticJudge` is included for reproducible CI and local development without cloud API keys or costs.

See [`docs/semantic-evaluation.md`](docs/semantic-evaluation.md) for full architectural details, criteria definitions, threshold configuration, and guidelines on non-determinism.

---

## 13. Evidence-Based Root Cause Analysis

When an agent fails, `aireliability` does not merely report a red test—it automatically diagnoses the most probable cause using empirical trace evidence via `RootCauseAnalyzer`.

```text
FailureReport + ExecutionTrace
               ↓
       RootCauseAnalyzer
               ↓
        RootCauseReport
 (Primary Cause, Evidence, Causal Links)
               ↓
       RegressionGenerator
(Provenance: root_cause_id & evidence)
```

### CLI Diagnostic Inspection

Inspect recorded failures with the `--explain` flag:

```bash
airel failures --explain
```

Example diagnostic output:

```text
AI Reliability Root Cause Analysis
──────────────────────────────────
Test:    refund_flow
Status:  FAIL

Primary Detected Cause: TOOL.WRONG_ORDER (confidence: 1.00)
Cause:   Tool sequence ordering violation: expected 'get_order → cancel_order → refund_order', observed 'get_order → refund_order → cancel_order'.
```

See [`docs/root-cause-analysis.md`](docs/root-cause-analysis.md) for data schemas, causal link construction, and provenance preservation.

---

## 14. Intelligent Regression Generation

`aireliability` synthesizes **minimal, explainable, and reproducible regression test cases** from observed failure reports and root cause evidence:

```text
FailureReport + RootCauseReport
               ↓
     RegressionSynthesizer
 ├── Input & Trace Minimizer (Conservative pruning)
 ├── Failure-Type-Aware Assertion Synthesis
 └── RegressionValidator (Quality & Duplicate Checking)
               ↓
    Validated RegressionTest
 (Full Provenance: source_failure_id & root_cause_id)
```

### Key Capabilities

* **Failure-Type-Aware Expectations**: Generates minimal tool ordering, arguments, tool calls, exact/schema output, or semantic thresholds tailored to the failure.
* **Conservative Minimization**: Safely reduces large inputs and pruned trace steps only when supported by empirical evidence.
* **Duplicate Detection**: Identifies equivalent tests and avoids polluting test repositories with redundant regression cases.
* **Quality Invariant Checks**: Verifies reproducibility, specificity (rejecting trivial checks), identity, and traceability.

Inspect regression tests with provenance details via the CLI:
```bash
airel regressions --details
```

See [`docs/regression-generation.md`](docs/regression-generation.md) for the complete architecture and minimization specifications.

---

## 15. Framework Integrations

`aireliability` provides optional, pluggable adapters to test agents built with modern orchestration frameworks without polluting core dependencies:

* **LangGraph Adapter**: Captures graph streaming and state updates, mapping `AIMessage.tool_calls` and `ToolMessage` instances into normalized `ToolCallRecord` steps.
* **LangChain Adapter**: Hooks into standard `BaseCallbackHandler` lifecycle events (`on_tool_start`, `on_tool_end`, `on_tool_error`) without monkey-patching internal classes.
* **Async & Sync Support**: All adapters support both `execute()` and asynchronous `aexecute()`.

### Installation
```bash
# Core remains dependency-free
pip install aireliability

# Optional framework integrations
pip install "aireliability[langgraph]"
pip install "aireliability[langchain]"
```

See [`docs/integrations.md`](docs/integrations.md) for architectural details, custom adapter implementation guides, and security considerations.

---

## 16. Provider-Neutral AI Model Integration

`aireliability` includes a provider-neutral model and tool execution adapter layer. It enables developers to observe, trace, evaluate, and diagnose agent interactions across any OpenAI-compatible API endpoint (including OpenAI, Azure OpenAI, vLLM, Ollama, LiteLLM, Groq, Together, and local inference engines) without locking the core package into vendor SDKs:

* **Normalized Tracing**: Maps chat completions, streaming deltas, and tool calls into standard `ExecutionTrace` and `ToolCallRecord` records with latency and token usage.
* **Streaming Delta Aggregation**: Transparently accumulates streaming token deltas and tool call chunks into coherent execution traces while recording `STREAM_START`, `STREAM_CHUNK`, and `STREAM_END` events.
* **Automatic Metadata Sanitization**: Redacts sensitive credentials (`api_key`, `token`, `secret`, `authorization`) from execution trace metadata.
* **Offline CI Compatibility**: Works seamlessly with mock clients, duck-typed handlers, or official SDK clients without requiring live network access or paid API keys.

```bash
# Core remains dependency-free
pip install aireliability

# Optional OpenAI-compatible client integration
pip install "aireliability[openai]"
```

See [`docs/provider-integration.md`](docs/provider-integration.md) for architectural details, streaming examples, and performance benchmarks.

---

## 17. Production Observability & Telemetry

`aireliability` includes a lightweight, framework-neutral telemetry layer designed for production observability and continuous verification. It captures execution trees, model invocations, tool executions, token usage, latency, failures, and root-cause diagnoses without locking your stack to vendor agents:

* **Zero Mandatory Dependencies**: Built using standard Python primitives and `pydantic`.
* **Hierarchical Traces & Spans**: Represents executions as nested trees (`agent.name` → `model.call`, `tool.call`, `eval.name`, `analysis.root_cause`).
* **Configurable Collectors**: Switch between `NoOpTelemetryCollector` (~6 µs overhead), `InMemoryTelemetryCollector` (~37 µs), and `JsonTelemetryCollector` (~37 µs).
* **Recursive Metadata Sanitization**: Automatically redacts API keys, auth headers, tokens, and passwords from all telemetry payloads.
* **Optional OpenTelemetry & Prometheus Integrations**: Pluggable exporters for enterprise OTel collectors and Prometheus metric scraping.
* **Flexible Sampling**: Supports `AlwaysOnSampler`, `AlwaysOffSampler`, and seeded `RatioSampler` for deterministic testing.

```bash
# Enable telemetry during test runs
airel test --telemetry --telemetry-output traces.json
```

See [`docs/observability.md`](docs/observability.md) for architectural details, schema specifications, and Prometheus metric definitions.

---

## 18. Distributed Reliability & Async Execution

`aireliability` provides a high-throughput asynchronous execution and distributed worker layer for evaluating test cases and regression suites concurrently without external brokers:

* **Bounded Concurrency Semaphore**: Run large test matrices across parallel worker pools with configurable concurrency (`max_concurrency`).
* **Deterministic Result Sorting**: Concurrently executed results are deterministically aggregated into original test order for reproducible CI reports.
* **Per-Test Timeouts & Cancellation**: Enforce timeouts on unresponsive agent runs and gracefully handle cancellations.
* **Automated Transient Retries**: Automatically retry transient or network errors while preserving attempt numbers and failure provenance.
* **Parallel Regression Execution**: Run entire `RegressionTest` suites concurrently with `RegressionRunner.run_suite_async()` and baseline comparison.
* **Asynchronous Telemetry Buffering**: Queue telemetry traces into `AsyncTelemetryCollector` with non-blocking enqueuing and background flushing.

```python
from aireliability import AsyncReliabilityRunner, TestCase

runner = AsyncReliabilityRunner(
    agent=my_agent, max_concurrency=10, test_timeout_seconds=5.0
)
summary = await runner.execute_many(test_cases)
```

See [`docs/distributed-execution.md`](docs/distributed-execution.md) for architectural details and performance benchmarks.

---

## 19. Production Persistence & Distributed Infrastructure

`aireliability` provides production persistence and multi-process/multi-node execution infrastructure without mandatory external database dependencies:

* **Unified Persistence Abstraction**: `DistributedPersistenceBackend` and `AsyncDistributedPersistenceBackend` protocols for managing executions, workers, jobs, outcomes, and retries.
* **Production SQLite Backend**: `SQLiteDistributedStorage` provides ACID transactions via WAL mode, connection safety, schema migrations, and index optimization.
* **Deterministic State Machines**: Transition enforcement for `JobStatus` and `WorkerState` preventing illegal lifecycle jumps.
* **Atomic Job Claiming**: Prevents duplicate executions of the same job attempt using transactional conditional updates.
* **Stale Worker Detection & Recovery**: Detects worker crashes via periodic heartbeats (`detect_stale_workers`) and requeues interrupted jobs (`recover_execution`) without losing historical provenance.
* **Execution Resumption**: `resume_execution()` restarts interrupted runs, preserving already completed tests and only executing unfinished jobs.
* **CLI Execution & Worker Management**: `airel executions list|show|resume|recover` and `airel workers list|stale`.
* **Optional Integrations**: Enterprise `PostgresDistributedStorage` (`aireliability[postgres]`) and `RedisDistributedCoordinator` (`aireliability[redis]`).

```python
from aireliability import AsyncReliabilityRunner, SQLiteDistributedStorage, TestCase

storage = SQLiteDistributedStorage(".aireliability/runs.db")
runner = AsyncReliabilityRunner(
    agent=my_agent,
    storage=storage,
    max_concurrency=10,
)
# Resume interrupted runs seamlessly
summary = await runner.resume_execution("exec_12345")
```

See [`docs/persistence.md`](docs/persistence.md) for complete details.

---

## 20. Production Control Plane & Intelligent Job Scheduling (Phase 25)

Phase 25 introduces a decoupled, provider-neutral control plane coordinating job queues, worker capacities, intelligent scheduling policies, cooperative cancellations, and automated retries.

```python
import asyncio
from aireliability import (
    ControlPlane,
    ControlPlaneConfig,
    JobPriority,
    RetryPolicy,
    BackoffStrategy,
    TestCase,
)


async def run_control_plane():
    def agent(inputs):
        return {"output": "processed"}

    config = ControlPlaneConfig(
        max_concurrency=5,
        scheduling_policy="fair",  # Prevents starvation with priority aging
        default_retry_policy=RetryPolicy(
            max_retries=3,
            strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay_seconds=1.0,
        ),
    )
    cp = ControlPlane(agent=agent, config=config)

    tc = TestCase(id="tc_001", name="Priority Case", input={"q": "test"})
    await cp.submit_job(tc, priority=JobPriority.CRITICAL)

    summary = await cp.execute_execution([tc])
    print(f"Executed: {summary.completed_jobs}/{summary.total_jobs}")
    await cp.stop()


asyncio.run(run_control_plane())
```

See [`docs/control-plane.md`](docs/control-plane.md) for complete architecture and benchmarks.

---

## 21. Fault Tolerance, Resilience & Self-Healing (Phase 26)

Phase 26 transforms `aireliability` into a resilience-aware reliability platform capable of detecting failures, isolating unhealthy workers, recovering automatically, preventing cascading failure storms, and restoring interrupted executions without mandatory external infrastructure:

* **Deterministic Failure Classification**: Maps raw exceptions and errors into a structured `DetailedFailureRecord` across 12 distinct operational categories while enforcing recursive credential sanitization.
* **Three-State Circuit Breakers**: `CircuitBreaker` isolates unhealthy model providers or workers across `CLOSED`, `OPEN`, and `HALF_OPEN` states.
* **Resilient Retry & Backoff**: Exponential backoff with uniform random spread (jitter) to prevent retry stampedes on upstream providers.
* **Bulkhead Concurrency Isolation**: Bounded concurrency limits partition resources independently across model providers and priority tiers.
* **Worker Health & Automatic Quarantine**: Tracks worker consecutive failures and degrades/quarantines unhealthy workers (`HEALTHY` → `DEGRADED` → `QUARANTINED` → `RECOVERING`).
* **Self-Healing Recovery**: Quarantined workers are automatically recovered through probe requests while preserving provenance and metrics.
* **Failure Storm Protection & Load Shedding**: Rolling failure rate window monitoring dynamically sheds lower-priority load under severe overload or upstream outages.
* **Multi-Component Health Checks**: Non-invasive diagnostic health probes for storage, schedulers, and workers.
* **Resilience Operations CLI**: `airel resilience status|failures|workers|circuits|quarantine|unquarantine|recover`.

```bash
# Inspect resilience subsystem health and active circuit breakers
airel resilience status
airel resilience circuits
```

See [`docs/resilience.md`](docs/resilience.md) for complete architecture, telemetry events, and benchmark results.

---

## 22. Roadmap

- [x] **Phase 1**: Package Foundation & Project Architecture
- [x] **Phase 2**: Core Domain Data Models & Protocols
- [x] **Phase 3**: Framework-Agnostic Interfaces (`ExecutionAdapter`, `Evaluator`)
- [x] **Phase 4**: Deterministic Assertions & Tracing Primitives
- [x] **Phase 5**: Execution Engine (`ReliabilityRunner`)
- [x] **Phase 6**: Structured Failure Taxonomy & `FailureAnalyzer`
- [x] **Phase 7**: Automated Regression Generation & Baseline Management
- [x] **Phase 8**: Serverless Storage Engine (`SQLiteStorage`)
- [x] **Phase 9**: Developer CLI (`airel`)
- [x] **Phase 10**: CI/CD Workflows, GitHub Actions & Packaging
- [x] **Phase 11**: Reproducible Benchmarks (< 0.04ms overhead)
- [x] **Phase 14**: Real-World Reliability Benchmark (Scenarios A–F)
- [x] **Phase 15**: Real Agent Integration Layer (`CallableAdapter`)
- [x] **Phase 16**: Semantic Evaluation Engine (`SemanticJudge`, `SemanticExpectation`)
- [x] **Phase 17**: Evidence-Based Root Cause Analysis (`RootCauseAnalyzer`)
- [x] **Phase 18**: Intelligent Regression Generation (`RegressionSynthesizer`, `RegressionValidator`)
- [x] **Phase 19**: Framework Integration Layer (`LangGraphAdapter`, `LangChainAdapter`)
- [x] **Phase 20**: CI/CD + Pull Request Reliability Workflows
- [x] **Phase 21**: Provider-Neutral AI Model Integration (`OpenAICompatibleAdapter`, `ProviderAdapter`)
- [x] **Phase 22**: Production Observability & Telemetry (`TelemetryTrace`, `TelemetryCollector`, OTel/Prometheus)
- [x] **Phase 23**: Distributed Reliability & Async Execution (`AsyncReliabilityRunner`, `ReliabilityWorker`, `ResultAggregator`)
- [x] **Phase 24**: Production Persistence & Distributed Infrastructure (`SQLiteDistributedStorage`, `DistributedPersistenceBackend`)
- [x] **Phase 25**: Production Control Plane & Intelligent Job Scheduling (`ControlPlane`, `JobQueue`, `JobScheduler`, `WorkerManager`)
- [x] **Phase 26**: Fault Tolerance, Resilience & Self-Healing (`ResilienceManager`, `CircuitBreaker`, `Bulkhead`, `WorkerHealthManager`)
- [x] **Phase 27**: Multi-Tenancy, Isolation & Resource Governance (`ResourceGovernanceManager`, `TenantAccessPolicy`, Quotas, Rate Limiting, Fair Scheduling)
- [x] **Phase 28**: Secure API Gateway, Authentication & Authorization (`SecurityGateway`, `APIKeyManager`, `AuthorizationEngine`, RBAC, Replay Protection, Audit Logging)
- [x] **Phase 30**: Evaluation Architecture & Specification (`docs/phase30-evaluation-architecture.md`)
- [x] **Phase 31**: Evaluation Intelligence Engine (Unified Metrics, Generation, Claims, RAG, Agents, LLM-as-a-Judge, Robustness, Safety, Privacy, Cost)
- [x] **Phase 32**: Evaluation Operations & Governance (Unified Scoring with Critical Veto, Release Gates, Baselines, History Trends, Multi-Format Reports)
- [x] **Phase 33**: Developer Platform & Production Integration (CLI Workflows, Evaluation Profiles, CI/CD Actions, Closed Production Feedback Loop)
- [x] **Phase 34**: AI Reliability Intelligence (`ReliabilityIntelligenceEngine`, Clustering, Patterns, Trends, Recommendations)
- [x] **Phase 35**: AI Reliability Knowledge Graph (`KnowledgeGraph`, Lineage, Blast Radius, Impact Analysis)
- [x] **Phase 36**: Automated AI Test Generation (`TestGenerationEngine`, 14 Strategies, Deduplication, Quality Scoring, Promotion)
- [x] **Phase 37**: Closed-Loop Self-Healing Engine (`RemediationEngine`, 6 Repairers, Simulation, Approvals, Canary/Shadow Rollouts)
- [x] **Phase 39**: Advanced RAG Reliability Engine (`AdvancedRAGReliabilityEngine`, 11 Stages, Claim-Evidence Alignment, Inline Citation Validation, Knowledge Base & Freshness Audits, Drift Detection, Multi-Hop Tracing, Bridges to Phases 34–38)
- [x] **Phase 40**: Advanced Agent Reliability Engine (`AdvancedAgentReliabilityEngine`, 15 Stages, Trajectory Analysis, Plan vs Execution, Tool & Argument Auditing, Loop & Runaway Detection, Multi-Agent Handoffs, Independent Goal Verification, Bridges to Phases 34–39)

---

## 23. AI Evaluation Platform (v0.2.0)

Version 0.2.0 expands `aireliability` into a complete, modular, provider-independent AI Evaluation, Reliability, and Governance platform.

### Core Capabilities

1. **Unified Evaluation Intelligence Engine (Phase 31)**:
   - **Classification & Ranking Metrics**: Accuracy, Precision, Recall, F1, F-beta, Specificity, Sensitivity, Balanced Accuracy, MCC, Confusion Matrix, Precision@K, Recall@K, Hit@K, MRR, MAP, NDCG@K.
   - **Generation Quality & Claim Verification**: Deterministic formatting/schema checks, semantic evaluators, atomic claim extraction, evidence matching, 3-state classification, and hallucination rate calculation.
   - **RAG & Agent Trajectory Auditing**: Context precision/recall/relevance, citation validation, tool selection, argument correctness, ordering, and loop detection.
   - **Safety, Security & Privacy**: Toxicity, jailbreak, prompt injection, system prompt leakage, PII masking, and credentials leakage detection.
   - **LLM-as-a-Judge & Evaluator Reliability**: Multi-provider adapters (OpenAI, Anthropic, Gemini, Ollama, custom/local) with Cohen's/Fleiss' Kappa, Brier calibration score, and length/position bias detection.
   - **FinOps & Performance**: Latency percentiles (P50, P90, P95, P99), TTFT, throughput, token usage, and customizable pricing engines.

2. **Operations & Governance (Phase 32)**:
   - **Multidimensional Reliability Scoring**: Configurable dimensional weighting with **non-compensatory critical veto** (safety/security violations immediately block deployment, preventing high scores from masking critical risks).
   - **Release Gates**: PASS, FAIL, and BLOCK decisions with customizable quality, latency, regression, and safety policies.
   - **Versioned Baselines & Trend Analysis**: `EvaluationBaselineManager` tracking reference snapshots across models and prompts; `EvaluationHistoryManager` computing regression and improvement slopes.
   - **Multi-Format Reporting**: Terminal CLI, JSON, JSONL, CSV, Markdown, GitHub PR comments, JUnit XML, and interactive standalone HTML dashboards with SVG radar charts.

3. **Developer Platform & Production Feedback Loop (Phase 33)**:
   - **Evaluation Profiles**: Reusable profiles (`rag`, `agent`, `classification`, `generation`, `safety`, `performance`, `cost`, `production`, `full`).
   - **CLI Platform**: Extended commands for running evaluations, inspecting datasets, calculating reliability scores, enforcing release gates, assessing judges, testing robustness, and diffing regressions.
   - **Closed Production Feedback Loop**: `ContinuousReliabilityMonitor` live sliding-window scoring, `ProductionSampler`, and `ProductionRegressionHarvester` automatically synthesizing production failures into golden regression test cases with `IncidentManager` correlation.

```bash
# Evaluate an agent with the RAG profile
airel evaluate run --agent agent:app --dataset datasets/qa.json --profile rag

# Enforce release gate policy with non-compensatory veto
airel gate --report report.json --min-score 0.85 --fail-on-regression

# Diff evaluation candidate against reference baseline
airel regression diff --candidate candidate_report.json --baseline baselines/prod_v1.json

# Serve interactive evaluation dashboard locally
airel dashboard --report report.json --port 8080
```

---

## 24. AI Reliability Intelligence (v0.3.0 / Phase 34)

Version 0.3.0 introduces an intelligence layer on top of evaluation, regression, diagnosis, observability, security, and production monitoring. It transforms raw failure data into actionable, evidence-backed reliability intelligence.

### Workflow & Architecture

```text
Evaluation Runs & Traces
          │
          ▼
Failure Normalization & Privacy Sanitization (FailureNormalizer)
          │
          ▼
Deterministic Structural Clustering (FailureClusterer)
          │
          ▼
Longitudinal Pattern Detection (PatternDetector)
          │
          ▼
Cross-Run Configuration Correlation (CorrelationAnalyzer)
          │
          ▼
Longitudinal Trajectory & Trend Analysis (TrendAnalyzer)
          │
          ▼
Operational & Risk Impact Assessment (ImpactAnalyzer)
          │
          ▼
Confidence Engine & Evidence Preservation (ConfidenceEngine & EvidenceReference)
          │
          ▼
Intelligent Remediation Recommendations (RecommendationEngine)
          │
          ▼
Explainable 10-Question Synthesis (IntelligenceExplainer & IntelligenceAnalysis)
```

### Answering the 10 Core Questions

1. **What failed?** Categorical failure taxonomy breakdown, representative failure signatures, and cluster sizing.
2. **Why did it fail?** Root cause intelligence mapped to retrieval, tool, model, or task issues.
3. **Has this failure happened before?** Historical recurrence count, first seen / last seen timestamps, persistent patterns.
4. **Are multiple failures related?** Deterministic clustering via SHA-256 fingerprints and structural similarity.
5. **Is this failure getting worse?** Longitudinal slope, relative change, and volatility classification (`INCREASING`, `DECREASING`, `STABLE`, `VOLATILE`).
6. **What components are associated with the failures?** Isolation to specific retrievers, tools, prompts, or model versions.
7. **What is the impact?** Rigorous risk assessment (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), treating safety/security breaches as non-negotiable critical impacts.
8. **How confident are we?** Categorical confidence rating (`VERY_LOW` to `VERY_HIGH`) based on evidence count, sample size, agreement, and completeness.
9. **What evidence supports the conclusion?** Non-invasive citations to evaluation runs, traces, root causes, test IDs, and baselines.
10. **What should an engineer investigate or fix first?** Deterministic, prioritized remediation actions linked to release gates, regression suites, and prompts.

### Python API Example

```python
from aireliability.intelligence import ReliabilityIntelligenceEngine
from aireliability.evaluation.models import EvaluationReport

# Initialize the intelligence engine (offline, deterministic by default)
engine = ReliabilityIntelligenceEngine()

# Analyze an evaluation report against reference baseline and historical runs
analysis = engine.analyze(
    report=current_report,
    baseline_report=baseline_report,
    history=history_manager,
)

# Inspect high-level summary
print(f"Failures: {analysis.summary.total_failures_analyzed}")
print(f"Clusters: {analysis.summary.total_clusters}")
print(f"Critical Issues: {analysis.summary.critical_issues_count}")

# Print human-readable report answering the 10 core questions
print(engine.explain_text(analysis))

# Access prioritized remediation recommendations
for rec in analysis.recommendations:
    print(f"[{rec.priority}] {rec.title}: {rec.suggested_action}")
```

### CLI Intelligence Commands

```bash
# Run comprehensive intelligence analysis on an evaluation report
airel intelligence analyze report.json

# Output machine-readable JSON analysis
airel intelligence analyze report.json --json

# Inspect normalized failure fingerprints and affected components
airel intelligence failures report.json

# Group failures into deterministic structural clusters
airel intelligence clusters report.json

# Detect recurring, newly introduced, or component-specific patterns
airel intelligence patterns report.json --history evaluations/

# Track metric trajectories and rates of change over historical evaluations
airel intelligence trends report.json --history evaluations/ --metric hallucination_rate

# Assess operational risk and safety criticality
airel intelligence impact report.json --critical-only

# Generate evidence-backed remediation recommendations
airel intelligence recommendations report.json --priority HIGH

# Output answers to all 10 core AI reliability intelligence questions
airel intelligence explain report.json
```

---

## 25. AI Reliability Knowledge Graph (v0.4.0 / Phase 35)

Version 0.4.0 transforms `aireliability` from a system that diagnoses isolated reliability failures into a platform that understands relationships, dependencies, and blast radius across the entire AI lifecycle.

The Knowledge Graph connects datasets, test cases, execution traces, models, prompt templates, tools, retrievers, evaluation reports, failures, diagnosed root causes, regression tests, operational incidents, and Phase 34 intelligence outputs into an explainable, deterministic graph topology.

### Conceptual Architecture

```text
              Dataset
                 │
                 ▼
              TestCase
                 │
                 ▼
           ExecutionTrace
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
  Model        Prompt        Tool
    │            │            │
    └────────────┼────────────┘
                 ▼
             Evaluation
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
     Metric   Failure   Evidence
                 │
                 ▼
             RootCause
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
  Regression            Incident
       │
       ▼
Golden Dataset / Phase 34 Intelligence (Clusters, Patterns, Trends, Recommendations)
```

### Answering the 10 Core Graph Questions

1. **What is connected to this failure?** Traversal to upstream evaluation, execution steps, models, prompts, tools, and downstream root causes, regressions, and incidents.
2. **Which models are associated with the most failures?** Topological queries identifying failure nodes linked via `USED_MODEL` or empirical correlations.
3. **Which prompts are associated with regressions?** Paths connecting prompt templates through evaluations and failure reports to synthesized regression tests.
4. **Which retrievers are associated with hallucination increases?** Trace step and evaluation paths linking retrieval components to context-grounding failure clusters.
5. **Which root causes affect the largest number of evaluations?** Predecessor and successor degree aggregations over diagnosed root-cause nodes.
6. **Which incidents originated from the same reliability pattern?** Multi-hop paths from incidents through failure nodes to Phase 34 `FailureCluster` and `FailurePattern` entities.
7. **What components are affected by a specific model change?** Quantitative downstream blast radius analysis (`GraphImpactAnalyzer`).
8. **What failures occurred after a configuration change?** Temporal metadata queries identifying events within validity windows.
9. **What is the dependency/impact path from an execution to an incident?** Shortest directed pathfinding (`find_path`) tracing execution traces to P0/P1 incidents.
10. **What historical evidence supports a reliability relationship?** Non-invasive `ProvenanceTracer` inspecting citations, source runs, confidence ratings, and empirical evidence.

### Correlation vs. Causation Separation

The graph strictly enforces the boundary between correlation and verified causality:
- `GraphRelationship.CORRELATED_WITH`: Used for co-occurrence and empirical correlations (`is_causal=False`). Temporal proximity or frequency alone never infers causality.
- Causal relationships (`FAILED`, `HAS_ROOT_CAUSE`, `CAUSED_REGRESSION`, `TRIGGERED`): Assigned `is_causal=True` only when direct empirical or programmatic assertion evidence exists.

### Python API Example

```python
from aireliability.graph import (
    KnowledgeGraph,
    KnowledgeGraphBuilder,
    GraphNodeType,
    GraphRelationship,
)
from aireliability.graph.serialization import GraphSerializer, diff_graphs

# 1. Initialize builder and ingest evaluation artifacts idempotently
builder = KnowledgeGraphBuilder()
builder.from_evaluation(report, model_name="gpt-4o", prompt_name="clinical_prompt_v1")
builder.from_failure(failure_report)
builder.from_incident(incident_record)
builder.from_intelligence(intelligence_analysis)

graph = builder.graph
print(f"Graph initialized with {graph.node_count} nodes and {graph.edge_count} edges.")

# 2. Query failures associated with a model
failures = graph.query.find_failures_for_model("gpt-4o")
for f in failures:
    print(f"Failure: {f.node_id} ({f.name})")

# 3. Assess quantitative blast radius and impact
impact = graph.impact_analyzer.analyze("model:gpt-4o")
print(f"Impact Score: {impact.impact_score}")
print(f"Failures: {impact.failure_count}, Incidents: {impact.incident_count}")
print(f"Security Critical: {impact.security_critical}")

# 4. Trace lineage and explain relationships
lineage = graph.provenance.get_lineage("failure:f_001")
print(f"Upstream dependencies: {lineage['upstream_count']}")

explanations = graph.provenance.explain_relationship("model:gpt-4o", "incident:inc_101")
for exp in explanations:
    print(f"Explanation: {exp['summary']}")

# 5. Export and compare snapshots
GraphSerializer.export_json(graph, "snapshots/run_v1.json")
diff = diff_graphs(graph, previous_graph)
if diff.has_changes:
    print(
        f"Added nodes: {len(diff.added_nodes)}, Removed nodes: {len(diff.removed_nodes)}"
    )
```

### CLI Knowledge Graph Commands

```bash
# Build knowledge graph snapshot from evaluation or trace JSON artifact
airel graph build report.json -o graph.json

# Inspect graph topology summary and distributions
airel graph inspect graph.json

# Output inspect summary in machine-readable JSON
airel graph inspect graph.json --json

# Query nodes by classification type
airel graph query graph.json --type MODEL

# List adjacent neighbors with direction filter
airel graph neighbors graph.json --node model:gpt-4o --direction outgoing

# Find directed shortest path between two nodes
airel graph path graph.json --from model:gpt-4o --to incident:inc_101

# Calculate blast radius and downstream impact assessment
airel graph impact graph.json --node model:gpt-4o

# Find failures linked to components
airel graph failures graph.json --model gpt-4o

# Find regressions associated with datasets
airel graph regressions graph.json --dataset golden_clinical_v1

# Find incidents triggered by root causes
airel graph incidents graph.json --root-cause rc_context_leak

# Trace history and timeline of a root cause
airel graph root-causes graph.json --id root_cause:rc_context_leak

# Export graph state to JSON, CSV edge list, or JSON Lines
airel graph export graph.json -o edges.csv --format csv
airel graph export graph.json -o graph.jsonl --format jsonl

# Compute structural differences between two graph runs
airel graph diff run_a.json run_b.json
```

---

## 26. Automated AI Test Generation (v0.5.0 / Phase 36)

Version 0.5.0 introduces a deterministic-first **Automated AI Test Generation Engine** that transforms reliability evidence (failure reports, operational incidents, production execution traces, knowledge graph paths, and intelligence patterns) into high-quality, executable test cases and safely promotes them into regression suites and golden datasets.

### Pipeline Architecture

```text
Evidence (Failures, Traces, Incidents, Graphs, Patterns)
   ↓
Source Normalization
   ↓
14 Generation Strategies
   ↓
Candidate Generation
   ↓
Validation (Schema, Assertions, Safety, Credentials Audit)
   ↓
Deduplication (Exact SHA-256 + Token Jaccard Similarity)
   ↓
Quality Scoring (Explainable Multi-Factor Scoring)
   ↓
Selection & Budgeting (Budgets, Diversity, Priority)
   ↓
Promotion (Golden Dataset / Regression Suite)
   ↓
Knowledge Graph Sync + Provenance Linking
```

### The 14 Generation Strategies

1. **Failure-Driven** (`FailureTestGenerator`): Converts `FailureReport` and `EvaluationReport` items into targeted regression guards.
2. **Regression-Driven** (`RegressionTestGenerator`): Synthesizes tests from `RegressionTest` and `EvaluationComparisonResult` baseline diffs.
3. **Graph-Driven** (`GraphTestGenerator`): Traverses `KnowledgeGraph` failure and impact paths to guard unhedged components.
4. **Pattern-Driven** (`PatternTestGenerator`): Generates tests targeting Phase 34 `FailurePattern`, `FailureCluster`, and remediation recommendations.
5. **Incident-Driven** (`IncidentTestGenerator`): Converts operational `IncidentRecord` entries into permanent regression protection.
6. **Production-Trace-Driven** (`TraceTestGenerator`): Converts sampled `ExecutionTrace` steps into replay tests with mandatory `SanitizationPolicy` credential redaction.
7. **Edge-Case** (`EdgeCaseGenerator`): Synthesizes deterministic boundary, null, extreme length, unicode, and malformed inputs.
8. **Mutation-Based** (`MutationGenerator`): Controlled, bounded mutations targeting prompts, contexts, retrieval chunks, and tool schemas.
9. **Adversarial** (`AdversarialTestGenerator`): Probes prompt injection overrides, instruction conflicts, and malformed outputs offline.
10. **Safety/Security/Privacy** (`SafetyTestGenerator`): Tests against secret leakage, credential exfiltration, PII exposure, and unauthorized tool calls.
11. **RAG-Focused** (`RAGTestGenerator`): Tests retrieval grounding, document chunk contradictions, ranking noise, and citation accuracy.
12. **Agent Trajectory** (`AgentTestGenerator`): Validates tool call ordering, loop limits, parameter schemas, and error recovery.
13. **Robustness** (`RobustnessTestGenerator`): Tests model invariance against casing, punctuation, and syntactic paraphrasing.
14. **Consistency** (`ConsistencyTestGenerator`): Generates semantic test clusters expecting bounded variance across equivalent queries.

### Python API Example

```python
from aireliability.generation import (
    TestGenerationEngine,
    TestGenerationRequest,
    TestGenerationConfig,
    GenerationStrategy,
)
from aireliability.core.models import FailureReport

# 1. Create source evidence
failure = FailureReport(
    failure_id="fail_output_12",
    trace_id="tr_456",
    category="output_hallucination",
    type="unsubstantiated_claim",
    message="Hallucinated revenue numbers",
)

# 2. Execute deterministic generation
engine = TestGenerationEngine()
request = TestGenerationRequest(
    sources=[failure],
    strategies=[GenerationStrategy.FAILURE_DRIVEN],
    config=TestGenerationConfig(deterministic_seed=42),
)
result = engine.generate(request)

# 3. Inspect explainable results
for test in result.validated_tests:
    print(f"Generated: {test.name} (Quality: {test.quality_score.total_score:.2f})")
```

### CLI Commands

```bash
# General test generation
airel generate tests "Summarize the quarterly earnings report" --output tests.json

# Generate regression tests from failure report
airel generate from-failure failure_report.json --format json

# Generate adversarial test suite
airel generate adversarial "Account balance transfer" --max-candidates 5

# Generate mutations from parent test
airel generate mutations "Calculate tax" --mutation-limit 4

# Manage and audit generated tests
airel test-generation inspect tests.json
airel test-generation validate tests.json
airel test-generation promote tests.json --dataset golden_dataset.json
```

---

## 27. Self-Healing AI Reliability Engine (v0.6.0 / Phase 37)

Version 0.6.0 introduces a production-grade, closed-loop **Self-Healing AI Reliability Engine** (`aireliability.remediation`) that automatically transforms reliability evidence into targeted remediation proposals, synthesizes verification tests via Phase 36 Test Generation, simulates repairs in sandbox environments, evaluates quality and safety gates, enforces organizational healing policies, manages human and automated approvals, progressively rolls out fixes via Direct, Shadow, or Canary deployments, monitors real-time telemetry, and safely promotes or automatically rolls back configurations.

### Closed-Loop Self-Healing Workflow

```text
                    ┌──────────────────────┐
                    │ Production / Tests   │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Failure Detection    │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Diagnosis            │
                    │ Intelligence         │
                    │ Root Cause           │
                    │ Knowledge Graph      │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Remediation Engine   │
                    └──────────┬───────────┘
                               ↓
          ┌────────────────────┼────────────────────┐
          ↓                    ↓                    ↓
       Prompt              Retrieval             Tool
       Repair               Repair              Repair
          ↓                    ↓                    ↓
       Agent              Config              Safety
       Repair              Repair              Repair
          └────────────────────┼────────────────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Test Generation      │
                    │ Phase 36             │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Simulation           │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Evaluation + Gates   │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Healing Policy       │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Approval             │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Apply / Shadow /     │
                    │ Canary               │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Verification         │
                    └──────────┬───────────┘
                         ┌─────┴─────┐
                         ↓           ↓
                      PROMOTE     ROLLBACK
                         │           │
                         └─────┬─────┘
                               ↓
                    ┌──────────────────────┐
                    │ Knowledge Graph      │
                    │ Audit + Intelligence │
                    └──────────────────────┘
```

### Key Subsystems & Repair Domains

1. **Six Specialized Repair Domain Generators**:
   - `PromptRepairer`: Output formatting enforcement (strict JSON schema constraints), refusal and factuality grounding, instruction clarity.
   - `RetrievalRepairer`: RAG configuration tuning for recall expansion (`top_k`), noise filtration (similarity thresholds, neural reranking), and hybrid search.
   - `ToolRepairer`: Parameter schema corrections, missing argument fallbacks, timeout expansions, exponential retry backoff, and fallback tools.
   - `AgentRepairer`: Trajectory loop detection and cycle prevention, max step limits, plan recovery replanning.
   - `ConfigRepairer`: Model inference hyperparameters (temperature reduction for determinism, `max_tokens` expansion to prevent truncation, connection timeouts).
   - `SafetyRepairer`: PII/secret regex sanitization and redaction rules, prompt injection defense barriers.
2. **Phase 36 Test Generation Integration**: Automatically synthesizes regression, edge-case, and robustness validation suites directly against proposed repair patches.
3. **Simulation Sandbox**: Isolated dry-run execution against newly generated tests and existing golden suites.
4. **Quality & Release Gates**: `RemediationGateChecker` enforcing zero regressions, minimum recovery rates, zero safety violations, and bounded latency overhead.
5. **Organizational Healing Policy**: `HealingPolicy` governing risk tiers (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), maximum rollouts per hour rate limiting, and auto-approval permissions.
6. **HMAC-Tokenized Approval Workflow**: Cryptographic approval tokens and immutable audit trail tracking.
7. **Progressive Rollout Controller**: `RolloutController` supporting `DIRECT`, `SHADOW` (mirrored traffic), and `CANARY` (stateless consistent hashing traffic routing).
8. **Live Verification & Automated Rollback**: `RemediationVerifier` monitoring error rates and telemetry deltas; `RollbackManager` restoring previous configurations automatically upon degradation.
9. **Permanent Baseline Promotion**: `PromotionManager` promoting verified canary patches to 100% active production baselines.
10. **Knowledge Graph Synchronization**: `RemediationGraphBridge` adding `RECOMMENDATION` nodes linked via `RECOMMENDS`, `AFFECTS`, and `SUPPORTED_BY` relationships.

### Python Quickstart

```python
from aireliability.remediation import RemediationEngine, RolloutStrategy
from aireliability.core.models import FailureReport

# 1. Initialize engine
engine = RemediationEngine()

# 2. Diagnose failure and plan remediation
failure = FailureReport(
    failure_id="fail_prod_01",
    trace_id="tr_101",
    category="retrieval",
    message="retrieval failure: customer query returned 0 documents",
)
proposal = engine.diagnose_and_plan(
    failure, context={"target_component": "faq_retriever"}
)

# 3. Simulate candidate patch in sandbox against Phase 36 tests
sim_result = engine.simulate(proposal)

# 4. Operator approval (if required by policy)
appr = engine.approve(proposal, approver="alice", rationale="Staging validated")

# 5. Apply canary deployment (10% traffic)
engine.apply(proposal, strategy=RolloutStrategy.CANARY, percentage=10.0)

# 6. Verify live telemetry
is_healthy = engine.verify(proposal, sample_count=50, remediation_error_rate=0.01)

# 7. Promote verified remediation to permanent baseline
if is_healthy:
    engine.promote(proposal, actor="alice")
```

### CLI Self-Healing Commands

```bash
# 1. Diagnose failure and generate remediation plan
airel heal plan "retrieval failure: customer query returned 0 documents" --component faq_retriever --output proposal.json

# 2. Simulate candidate patch in isolated sandbox
airel heal simulate proposal.json

# 3. Approve proposal
airel heal approve proposal.json --approver alice --rationale "Staging verified"

# 4. Deploy remediation via canary
airel heal apply proposal.json --strategy canary --percentage 15

# 5. Verify live canary telemetry
airel heal verify proposal.json --samples 30 --error-rate 0.01

# 6. Promote verified remediation to permanent baseline
airel heal promote proposal.json --actor alice

# 7. Rollback if degradation occurs
airel heal rollback proposal.json --reason "Spike in latency"

# 8. View proposal status and audit trail
airel heal status proposal.json
```

```

---

## 28. Multi-Objective AI Reliability Optimization (v0.7.0 / Phase 38)

Version 0.7.0 introduces a production-grade, multi-objective **AI Reliability Optimization Engine** (`aireliability.optimization`) that automatically searches for optimal AI-system configurations across competing objectives (reliability, quality, groundedness, safety, security, latency, cost, and token usage) without compromising safety, governance, or self-healing controls.

### End-to-End Optimization Architecture

```text
              BASELINE CONFIGURATION
                        │
                        ▼
            OPTIMIZATION PROBLEM DEFINITION
            (Objectives, Hard Constraints, Registered Variables)
                        │
                        ▼
            CANDIDATE GENERATION & BOUNDED SEARCH
            (Grid, Random, Local, Hill Climbing, Bayesian, Evolutionary)
                        │
                        ▼
            EVALUATION & RESULT CACHING
            (Repeated Runs, Baseline Delta, Multi-Tier Caching)
                        │
                        ▼
            HARD CONSTRAINT VETO EVALUATION
            (Safety, Security, Regressions, Latency Caps)
                        │
                        ▼
            PARETO FRONTIER ANALYSIS
            (Non-Dominated Sorting & Crowding Distance)
                        │
                        ▼
            RELIABILITY RELEASE GATES
            (Zero Critical Regressions, Min Quality, Safety Thresholds)
                        │
                        ▼
            POLICY-DRIVEN CANDIDATE SELECTION
            (Balanced, Highest Quality, Lowest Cost, Lowest Latency)
                        │
                        ▼
            PHASE 36 TEST GENERATION BRIDGE
            (Synthesize Validation Tests for Modified Parameters)
                        │
                        ▼
            PHASE 37 SELF-HEALING & ROLLOUT BRIDGE
            (Remediation Proposal, Approval, Shadow/Canary Deployment)
                        │
                        ▼
            LIVE TELEMETRY VERIFICATION
            (RemediationVerifier: Error Rate & Latency Checks)
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
          PROMOTE               ROLLBACK
      (100% Production)    (Restore Baseline)
             │                     │
             └──────────┬──────────┘
                        │
                        ▼
            PHASE 35 KNOWLEDGE GRAPH SYNC
            (Record Run, Candidates, Pareto Results, Lineage)
                        │
                        ▼
            CONTINUOUS LEARNING & METRICS
            (Phase 34 Intelligence, Observability Telemetry)
```

### Core Subsystems & Innovations

1. **Multi-Objective Pareto Dominance**:
   - Rather than collapsing competing metrics into a naive single score, computes true non-dominated Pareto frontiers ($A \succ B$).
   - NSGA-II crowding distance preserves diversity along trade-off surfaces.
2. **Deterministic-First Search Strategies**:
   - 6 bounded strategies: `GridSearchStrategy`, `RandomSearchStrategy`, `LocalSearchStrategy`, `HillClimbingStrategy`, `BayesianOptimizationStrategy` (IDW surrogate + UCB acquisition), and `EvolutionarySearchStrategy` (tournament selection, crossover, mutation, elitism).
3. **Non-Negotiable Hard Vetoes**:
   - Hard safety ($\ge 0.95$), security ($\ge 0.95$), and regression constraints are checked before Pareto analysis.
   - Any candidate violating a hard constraint is marked `INVALID` and **never** enters the Pareto frontier.
   - If no configuration satisfies constraints, the engine halts with `NO_FEASIBLE_CONFIGURATION`.
4. **Deterministic Fingerprinting & Multi-Tier Caching**:
   - SHA-256 configuration fingerprints ignore volatile fields (timestamps, IDs).
   - Multi-tier caching keyed by `(candidate_fp, dataset_id, model_ver, eval_ver)` avoids redundant evaluation runs.
5. **Cross-Phase Integration Bridges**:
   - **Phase 36 Bridge**: Invokes `TestGenerationEngine` to synthesize targeted validation tests for parameter edge cases.
   - **Phase 37 Bridge**: Converts selected candidate into a `RemediationProposal`, routing deployment via `RolloutController` (`SHADOW`, `CANARY`), `RemediationVerifier`, and `PromotionManager`/`RollbackManager`.
   - **Phase 35 Bridge**: Synchronizes experiments, candidates, Pareto points, and lineages into `KnowledgeGraph`.
   - **Phase 22 Bridge**: Emits Prometheus metrics (`optimization_runs_total`, `optimization_pareto_size`, etc.).

### Python API Example

```python
from aireliability.optimization import (
    OptimizationEngine,
    OptimizationProblem,
    OptimizationObjective,
    OptimizationConstraint,
    OptimizationVariable,
    OptimizationBudget,
    OptimizationPolicy,
    ObjectiveDirection,
    VariableDomain,
    ComponentCategory,
    SelectionStrategy,
)

# 1. Define multi-objective optimization problem
problem = OptimizationProblem(
    problem_id="rag_opt_01",
    name="RAG Reliability and Cost Optimization",
    baseline_configuration={
        "top_k": 3,
        "similarity_threshold": 0.70,
        "temperature": 0.7,
    },
    objectives=[
        OptimizationObjective(
            objective_id="quality",
            metric="quality_score",
            direction=ObjectiveDirection.MAXIMIZE,
            weight=0.5,
        ),
        OptimizationObjective(
            objective_id="cost",
            metric="cost_usd",
            direction=ObjectiveDirection.MINIMIZE,
            weight=0.3,
        ),
        OptimizationObjective(
            objective_id="latency",
            metric="latency_seconds",
            direction=ObjectiveDirection.MINIMIZE,
            weight=0.2,
        ),
    ],
    constraints=[
        OptimizationConstraint(
            metric="safety_score",
            operator=">=",
            threshold=0.95,
            is_hard=True,
        ),
    ],
    variables=[
        OptimizationVariable(
            name="top_k",
            domain=VariableDomain.INT,
            min_value=1,
            max_value=10,
            step=1,
            category=ComponentCategory.RETRIEVAL,
        ),
        OptimizationVariable(
            name="temperature",
            domain=VariableDomain.FLOAT,
            min_value=0.1,
            max_value=1.0,
            step=0.1,
            category=ComponentCategory.GENERATION,
        ),
    ],
    budget=OptimizationBudget(max_candidates=15, max_evaluations=15),
    policy=OptimizationPolicy(selection_strategy=SelectionStrategy.BALANCED_SCORE),
)

# 2. Run optimization engine
engine = OptimizationEngine()
result = engine.run(problem, strategy_name="grid")

# 3. Inspect Pareto frontier and selected configuration
print(f"Status: {result.status}")
print(f"Pareto Frontier Size: {len(result.pareto_frontier.points)}")
if result.selected_candidate:
    print(f"Selected Candidate: {result.selected_candidate.candidate_id}")
    print(f"Optimized Parameters: {result.selected_candidate.configuration.parameters}")
```

### CLI Optimization Commands

```bash
# Plan optimization problem
airel optimize plan --objective "quality:maximize" --objective "latency:minimize" --variable "temperature:float:0.0:1.0:0.1" -o problem.json

# Run optimization using grid, random, local, climbing, bayesian, or evolutionary
airel optimize run problem.json --strategy grid --max-candidates 20 --output result.json

# Inspect Pareto frontier and dominated/non-dominated points
airel optimize pareto result.json

# Compare baseline vs candidate configurations and deltas
airel optimize compare result.json

# Policy-driven candidate selection
airel optimize select result.json --strategy balanced_score

# Validate selected candidate against reliability gates
airel optimize validate result.json

# Deploy selected candidate via Phase 37 canary
airel optimize deploy result.json --strategy canary --percentage 10

# Rollback deployed candidate if regressions occur
airel optimize rollback result.json --reason "Latency threshold exceeded"

# Check budget usage and run status
airel optimize budget result.json
airel optimize status result.json
```

---

## 29. Advanced RAG Reliability Engine (v0.8.0 / Phase 39)

Phase 39 introduces a production-grade **Advanced RAG Reliability Engine** (`aireliability.rag`) providing end-to-end evaluation, diagnosis, testing, monitoring, and self-healing across the complete 11-stage RAG lifecycle:

```
USER QUERY → QUERY ANALYSIS → RETRIEVAL → RANKING/RERANKING → CONTEXT ANALYSIS → LLM GENERATION → CLAIM EXTRACTION → EVIDENCE ALIGNMENT → CITATION VALIDATION → GROUNDEDNESS/FAITHFULNESS → RAG RELIABILITY VERIFICATION
```

### Key Principles & Capabilities

1. **Stage-Level Attribution & Isolation**:
   - Decomposes RAG reliability into independent stages so a high final-answer score never masks a catastrophic retrieval failure (or vice versa).
2. **Deterministic-First Evaluation**:
   - Operates with zero required external LLM or vector database dependencies. Deterministic regex-based claims, factual contradiction heuristic graphs, and statistical metrics run reliably in offline CI/CD pipelines.
3. **No Fabricated Ground Truth**:
   - If expected documents/chunks or gold answers are absent, exact recall/precision metrics report `ground_truth_available = False` and heuristic evidence scores are surfaced without fabricating ground truth.
4. **Untrusted Evidence & Non-Compensatory Security Vetoes**:
   - Treats all retrieved documents as untrusted inputs. Prompt injection overrides, credential leaks, and poisoning patterns trigger an immediate critical veto, capping composite reliability score ($\le 0.30$) regardless of retrieval recall.
5. **Inline Citation & Fact Verification**:
   - Resolves inline citations (`[1]`, `[doc_1]`), verifies chunk existence, checks claim-evidence alignment across 4 states (`SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`), and calculates hallucination rates.
6. **Knowledge Base Health & Freshness Tracking**:
   - Evaluates document staleness against configurable `max_age_days` policies, detects index staleness, chunk duplication, fragmentation, and orphaned chunks.
7. **Statistical Drift & Multi-Hop Reasoning**:
   - Detects query length, retrieval score, grounding, and embedding model version drift; validates intermediate entity hops and broken multi-hop chains.
8. **Seamless Integration with Phases 34–38**:
   - Feeds RAG failures into Phase 34 `FailureClusterer` and `RecommendationEngine`.
   - Links runs, claims, and chunks into Phase 35 `KnowledgeGraph` with full provenance.
   - Generates RAG regression tests via Phase 36 `TestGenerationEngine`.
   - Proposes remediation actions via Phase 37 `RemediationEngine`.
   - Tunes RAG hyperparameters (e.g. `top_k`, `similarity_threshold`) via Phase 38 `OptimizationEngine`.

### Python API Example

```python
from aireliability.rag import (
    AdvancedRAGReliabilityEngine,
    RetrievedDocument,
    RetrievedChunk,
)

# 1. Initialize RAG Engine
engine = AdvancedRAGReliabilityEngine()

# 2. Evaluate a RAG execution
run = engine.evaluate_run(
    query="What is AI reliability and how does it prevent hallucinations?",
    retrieved_documents=[
        RetrievedDocument(
            document_id="doc_1",
            title="Reliability Guide",
            text="AI reliability guarantees grounded systems and prevents hallucinations.",
            source="knowledge_base",
        )
    ],
    retrieved_chunks=[
        RetrievedChunk(
            chunk_id="chk_1",
            document_id="doc_1",
            text="AI reliability guarantees grounded systems and prevents hallucinations.",
            retrieval_score=0.95,
        )
    ],
    generated_answer="AI reliability guarantees grounded systems and prevents hallucinations [1].",
)

# 3. Inspect Stage-Level Reliability Scores
print(f"Overall RAG Score: {run.reliability_score.overall_score:.2f}")
print(f"Security Passed:   {run.reliability_score.security_passed}")
for stage, score in run.stage_scores.items():
    print(
        f"  {stage.capitalize():<12}: {score.score:.2f} (Confidence: {score.confidence:.2f})"
    )

# 4. Check Extracted Claims & Grounding
for claim in run.claims:
    print(f"Claim: {claim.text} -> {claim.support_status.value}")
```

### CLI Commands

```bash
# Evaluate complete RAG run
airel rag evaluate run.json

# Analyze query complexity, type, and expected retrieval difficulty
airel rag analyze "What is AI reliability?"

# Evaluate retrieval precision, recall, MRR, and NDCG
airel rag retrieve run.json

# Evaluate groundedness and faithfulness
airel rag grounding run.json

# Validate inline citations and chunk references
airel rag citations run.json

# Extract atomic claims from answer text
airel rag claims "AI reliability guarantees safe systems. It prevents hallucinations."

# Audit knowledge base freshness
airel rag freshness run.json --freshness-window 60

# Detect query, retrieval, and grounding drift
airel rag drift current_run.json --baseline baseline_run.json

# Audit knowledge base health and chunk fragmentation
airel rag knowledge kb_docs.json

# Detect contradictory retrieved evidence
airel rag conflicts run.json

# Diagnose root cause RAG failures
airel rag failures run.json

# Trace provenance chains from answers to claims and chunks
airel rag provenance run.json --claim-id clm_1

# Execute golden RAG regression test suite against release gates
airel rag regression rag_suite.json

# Sample production RAG telemetry with sanitization
airel rag monitor

# Generate multi-format report
airel rag report run.json --format markdown -o rag_report.md

# Inspect detailed run diagnostics
airel rag inspect run.json
```

---

## 30. Advanced Agent Reliability Engine (v0.9.0 / Phase 40)

Phase 40 introduces the production-grade **Advanced Agent Reliability Engine** (`aireliability.agent`) providing complete evaluation, diagnosis, testing, monitoring, self-healing, and Pareto optimization for autonomous AI agents and multi-agent systems across the 15-stage lifecycle:

$$\text{Task} \to \text{Decomposition} \to \text{Plan} \to \text{Action} \to \text{Tool Call} \to \text{Tool Result} \to \text{Observation} \to \text{State} \to \text{Memory} \to \text{Reasoning} \to \text{Replan} \to \text{Handoff} \to \text{Goal Check} \to \text{Final Response} \to \text{Verification}$$

### Core Architectural Principles
1. **Trajectory-First Evaluation**: Evaluates agents as execution trajectories rather than black-box question-answer systems. A correct final output never excuses, hides, or compensates for upstream trajectory failures (e.g. wrong tool selection, schema violations, redundant loops, or unsafe operations).
2. **Never Fabricate Expected Behavior**: Ground-truth expectations are only enforced when specified by benchmarks or deterministic schemas. If ground truth is absent, the engine reports `UNKNOWN` rather than hallucinating expected tools.
3. **No Infrastructure Blame**: Distinguishes agent parameter faults from external infrastructure outages (e.g., timeouts, rate limits, 500 errors).
4. **Observable Reasoning Only**: Compares declared plans and actions against observations. It never attempts to reconstruct or police private chain-of-thought tokens.
5. **Untrusted Tool Outputs & Observations**: Detects prompt injections, instruction overrides, and credential leaks embedded in external tool results.
6. **Hard Safety/Security Vetoes**: Hard vetoes capping overall scores at $\le 0.30$ upon unauthorized tool calls or credential exposure.
7. **Full Ecosystem Bridges**: Integrated with Phase 34 (Intelligence), Phase 35 (Knowledge Graph), Phase 36 (Test Generation), Phase 37 (Self-Healing), Phase 38 (Optimization), and Phase 39 (RAG).

### Python API

```python
from aireliability.agent import (
    AdvancedAgentReliabilityEngine,
    AgentTask,
    AgentPlan,
    AgentTrajectory,
    AgentStep,
    ToolCall,
    ToolResult,
    Observation,
    Goal,
    GoalCriterion,
)

engine = AdvancedAgentReliabilityEngine()

# Evaluate an agent run
run = engine.evaluate_run(
    task=AgentTask(request_text="Refund order #ORD-1234 and send confirmation email"),
    plan=AgentPlan(steps=["lookup_order", "process_refund", "send_email"]),
    trajectory=AgentTrajectory(
        steps=[
            AgentStep(
                sequence=1,
                action="lookup_order",
                tool_call=ToolCall(
                    tool_name="order_api", arguments={"order_id": "ORD-1234"}
                ),
            ),
            AgentStep(
                sequence=2,
                action="process_refund",
                tool_call=ToolCall(
                    tool_name="stripe_api",
                    arguments={"amount": 49.99, "order_id": "ORD-1234"},
                ),
            ),
            AgentStep(
                sequence=3,
                action="send_email",
                tool_call=ToolCall(
                    tool_name="mailer",
                    arguments={"recipient": "user@example.com", "template": "refund"},
                ),
            ),
        ]
    ),
    goals=[
        Goal(
            description="Issue refund and notify customer",
            criteria=[
                GoalCriterion(description="Refund transaction succeeded"),
                GoalCriterion(description="Confirmation email sent"),
            ],
        ),
    ],
    final_response="Order #ORD-1234 has been refunded and confirmation was sent to user@example.com.",
)

print(f"Overall Score: {run.reliability_score.overall_score:.2f}")
print(f"Goal Status: {run.goal_verification.overall_status}")
print(f"Safety Passed: {run.reliability_score.safety_passed}")
```

### CLI Commands (`airel agent`)

```bash
# Evaluate full agent trajectory reliability
airel agent evaluate run.json

# Analyze task complexity and constraints
airel agent analyze "Analyze quarterly earnings, train forecasting model, and deploy dashboard"

# Inspect execution trajectory timeline
airel agent trajectory run.json

# Evaluate plan validity, completeness, and deviation
airel agent plan run.json

# Validate tool selection, schema arguments, and risk tiers
airel agent tools run.json

# Detect cyclic trajectory patterns and runaway loops
airel agent loops run.json

# Analyze retry efficacy and retry storms
airel agent retries run.json

# Audit memory read/write/retrieve operations
airel agent memory run.json

# Validate state transition consistency
airel agent state run.json

# Verify goal criteria satisfaction independently
airel agent goals run.json

# Analyze multi-agent communication and task transfers
airel agent handoffs run.json

# Explain root-cause failure attributions
airel agent failures run.json

# Detect behavioral, tool, and trajectory drift
airel agent drift current_run.json --baseline baseline_run.json

# Audit tool output injection and credential exposure
airel agent security run.json

# Execute golden trajectory test suites
airel agent regression agent_suite.json

# Run root-cause diagnostic engine
airel agent diagnose run.json

# Generate automated regression tests from failures
airel agent tests run.json

# Propose self-healing remediation patches
airel agent heal run.json

# Formulate Pareto optimization problems
airel agent optimize run.json

# Generate multi-format evaluation summaries
airel agent report run.json --format markdown -o agent_report.md

# Inspect serialized run diagnostics
airel agent inspect run.json
```

---

## 31. Enterprise Reliability Platform (v1.4.0 / Phases 41–46)

Release **v1.4.0** completes the enterprise reliability roadmap with six deeply integrated platform capabilities:

### 31.1 AI Safety Validation (Phase 41 — `aireliability.safety`)
Defensive, deterministic-first automated safety evaluation and campaign engine designed for sandboxed validation:
- **Boundary Categories**: Prompt injection, instruction boundary override, tool-use sandbox limits, memory manipulation, multi-agent coordination, privacy & data leakage, and retrieved document trust.
- **Deterministic Mutation Engine**: Zero-width character insertion, unicode homoglyph substitution, token splitting, Base64/Rot13/URL encoding, and adversarial framing prefixes.
- **Hard Safety Veto**: Non-compensatory cap enforcing composite reliability $\le 0.30$ upon critical safety violations.

```python
from aireliability.safety import (
    SafetyEngine,
    SafetyCampaign,
    SafetyTarget,
    SafetyCategory,
)

engine = SafetyEngine()
campaign = SafetyCampaign(
    target=SafetyTarget(target_id="customer_bot"),
    categories=[SafetyCategory.INSTRUCTION_BOUNDARY, SafetyCategory.TOOL_USE_BOUNDARY],
    max_tests=10,
)
result = engine.run_campaign(campaign)
print(f"Safety Score: {result.score.overall_score:.2f}")
print(f"Hard Veto Triggered: {result.score.hard_veto_triggered}")
```

### 31.2 Reliability Prediction (Phase 42 — `aireliability.prediction`)
Statistical and machine learning forecasting of reliability trends, failure probabilities, and remaining safe operations:
- **Forecasting Models**: Exponential smoothing, linear trend regression, rolling variance volatility, and Weibull hazard estimation.
- **Multi-Horizon**: `NEXT_EXECUTION`, `SHORT_TERM`, `MEDIUM_TERM`, `LONG_TERM`.
- **Confidence Engine**: Combines sample size sufficiency, signal volatility, and historical forecast accuracy.

```python
from aireliability.prediction import (
    ReliabilityPredictionEngine,
    PredictionInput,
    PredictionHorizon,
)

engine = ReliabilityPredictionEngine()
pred = engine.predict(
    PredictionInput(
        target_id="order_service",
        historical_signals={"reliability": [0.99, 0.98, 0.96, 0.93, 0.90]},
        current_metrics={"reliability": 0.90},
    ),
    horizon=PredictionHorizon.SHORT_TERM,
)
print(f"Forecast: {pred.reliability_forecast.forecasted_value:.2f}")
print(f"Trend: {pred.risk_forecast.trend.value}")
```

### 31.3 Reliability Intelligence Dashboard (Phase 43 — `aireliability.dashboard`)
System-wide observability aggregating all reliability subsystems (Phases 1–46) into unified intelligence views:
- **21 Specialized Panels**: Covering Reliability, Safety, Security, Agent Trajectories, RAG Quality, Regression, Prediction, Pareto Optimization, Self-Healing, and Knowledge Graphs.
- **Weighted Health Scoring**: Calculates overall health summaries with hard veto caps and automated incident detection.
- **Multi-Format Export**: Deterministic JSON, Markdown, and CSV exports with cryptographic fingerprinting.

```python
from aireliability.dashboard import DashboardService

service = DashboardService()
dashboard = service.get_dashboard(metrics={"reliability": 0.95, "safety": 1.0})
print(f"System Health: {dashboard.health_summary.overall_health:.2f}")
print(f"Status: {dashboard.health_summary.status.value}")
```

### 31.4 Reliability Policy Engine (Phase 44 — `aireliability.policy`)
Declarative policy governance engine enforcing organizational reliability standards before deployment:
- **Strict Priority Ordering**: `SECURITY > SAFETY > TENANT_ISOLATION > AUTHORIZATION > COMPLIANCE > RELIABILITY > PERFORMANCE > COST`.
- **Hard Constraints**: Non-negotiable gates triggering immediate `BLOCK` on security, safety, or tenant isolation violations.
- **Audit & Rollback**: Versioned policy bundles with explanation trees and cryptographic verification.

```python
from aireliability.policy import PolicyEngine, PolicyDecision

engine = PolicyEngine()
decision = engine.evaluate(
    {
        "reliability_score": 0.95,
        "safety_score": 1.0,
        "credential_leakage": False,
        "cross_tenant_access": False,
    }
)
assert decision.decision == PolicyDecision.ALLOW
```

### 31.5 Enterprise Multi-Tenancy (Phase 45 — `aireliability.tenancy`)
Enterprise isolation and governance infrastructure:
- **Context Isolation**: Thread-safe `contextvars` tracking tenant, actor, and roles across asynchronous tasks.
- **Resource Isolation & Auditing**: Strict tenant boundary validation preventing data leakage with real-time audit event logging.
- **RBAC & Quotas**: Role-based access control with token, concurrency, and rate-limiting quota enforcement.

```python
from aireliability.tenancy import (
    TenantContextManager,
    TenantIsolationManager,
    TenantResource,
    TenantContext,
)

iso_mgr = TenantIsolationManager()
ctx = TenantContext(tenant_id="tenant_alpha", actor_id="user_1")
res = TenantResource(
    resource_id="eval_1", tenant_id="tenant_alpha", resource_type="evaluation"
)

with TenantContextManager(ctx):
    assert iso_mgr.verify_access(res) is True
```

### 31.6 Reliability Platform API & SDK (Phase 46 — `aireliability.api`, `aireliability.sdk`)
REST platform and typed client library:
- **FastAPI Backend**: 24 REST endpoints covering evaluations, safety validation, predictions, dashboards, policies, tenants, quotas, async jobs, and HMAC-SHA256 signed webhooks.
- **Typed Python SDK**: Synchronous `Client` and asynchronous `AsyncClient` with custom error hierarchy.

```python
from aireliability.sdk import Client

with Client(base_url="http://localhost:8000", api_key="airel_...") as client:
    health = client.get_health()
    eval_res = client.evaluations.create(input_text="hello", output_text="world")
    print(f"Eval ID: {eval_res['evaluation_id']}, Passed: {eval_res['passed']}")
```

---

## Real-World Demo

A complete, self-contained demonstration application showcasing real-world integration of `aireliability` v1.4.0 into production AI pipelines is available in [`examples/aireliability_demo/`](examples/aireliability_demo/).

### Architecture & Closed-Loop Workflow

```text
       AI Application (LLM / RAG / Agent)
                     │
                     ▼
           Unified Observability (Phase 22)
                     │
                     ▼
       Reliability Evaluation (Phases 31, 39, 40)
                     │
                     ▼
         Failure Detection & Normalization (Phase 34)
                     │
                     ▼
        Evidence-Based Root Cause Analysis (Phases 17, 34)
                     │
                     ▼
          Graph Provenance & Lineage (Phase 35)
                     │
                     ▼
      Safety Validation & Hard Veto (Phases 32, 41)
                     │
                     ▼
     Time-Series Reliability Prediction (Phase 42)
                     │
                     ▼
      Enterprise Policy Enforcement (Phase 44)
                     │
                     ▼
    Self-Healing Remediation & Verification (Phase 37)
                     │
                     ▼
       Automated Regression Test Generation (Phases 18, 36)
                     │
                     ▼
       Unified Multi-Tenant Dashboard & API/SDK (Phases 43, 45, 46)
```

### Key Highlights
- **100% Local & Deterministic**: Zero cloud credentials, external databases, or GPUs required. Runs entirely in-process or via SQLite.
- **Provider Agnostic**: Default `DeterministicLLM` supports reproducible scenarios (`NORMAL`, `LOW_QUALITY`, `HALLUCINATION`, `LATENCY`, `EMPTY_RESPONSE`); optional `OptionalLocalLLM` adapter connects to local Ollama instances when available.
- **Deep Phase Integration**: Integrates all capabilities from core evaluation to knowledge graph lineage, automated repair, safety veto, multi-tenant isolation, and OpenAPI/SDK client interactions.

### Quick Start

```bash
# 1. Run all demo test suites
pytest examples/aireliability_demo/tests

# 2. Run the full 17-step end-to-end reliability workflow
python3 examples/aireliability_demo/scripts/run_full_workflow.py

# 3. Run individual controlled scenarios
python3 examples/aireliability_demo/scripts/run_demo.py --scenario normal
python3 examples/aireliability_demo/scripts/run_demo.py --scenario llm_failure
python3 examples/aireliability_demo/scripts/run_demo.py --scenario rag_failure
python3 examples/aireliability_demo/scripts/run_demo.py --scenario agent_failure
python3 examples/aireliability_demo/scripts/run_demo.py --scenario safety_failure
python3 examples/aireliability_demo/scripts/run_demo.py --scenario regression
```

### Example Terminal Output

```text
============================================================
AIRELIABILITY REAL-WORLD DEMONSTRATION WORKFLOW
============================================================
[Step 1] Initializing isolated tenant environments...
  ✓ Multi-tenancy configured: tenant_alpha, tenant_beta
[Step 2] Ingesting knowledge base corpus...
  ✓ Loaded 7 documents and 14 chunks into DeterministicRetriever
[Step 3] Running deterministic LLM evaluations...
  ✓ LLM Evaluation: Passed (Quality: 0.98, Hallucination: 0.00)
[Step 4] Running RAG evaluation (Phase 39)...
  ✓ RAG Evaluation: Passed (Score: 0.96)
[Step 5] Running Agent auditing & trajectory verification (Phase 40)...
  ✓ Agent Evaluation: Passed (Score: 1.00)
[Step 6] Running safety validation probe suite (Phase 41)...
  ✓ Critical safety boundary test: VETO TRIGGERED (Blocked: True)
[Step 7-9] Failure injection, clustering, and root cause analysis...
  ✓ Failure clustered into 'grounding_violation' with confidence 0.95
[Step 10-12] Automated test generation & self-healing verification...
  ✓ Synthesized regression test 'reg_test_demo_001'
  ✓ Remediation simulated & verified (Recovery Rate: 100%)
[Step 13] Running reliability forecasting & trend prediction (Phase 42)...
  ✓ Projected Reliability: 0.94 (Risk: Low)
[Step 14] Enforcing enterprise governance policies (Phase 44)...
  ✓ Policy decision: ALLOW (Violations: 0, Warnings: 0)
[Step 15] Compiling 21-panel health dashboard (Phase 43)...
  ✓ Overall Status: HEALTHY | Reliability: 0.96
[Step 16-17] Verifying REST Platform API & typed Python SDK (Phase 46)...
  ✓ API Health check: 200 OK
  ✓ SDK Client execution: Success
============================================================
DEMO COMPLETE
============================================================
```

Explore the complete demo implementation, sample data, and scenarios in [examples/aireliability_demo/](examples/aireliability_demo/).

---

## 32. Current Limitations

To maintain technical honesty and integrity:

1. **Provider Independence**:
   - The core package requires zero external graph database dependencies (no mandatory Neo4j, PostgreSQL, Redis, Elasticsearch, or vector DB). The default in-memory graph backend operates entirely in-process with index acceleration.
2. **Deterministic Mock Fallback in CI**:
   - All evaluators and judges seamlessly fall back to deterministic mocks in offline CI environments, ensuring zero unexpected network egress or test flakiness.
3. **Statistical Sample Awareness**:
   - Small dataset samples may lack statistical significance for subtle metric shifts; bootstrap confidence intervals and p-value checks should be utilized on larger validation sets.
4. **Graph Scalability**:
   - The default in-memory store is optimized for single-machine execution supporting thousands of nodes and tens of thousands of edges per evaluation run. Large enterprise-scale distributed graphs can plug into `GraphStoreRegistry`.

---

## 33. License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.





