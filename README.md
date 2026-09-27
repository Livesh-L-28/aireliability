# AI Reliability Engine (`aireliability`)

> An open-source reliability and regression-testing framework for LLM applications and AI agents.

[![CI](https://github.com/aireliability/aireliability/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![Reliability](https://github.com/aireliability/aireliability/actions/workflows/reliability.yml/badge.svg)](.github/workflows/reliability.yml)
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
- [x] **Phase 30**: Production Hardening & Final Release (Audited End-to-End Workflows A–H, Security & Multi-Tenancy Boundaries, Parity Storage, Packaging & Production Readiness)


---

## 23. Current Limitations

To maintain technical honesty and integrity, developers should be aware of the framework's current operational scope and trade-offs:

1. **Deterministic Evaluation Focus (v0.1)**:
   - Version 0.1 primarily demonstrates **deterministic evaluation** (tool execution sequences, argument assertions, JSON schema conformance, output containment, and latency/cost budgets).
   - Semantic LLM evaluation (e.g. LLM-as-a-judge or semantic embeddings) is not yet the core benchmark. While the `Evaluator` protocol supports custom probabilistic evaluators, LLM-based evaluation introduces non-determinism, latency, and cost, and is not automatically treated as infallible ground truth.
2. **Synthetic Agent Scenarios for Reproducibility**:
   - The included benchmark suite uses deterministic synthetic agent scenarios to ensure exact reproducibility across machines without requiring paid API keys or exposing benchmarks to remote endpoint jitter.
3. **Framework Adapters Are Still Limited**:
   - While the `ExecutionAdapter` protocol provides a clean contract for integration, out-of-the-box first-party adapters for external frameworks (LangChain, LlamaIndex, CrewAI) are currently reference examples rather than bundled production drivers.
4. **Hardware and Workload Dependency**:
   - Microsecond overhead and storage throughput results depend on CPU single-core performance and local disk I/O characteristics.
5. **Local SQLite Concurrency**:
   - Persistence is implemented on top of serverless SQLite with transactional write locks. Multi-node distributed workers should await the upcoming PostgreSQL backend.


---

## 24. License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.


