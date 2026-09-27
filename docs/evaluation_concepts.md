# Evaluation Concepts: Deterministic vs Semantic vs Observability vs Regression Testing

Understanding the distinct roles of evaluation, observability, and regression testing is critical for building trustworthy AI applications.

---

## 1. Deterministic Evaluation

### Definition
Deterministic evaluation tests software against explicit, mathematically verifiable rules and invariants without relying on another probabilistic model (such as an LLM judge).

### Characteristics
- **Repeatability**: 100% reproducible. Given the same inputs and trace, the outcome will never fluctuate.
- **Latency**: Sub-millisecond (typically 1–5 microseconds per assertion).
- **Cost**: $0.00 compute cost beyond CPU clock cycles.
- **Confidence**: `1.0` confidence score when evidence supports the violation.

### When to Use
- **Tool usage**: Ensuring required tools were called (`ToolCalled`), forbidden tools were not called (`ToolNotCalled`), and tools were invoked with required parameters (`ToolArguments`).
- **Orchestration order**: Verifying sequences like `lookup_order` $\rightarrow$ `verify_eligibility` $\rightarrow$ `issue_refund` (`ToolOrder`).
- **Structural output contracts**: Validating JSON Schemas, required keys, and types (`SchemaMatch`).
- **Resource bounds**: Enforcing response deadlines (`MaxLatency`) and financial budgets (`MaxCost`).
- **Deterministic substrings**: Guaranteeing mandatory disclaimers, format tokens, or system identifiers (`OutputContains`, `OutputEquals`).

---

## 2. Semantic Evaluation

### Definition
Semantic evaluation assesses linguistic meaning, context relevance, qualitative tone, or subjective intent when strict string matching or schema verification is insufficient.

### Characteristics
- **Probabilistic Nature**: Uses embedding distances, cross-encoders, or LLM-as-a-judge prompts.
- **Variability**: Subject to prompt drift, temperature jitter, and evaluator model updates.
- **Latency & Cost**: Requires remote network calls (200ms–3000ms) and API token consumption.
- **Confidence**: Fractional confidence scores (e.g. 0.75 relevance), requiring confidence intervals.

### When to Use
- Evaluating nuanced conversational empathy or user sentiment.
- Assessing factual consistency across long-form synthesis.
- Ranking multiple valid formulations of a natural language explanation.

> **Architectural Boundary in `aireliability`**:  
> In Phase 1–10, `aireliability` implements a robust, deterministic core. Semantic evaluators can be added as custom plugins implementing the `Evaluator` protocol without compromising deterministic invariants.

---

## 3. Observability vs Testing

| Dimension | Observability (Monitoring & APM) | Reliability Testing (`aireliability`) |
| :--- | :--- | :--- |
| **Primary Goal** | Passive telemetry, metrics, and incident debugging in production. | Active prevention of regressions before and during deployment. |
| **Lifecycle Phase** | Post-deployment (runtime). | Pre-deployment, CI/CD gates, local pair programming. |
| **Execution Trigger** | Live end-user traffic. | Explicit automated test cases and regression suites. |
| **Action on Failure**| Alert on-call engineers; record dashboard metrics. | **Block CI pipeline**; synthesize reproducible regression tests. |
| **State Tracking** | Rolling averages, histograms, p99 latencies. | Historical baseline snapshots; diffing previous vs current results. |

Observability tells you *that something broke in production*. `aireliability` ensures *the issue is converted into a regression test so it never breaks again*.

---

## 4. Regression Testing in AI Systems

### What Constitutes an AI Regression?
In traditional software, regression means an existing unit test that passed on commit $A$ now throws an exception on commit $B$.

In AI applications, models rarely throw exceptions when they degrade. Instead:
- A prompt tweak improves creative writing but causes the agent to skip a safety verification tool.
- A model update changes output format, breaking downstream consumers.
- A tool definition change causes the agent to call tools out of sequence.

### The Regression Taxonomy
`aireliability` categorizes comparison against baselines into five distinct states:

$$\begin{aligned}
\text{Passing in Baseline} + \text{Passing Now} &\implies \mathbf{PASSING} \\
\text{Passing in Baseline} + \text{Failing Now} &\implies \mathbf{REGRESSION}\text{ (CI Gate Blocks)} \\
\text{Failing in Baseline} + \text{Failing Now} &\implies \mathbf{KNOWN\_FAILURE} \\
\text{Failing in Baseline} + \text{Passing Now} &\implies \mathbf{FIXED} \\
\text{Not in Baseline} + \text{Any Outcome} &\implies \mathbf{NEW}
\end{aligned}$$

By distinguishing **known failures** from **regressions**, teams can iterate rapidly without being blocked by preexisting issues while guaranteeing zero backsliding on working capabilities.
