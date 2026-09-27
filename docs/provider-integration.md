# Provider-Neutral AI Model Integration Layer

`aireliability` provides a provider-neutral model/tool execution integration layer. It allows developers to observe, trace, evaluate, diagnose, and benchmark model invocations and tool calls across diverse LLM inference endpoints (OpenAI, Azure OpenAI, vLLM, Ollama, LiteLLM, Groq, Together, Mistral, and local compatible servers) without vendor lock-in or heavy mandatory dependencies.

```text
       ┌────────────────────────────────────────────────────────┐
       │             OpenAI-Compatible Inference Endpoint       │
       │    (OpenAI / Azure / vLLM / Ollama / LiteLLM / Groq)   │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │   OpenAICompatibleAdapter     │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                       Normalized ExecutionTrace
                                   │
                 ┌─────────────────┼─────────────────┐
                 ▼                 ▼                 ▼
          Deterministic        Semantic          Root-Cause
           Evaluators          Evaluators        Diagnosis
                 │                 │                 │
                 └─────────────────┼─────────────────┘
                                   ▼
                             FailureReport
                                   │
                                   ▼
                       Regression Test Synthesis
                                   │
                                   ▼
                           RegressionRunner
```

---

## 1. Core Abstractions & Schema

### ProviderAdapter
`ProviderAdapter` inherits from `BaseAdapter` and serves as the provider-neutral base class for model adapters. It provides:
- **`sanitize_metadata(metadata: dict) -> dict`**: Automatically redacts sensitive fields (such as `api_key`, `authorization`, `token`, `secret`, `password`, `key`) from trace metadata and logs.
- **Provider Event Emission**: Standardized event dispatching for model life cycles.

### AgentEventType Extensions
The following event types provide fine-grained observability into model lifecycle and streaming:
- `MODEL_CALL_START`: Model request dispatched.
- `MODEL_CALL_END`: Model response completed and parsed.
- `MODEL_CALL_ERROR`: Model invocation failed or threw an exception.
- `STREAM_START`: First token/chunk received from streaming response.
- `STREAM_CHUNK`: Intermediate chunk/delta received.
- `STREAM_END`: Stream terminated and fully aggregated.

### ModelUsage
Immutable dataclass representing token consumption:
```python
@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
```

### ModelCallRecord
Immutable dataclass capturing individual model invocations:
```python
@dataclass(frozen=True)
class ModelCallRecord:
    call_id: str
    model: str
    prompt: Any
    completion: Any | None
    latency_ms: float
    usage: ModelUsage | None = None
    streamed: bool = False
    error: str | None = None
    retries: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
```

### ToolCallRecord Call ID
`ToolCallRecord` includes an optional `call_id: str | None = None` linking tool calls directly to provider-specific call IDs (e.g. `call_abc123`).

---

## 2. OpenAICompatibleAdapter

`OpenAICompatibleAdapter` normalizes synchronous and asynchronous chat completions, tool call invocations, streaming chunks, token usage, errors, and retries into standard `ExecutionTrace` structures.

### Supported Scenarios:
1. **Direct client or dict inputs**: Works with official `openai.OpenAI` clients, duck-typed clients, dict payloads, or callable wrappers.
2. **Tool Calling**: Extracts function arguments (JSON-parsed or raw string fallback) and tool execution results into `StepType.TOOL` steps with `ToolCallRecord`.
3. **Streaming Aggregation**: Reconstructs complete content and tool call deltas across stream chunks into a single unified output while preserving streaming events.
4. **Latency Measurement**: Accurate wall-clock latency measurement recorded via monotonic clocks (`time.perf_counter()`).
5. **Error Normalization**: Maps network/API/rate-limit exceptions to failed `TraceStep` records and `ExecutionStatus.FAILED` without masking root causes.
6. **Async Execution**: Full asynchronous execution support via `await adapter.aexecute(test_case=tc)`.

---

## 3. Installation & Dependency Decoupling

The core package remains completely dependency-free:
```bash
pip install aireliability
```

To install optional OpenAI client support:
```bash
pip install "aireliability[openai]"
```

If `openai` is not installed, attempting to construct an adapter without a custom client or handler raises a helpful `ImportError`:
```text
OpenAICompatibleAdapter requires the 'openai' extra when no custom client is provided.
Install with: pip install 'aireliability[openai]'
```

---

## 4. Usage Examples

### Synchronous Chat Completion & Evaluation
```python
from openai import OpenAI
from aireliability.core.models import TestCase
from aireliability.evaluators import OutputExactMatch
from aireliability.execution.runner import ReliabilityRunner
from aireliability.integrations.openai_compatible import OpenAICompatibleAdapter

client = OpenAI(api_key="your-api-key")
adapter = OpenAICompatibleAdapter(client=client, model="gpt-4o-mini")

test_case = TestCase(
    id="greeting_test",
    name="Greeting Verification",
    input="Respond with 'Hello World'",
)

runner = ReliabilityRunner(
    adapter=adapter,
    evaluators=[OutputExactMatch(expected="Hello World")],
)
result = runner.run(test_case)
assert result.passed
```

### Tool Calling with Automatic Tool Execution
```python
def execute_tool(name: str, args: dict):
    if name == "lookup_order":
        return {"order_id": args["order_id"], "status": "shipped"}
    raise ValueError(f"Unknown tool: {name}")


adapter = OpenAICompatibleAdapter(
    client=client,
    model="gpt-4o-mini",
    tool_executor=execute_tool,
)

runner = ReliabilityRunner(adapter=adapter)
result = runner.run(
    TestCase(id="tc_order", name="order_lookup", input="Check order #102")
)
```

### Streaming Completion
```python
adapter = OpenAICompatibleAdapter(client=client, stream=True)
trace = adapter.execute(
    test_case=TestCase(id="tc_stream", name="stream", input="Count 1 to 5")
)
assert trace.output is not None
```

---

## 5. Metadata Sanitization

Any sensitive credentials contained within `call_metadata` or client configurations are automatically scrubbed:
```python
adapter = OpenAICompatibleAdapter(
    client=client,
    metadata={"api_key": "sk-secret123", "region": "us-east-1"},
)
trace = adapter.execute(test_case=tc)
assert trace.metadata["api_key"] == "[REDACTED]"
assert trace.metadata["region"] == "us-east-1"
```

---

## 6. Performance Overhead

Execution tracing overhead is measured over 1,000 iterations:
- **Mean overhead**: ~19.1 µs
- **Median overhead**: ~18.1 µs
- **Min overhead**: ~17.6 µs
- **Max overhead**: ~100.3 µs

The instrumentation overhead is orders of magnitude smaller than model network latency (typically 50 ms – 1500 ms), introducing effectively zero observable overhead to agent execution.
