# Execution Adapters Specification

The **Execution Adapter** layer decouples `aireliability` from specific LLM providers and agent orchestrators. It allows the testing and reliability engine to observe real Python AI agents without requiring external SDKs as mandatory core dependencies.

---

## 1. Why Adapters Exist

AI agents are built using heterogeneous frameworks:
- Custom Python classes and functions
- LangChain / LangGraph runnables
- OpenAI Assistants / Responses API
- Anthropic Claude Tool Calling
- Google Gemini SDK
- Local models via Ollama or vLLM

If `aireliability` coupled directly to each provider SDK, users would face massive dependency conflicts, bloated installation sizes, and fragile API churn.

**Adapters solve this by introducing an isolation barrier:**

```text
Real Agent (Custom, LangChain, OpenAI, etc.)
       │
       ▼
ExecutionAdapter Protocol
       │
       ▼
aireliability ExecutionTrace (TraceStep list, timestamps, latency)
       │
       ▼
Evaluators & Deterministic Assertions
       │
       ▼
FailureReport & RegressionTest
```

The core engine only ever processes standard `TestCase` inputs and `ExecutionTrace` outputs.

---

## 2. Core Protocol: `ExecutionAdapter`

Any adapter satisfies the runtime-checkable protocol defined in `aireliability.core.protocols`:

```python
from typing import Any, Protocol, runtime_checkable
from aireliability.core.models import ExecutionTrace, TestCase


@runtime_checkable
class ExecutionAdapter(Protocol):
    def execute(self, agent: Any, test_case: TestCase) -> ExecutionTrace:
        """Execute an agent with inputs from a test case and produce an ExecutionTrace."""
        ...
```

---

## 3. The `CallableAdapter`

`aireliability.execution.adapters.CallableAdapter` is the default adapter for standard Python functions and agent objects.

### Capabilities:
- Executes ordinary callables: `def agent(prompt: str) -> str`.
- Executes objects with `.run(input)` or `.invoke(input)`.
- Handles exceptions cleanly (propagating with an attached trace, or capturing as a failed trace).
- Automatically records execution latency, start/end UTC timestamps, and status.
- Inspects agent execution for structured tool events and history.

### Basic Usage:

```python
from aireliability import CallableAdapter, TestCase


def my_agent(prompt: str) -> str:
    return f"Response to: {prompt}"


adapter = CallableAdapter(agent=my_agent)
test = TestCase(name="sample_test", input="Hello agent")

trace = adapter.execute(test_case=test)
print(trace.output)  # "Response to: Hello agent"
print(trace.latency_ms)  # Measured execution time in ms
```

---

## 4. Tool Call Representation

Tool executions are captured as `TraceStep` instances with `type = StepType.TOOL`.

To ensure framework independence, `aireliability.execution.adapters` provides `ToolCallRecord`:

```python
class ToolCallRecord(BaseModel):
    name: str  # Tool name (e.g., 'get_order')
    arguments: dict[str, Any]  # Arguments passed to tool
    result: Any  # Result or output of tool
    started_at: datetime  # Invocation timestamp
    completed_at: datetime | None  # Finish timestamp
    duration_ms: float | None  # Execution duration
    status: str = "completed"  # 'completed' or 'error'
    metadata: dict[str, Any]  # Arbitrary tags/context
```

### Conversion:
Calling `.to_trace_step()` on a `ToolCallRecord` maps it directly into an immutable `TraceStep` for evaluation:

```json
{
  "type": "tool",
  "name": "get_order",
  "input": {
    "order_id": "123"
  },
  "output": {
    "status": "active",
    "amount": 99.99
  },
  "duration_ms": 1.25,
  "metadata": {
    "status": "completed"
  }
}
```

---

## 5. How Tool Events Are Extracted

`CallableAdapter` automatically extracts tool calls and execution events through four flexible mechanisms:

1. **Agent Attributes**: If the agent instance exposes `.tool_calls`, `.tools_called`, or `.tool_history`, records are automatically mapped into trace steps.
2. **Event History**: If the agent exposes `.events`, `.execution_events`, or `.history`, structured `ExecutionEvent` items are mapped.
3. **Dictionary Return Envelopes**: If the agent returns `{"output": ..., "tool_calls": [...]}`, the adapter unboxes the payload and extracts steps.
4. **Custom Extraction Hook**: Callers can supply an `extract_steps_hook(agent, raw_result) -> list[TraceStep]` callback.

---

## 6. Implementing a Custom Adapter

Implementing a custom adapter for an external framework is straightforward.

### Minimal Custom Adapter Example:

```python
import time
from datetime import UTC, datetime
from typing import Any
from aireliability.core.models import (
    ExecutionStatus,
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.execution.adapters import BaseAdapter


class SimpleHTTPServiceAdapter(BaseAdapter):
    """Adapter for an external HTTP-based AI service."""

    def __init__(self, endpoint_url: str) -> None:
        self.endpoint_url = endpoint_url

    def execute(self, agent: Any, test_case: TestCase) -> ExecutionTrace:
        start_time = datetime.now(UTC)
        t0 = time.perf_counter()

        # Simulated or actual service call
        # response = requests.post(self.endpoint_url, json={"prompt": test_case.input})
        # data = response.json()
        data = {"answer": f"Processed {test_case.input}", "tool": "search"}

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        end_time = datetime.now(UTC)

        step = TraceStep(
            type=StepType.TOOL,
            name=data["tool"],
            input={"query": test_case.input},
            output={"found": True},
        )

        return ExecutionTrace(
            test_id=test_case.id,
            input=test_case.input,
            output=data["answer"],
            status=ExecutionStatus.COMPLETED,
            started_at=start_time,
            completed_at=end_time,
            latency_ms=elapsed_ms,
            steps=[step],
        )
```
