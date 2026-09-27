# Framework Integration Layer

`aireliability` provides optional, decoupled adapters for observing and reliability-testing AI agents built with popular frameworks like **LangGraph** and **LangChain**.

The core engine remains completely framework-agnostic, lightweight, and dependency-free:

```text
                    aireliability
                         │
              ┌──────────┴──────────┐
              │                     │
          Core Engine          Integrations
              │                     │
       no framework deps       optional extras
              │                     │
              ├──────────────┬──────┤
              │              │      │
          Callable       LangGraph  LangChain
```

---

## 1. Core vs. Optional Dependencies

Core installation requires **no framework dependencies**:
```bash
pip install aireliability
```

To enable framework adapters:
```bash
# LangGraph support
pip install "aireliability[langgraph]"

# LangChain support
pip install "aireliability[langchain]"
```

If code attempts to import an adapter without the corresponding package installed, a clear, actionable `ImportError` is raised with installation instructions.

---

## 2. Event and Tool Call Normalization

Different frameworks represent tool calls and state transitions using disparate schemas. `aireliability` normalizes them into standard, framework-independent objects:

| Framework Event | Extracted Data | Normalized Representation |
| :--- | :--- | :--- |
| **LangGraph** `AIMessage.tool_calls` | `name`, `args` | `ToolCallRecord(name=..., arguments=...)` |
| **LangGraph** `ToolMessage` | `name`, `content` | `ToolCallRecord.result` / `TraceStep.output` |
| **LangChain** `on_tool_start` | `serialized.name`, `inputs` | `ToolCallRecord(name=..., arguments=...)` |
| **LangChain** `on_tool_end` | `output` | `ToolCallRecord(result=...)` |
| **LangChain** `on_tool_error` | `error` | `ToolCallRecord(status="failed", result=...)` |

### Field Invariants
The evaluator always receives normalized `TraceStep` records with:
* `name`: Tool identifier string.
* `input`: Normalized dictionary of arguments (or `{}` if omitted).
* `output`: Tool return value or error dictionary.
* `status`: `"completed"` or `"failed"`.
* `duration_ms`: Execution time in milliseconds when measurable.

Evaluators and regression generators never interact with framework-specific message objects.

---

## 3. LangGraph Integration (`LangGraphAdapter`)

`LangGraphAdapter` observes compiled `StateGraph` applications via `.stream()` or `.invoke()`.

```python
from aireliability import ReliabilityRunner, TestCase, ToolOrder
from aireliability.integrations.langgraph import LangGraphAdapter

# Compiled LangGraph application
graph = workflow.compile()

# Connect adapter
adapter = LangGraphAdapter(graph=graph)

test_case = TestCase(
    name="order_flow",
    input={"order_id": "123"},
    expectations=["ToolOrder:get_order,cancel_order,refund_order"],
)

runner = ReliabilityRunner(
    adapter=adapter,
    evaluators=[ToolOrder(["get_order", "cancel_order", "refund_order"])],
)

result = runner.run(test_case)
```

### Features:
* **Node Transition Tracking**: Node execution steps are captured as `StepType.AGENT` steps.
* **Tool Message Pairing**: Correlates `tool_calls` on `AIMessage` with downstream `ToolMessage` results.
* **Async Execution**: Supports `await adapter.aexecute(test_case)`.

---

## 4. LangChain Integration (`LangChainAdapter`)

`LangChainAdapter` attaches a `ReliabilityCallbackHandler` to LangChain runnables, chains, or agent executors.

```python
from aireliability import ReliabilityRunner, TestCase, ToolArguments
from aireliability.integrations.langchain import LangChainAdapter

# LangChain Runnable or AgentExecutor
chain = prompt | model | tools

# Connect adapter
adapter = LangChainAdapter(chain=chain)

test_case = TestCase(
    name="lookup_test",
    input={"user_id": "usr_99"},
)

runner = ReliabilityRunner(
    adapter=adapter,
    evaluators=[ToolArguments("get_user", {"user_id": "usr_99"})],
)

result = runner.run(test_case)
```

### Features:
* **Official Callback API**: Uses `BaseCallbackHandler` (`on_tool_start`, `on_tool_end`, `on_tool_error`) without monkey-patching.
* **Error Normalization**: Maps chain and tool errors into framework-independent error payloads.
* **Async Execution**: Supports `await adapter.aexecute(test_case)`.

---

## 5. Security & Sensitive Data Handling

When testing agents with real customer or corporate data:
1. **Tool Arguments & Results**: Adapters observe and record tool arguments and output strings in `ExecutionTrace.steps`.
2. **Secrets & Tokens**: Never pass API tokens, passwords, or bearer keys into logged tool arguments. Use environment variables or secret vaults.
3. **Data Sanitization**: Before persisting traces in SQLite or sharing failure reports, sanitize sensitive PII using custom hooks or test fixture cleanups.
4. **No Telemetry**: `aireliability` does not collect telemetry, track usage, or transmit traces over the network.

---

## 6. How to Build a Custom Adapter

You can easily adapt any proprietary or custom framework by subclassing `BaseAdapter`:

```python
from aireliability.execution.adapters import BaseAdapter, ToolCallRecord
from aireliability.core.models import ExecutionTrace, TestCase, ExecutionStatus
from datetime import datetime, UTC


class MyFrameworkAdapter(BaseAdapter):
    def __init__(self, agent):
        self.agent = agent

    def execute(self, agent=None, test_case=None):
        effective_agent = agent or self.agent
        start = datetime.now(UTC)

        # 1. Execute proprietary agent
        response = effective_agent.run(test_case.input)

        # 2. Extract and normalize tool events
        steps = []
        for call in effective_agent.get_tool_history():
            record = ToolCallRecord(
                name=call["tool"],
                arguments=call.get("args", {}),
                result=call.get("output"),
            )
            steps.append(record.to_trace_step())

        # 3. Return standard ExecutionTrace
        return ExecutionTrace(
            test_id=test_case.id,
            input=test_case.input,
            output=response,
            status=ExecutionStatus.COMPLETED,
            steps=steps,
            started_at=start,
            completed_at=datetime.now(UTC),
        )
```

---

## 7. Version Compatibility

Tested and supported version ranges:

| Framework | Supported Version | Python Support |
| :--- | :--- | :--- |
| **Core `aireliability`** | `0.1.0` | Python 3.11, 3.12, 3.13 |
| **`langgraph`** | `>= 0.0.1` | Python 3.11, 3.12, 3.13 |
| **`langchain-core`** | `>= 0.1.0` | Python 3.11, 3.12, 3.13 |
| **`langchain`** | `>= 0.1.0` | Python 3.11, 3.12, 3.13 |

---

## 8. Performance Benchmark

Overhead measured across adapters using an identical 3-tool sequence over 1,000 runs:

| Adapter | Mean Latency | Median Latency | Min Latency | Max Latency |
| :--- | :--- | :--- | :--- | :--- |
| **`CallableAdapter`** | 17.80 µs | 16.71 µs | 16.08 µs | 470.50 µs |
| **`LangChainAdapter`** | 23.45 µs | 22.67 µs | 21.79 µs | 151.29 µs |
| **`LangGraphAdapter`** | 29.93 µs | 28.92 µs | 27.79 µs | 122.67 µs |

Adapter execution overhead is approximately **20–30 microseconds**, which is completely negligible compared to real LLM call latencies (100–1,500 ms).
