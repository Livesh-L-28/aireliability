# Semantic Evaluation Engine Specification

The **Semantic Evaluation Engine** introduces evaluation capabilities for generative, probabilistic, and natural language outputs produced by AI agents and LLMs.

Crucially, **semantic evaluation does not replace deterministic assertions**—the deterministic evaluation layer (`ToolOrder`, `ToolCalled`, `SchemaMatch`, `OutputEquals`) remains the foundational verification bedrock. Semantic evaluators provide an additional layer for evaluating relevance, semantic similarity, and nuanced instruction-following.

---

## 1. Deterministic vs. Semantic Evaluation

| Dimension | Deterministic Evaluation (`evaluation.deterministic`) | Semantic Evaluation (`evaluation.semantic`) |
| :--- | :--- | :--- |
| **Foundation** | Invariant rule checks, exact matches, JSON schema, sequence orders | Natural language understanding, criteria satisfaction, meaning equivalence |
| **Output Space** | Boolean binary passes or structural diffs | Normalized score ($0.0 \le s \le 1.0$), reasoning, criteria breakdowns |
| **Execution Cost**| Microseconds ($\sim 8\,\mu\text{s}$ CPU overhead, no network/token costs) | Milliseconds to seconds (local heuristic or external judge invocation) |
| **Confidence** | Always $1.0$ (direct mathematical/logical proof of failure) | Model-dependent ($\le 0.95$ typical; preserves judge confidence) |
| **Flakiness Risk**| $0\%$ deterministic | Non-zero variance across runs when using remote LLM judges |

---

## 2. Why Semantic Evaluation Is Probabilistic

LLM-as-a-judge evaluators evaluate outputs using statistical token distributions rather than formal logic. Consequently:
1. Two identical agent outputs evaluated against identical prompts may receive minor score fluctuations across temperature/sampling runs.
2. Evaluator outputs are **rationales and model-produced evidence**, not infallible ground truth.
3. Therefore, `aireliability` stores the **evaluator name, provider, model ID, timestamp, score, threshold, and confidence** alongside the trace for rigorous auditability.

---

## 3. Judge & Provider Abstraction

The core engine remains strictly provider-agnostic. No external LLM SDKs (OpenAI, Anthropic, Gemini) are mandatory dependencies.

All judges adhere to the `SemanticJudge` protocol:

```python
from typing import Any, Protocol, runtime_checkable
from aireliability.evaluation.semantic import JudgeResult


@runtime_checkable
class SemanticJudge(Protocol):
    name: str

    def judge(
        self,
        prompt: str,
        output: str,
        reference: str | None = None,
        criteria: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> JudgeResult: ...
```

The resulting `JudgeResult` normalizes model outputs across any provider:
- `passed: bool`
- `score: float` ($0.0$ to $1.0$)
- `reasoning: str` (model rationale)
- `evidence: dict[str, Any]` (structured evidence payload)
- `criteria_results: dict[str, bool]` (per-criterion pass/fail breakdown)
- `confidence: float | None` (judge confidence)
- `provider: str`, `model: str`, `timestamp: datetime`

---

## 4. Thresholds & Confidence

### Configurable Thresholds
Each semantic expectation accepts a `threshold` argument ($0.0 \le \text{threshold} \le 1.0$):

```python
from aireliability import SemanticRelevance

# Pass if score >= 0.80, fail otherwise
expectation = SemanticRelevance(threshold=0.80)
```

### Deterministic vs. Model Confidence
In failure reports:
- Deterministic assertions set `confidence = 1.0`.
- Semantic evaluators report the judge's calibrated confidence (e.g. `0.85` or `0.90`), explicitly preventing probabilistic inferences from masquerading as deterministic facts.

---

## 5. Grounding: Reference Answers, Criteria, and Context

Semantic expectations support multidimensional grounding:

```python
from aireliability import SemanticExpectation

expectation = SemanticExpectation(
    criteria=[
        "must answer user's return query",
        "must specify return window timeframe",
        "must not contradict return policy",
    ],
    reference="Items can be returned within 30 days of purchase at any UPS location.",
    context={
        "retrieved_policy_id": "pol_return_v2",
        "policy_text": "Standard return window is 30 days for undamaged goods.",
    },
    threshold=0.85,
)
```

If `reference` is omitted from `SemanticExpectation`, the evaluator automatically falls back to `test_case.expected_output` if present.

---

## 6. Evaluation Composition

Multiple evaluators can be composed simultaneously in a single `ReliabilityRunner`:

```python
from aireliability import (
    OutputContains,
    ReliabilityRunner,
    SemanticRelevance,
    TestCase,
    ToolOrder,
)

runner = ReliabilityRunner(
    agent=my_agent,
    evaluators=[
        # 1. Deterministic sequence invariant
        ToolOrder(["get_order", "cancel_order", "refund_order"]),
        # 2. Deterministic text invariant
        OutputContains("refund"),
        # 3. Semantic quality & tone check
        SemanticRelevance(threshold=0.80),
    ],
)

result = runner.run(test_case)
```

**Composition Rules**:
- Every evaluator runs and produces an independent `EvaluationResult`.
- Overall test run `passed` is `True` only if **all** evaluators pass and no execution crashes occurred.
- If a deterministic evaluator passes but a semantic evaluator fails, the failure is reported under `FailureCategory.OUTPUT` with `FailureType.SEMANTIC_RELEVANCE` and the semantic judge's explanation as evidence.

---

## 7. Deterministic `MockSemanticJudge` for Testing & CI

For continuous integration and local unit testing, `MockSemanticJudge` provides deterministic evaluations without remote API calls or GPU requirements:

```python
from aireliability import MockSemanticJudge, SemanticExpectation

mock_judge = MockSemanticJudge(
    default_score=0.92,
    threshold=0.80,
    confidence=0.95,
)

evaluator = SemanticExpectation(threshold=0.80, judge=mock_judge)
```

`MockSemanticJudge` also supports custom rules:
```python
def custom_evaluation_rule(prompt, output, reference, criteria):
    if "forbidden_term" in output:
        return 0.2, "Forbidden term present in output"
    return 0.95, "Criteria fully satisfied"


judge = MockSemanticJudge(custom_rule=custom_evaluation_rule)
```

---

## 8. Failure and Regression Integration

Semantic failures integrate seamlessly into the core reliability loop:
```text
Semantic Evaluation Failure
             ↓
FailureAnalyzer classifies as category: OUTPUT, type: SEMANTIC_RELEVANCE
             ↓
FailureReport synthesized (captures judge evidence, reasoning, confidence)
             ↓
RegressionGenerator synthesizes RegressionTest
             ↓
BaselineManager records regression in baseline comparison
```

---

## 9. Current Limitations

1. **Remote LLM Network Dependency**: Production semantic judges require calling external LLM inference endpoints or running local SLM servers.
2. **Scoring Subjectivity**: Criteria evaluation depends on prompt design and model alignment.
3. **No Automatic Ground Truth**: High semantic similarity does not guarantee factual correctness if the reference answer itself is flawed.
