# Phase 40 — Advanced Agent Reliability Architecture

## 1. Executive Summary

Phase 40 introduces the **Advanced Agent Reliability Engine** (`aireliability.agent`), extending the AI Reliability Engine to evaluate, diagnose, test, monitor, self-heal, and optimize autonomous AI agents and multi-agent systems across their entire lifecycle.

A fundamental axiom of agent reliability is that **an agent must be evaluated as an execution trajectory, not merely as a final answer**. A seemingly correct final response can easily obscure critical upstream failures—such as selecting dangerous or wrong tools, repeatedly passing invalid schema arguments, entering redundant loops, or mutating stale state. 

Phase 40 provides deterministic, evidence-based diagnostic decomposition across all 15 stages of the agent execution lifecycle without speculating on unobservable neural weights or hidden chain-of-thought tokens.

---

## 2. Core Agent Reliability Lifecycle

```text
USER REQUEST
    ↓
TASK ANALYSIS
    ↓
TASK DECOMPOSITION
    ↓
PLANNING
    ↓
ACTION SELECTION
    ↓
TOOL SELECTION
    ↓
TOOL ARGUMENT GENERATION
    ↓
TOOL EXECUTION
    ↓
OBSERVATION
    ↓
STATE / MEMORY UPDATE
    ↓
REASONING / REPLANNING
    ↓
GOAL VERIFICATION
    ↓
FINAL RESPONSE
    ↓
AGENT RELIABILITY SCORE & ROOT CAUSE ATTRIBUTION
    ↓
BRIDGES: INTELLIGENCE (34) | GRAPH (35) | TEST (36) | HEALING (37) | OPTIMIZATION (38) | RAG (39)
```

---

## 3. Core Architectural Principles

1. **Trajectory-First Evaluation**: Every step within the agent trajectory is evaluated independently. A correct final output never excuses, hides, or compensates for intermediate trajectory failures.
2. **Never Fabricate Expected Behavior**: The engine never invents a supposed "correct tool" or "correct plan" unless explicitly defined by benchmark ground truth or deterministic schema invariants. Missing ground truth evaluates to `UNKNOWN`, never a hallucinated failure.
3. **No Infrastructure Blame**: External network timeouts, API 500s, or provider rate limits are attributed to `TOOL_EXECUTION_FAILURE` (infrastructure) rather than blaming the agent, unless evidence demonstrates the agent caused the error through malformed parameters or retry storms.
4. **Observable Reasoning Only**: The system assesses stated plans, explicit rationale, and observable actions against observations. It never attempts to reconstruct or police private chain-of-thought reasoning.
5. **Untrusted External Observations**: Tool outputs, retrieved memories, API responses, and inter-agent messages are treated as untrusted inputs subject to prompt injection audits and secret sanitization.
6. **Hard Safety & Security Vetoes**: Any prompt injection, unauthorized tool call, or secret credential leak triggers an immediate, non-compensatory veto capping the overall reliability score at $\le 0.30$.
7. **Full Subsystem Reuse**: Agent failures seamlessly feed into Phase 34 (Failure Intelligence), Phase 35 (Knowledge Graph), Phase 36 (Test Generation), Phase 37 (Self-Healing), Phase 38 (Optimization), and Phase 39 (RAG Reliability).

---

## 4. Evaluated Stages & Taxonomy

| Stage | Evaluator | Core Failure Categories |
|---|---|---|
| `TASK_ANALYSIS` | `TaskAnalyzer` | `TASK_UNDERSTANDING_FAILURE`, `MISSING_CONSTRAINT`, `MISINTERPRETED_GOAL`, `UNSUPPORTED_OBJECTIVE` |
| `DECOMPOSITION` | `TaskDecompositionAnalyzer` | `DECOMPOSITION_FAILURE`, `DEPENDENCY_VIOLATION`, `CIRCULAR_DEPENDENCY` |
| `PLANNING` | `PlanEvaluator` | `PLAN_INCOMPLETE`, `PLAN_INCONSISTENT`, `PLAN_UNFEASIBLE`, `PLAN_REDUNDANCY`, `PLAN_DEPENDENCY_FAILURE` |
| `TOOL_SELECTION` | `ToolEvaluator` | `WRONG_TOOL`, `UNNECESSARY_TOOL`, `MISSING_TOOL`, `UNSAFE_TOOL`, `UNNECESSARY_HIGH_RISK_TOOL` |
| `TOOL_ARGUMENTS` | `ToolEvaluator` | `INVALID_ARGUMENTS`, `MISSING_ARGUMENT`, `TYPE_ERROR`, `RANGE_ERROR`, `DEPENDENCY_ERROR`, `UNSAFE_ARGUMENT` |
| `TOOL_EXECUTION` | `ToolEvaluator` | `TOOL_TIMEOUT`, `TOOL_ERROR`, `TOOL_UNAVAILABLE`, `TOOL_AUTH_FAILURE`, `TOOL_RATE_LIMIT`, `TOOL_PARTIAL_FAILURE` |
| `OBSERVATION` | `ObservationEvaluator` | `OBSERVATION_INTERPRETATION_FAILURE`, `MALFORMED_TOOL_RESULT`, `TOOL_OUTPUT_INJECTION` |
| `STATE` | `StateTracker` | `INVALID_STATE_TRANSITION`, `MISSING_STATE_UPDATE`, `STALE_STATE`, `CORRUPTED_STATE` |
| `MEMORY` | `MemoryAnalyzer` | `MEMORY_MISS`, `MEMORY_STALENESS`, `MEMORY_CONTRADICTION`, `MEMORY_DUPLICATION`, `MEMORY_CORRUPTION` |
| `REASONING` | `ReasoningEvaluator` | `REASONING_ACTION_MISMATCH`, `GOAL_DRIFT` |
| `REPLANNING` | `ReasoningEvaluator` | `FAILED_REPLAN`, `REPEATED_REPLAN`, `NO_ADAPTATION` |
| `LOOP` | `LoopDetector` | `RECOVERABLE_LOOP`, `RUNAWAY_LOOP`, `INFINITE_LOOP_RISK` |
| `RETRY` | `RetryAnalyzer` | `REDUNDANT_RETRY`, `RETRY_STORM` |
| `RUNAWAY` | `RunawayDetector` | `LIMIT_EXCEEDED`, `RUNAWAY_RISK` |
| `MULTI_AGENT` | `MultiAgentAnalyzer` | `AGENT_HANDOFF_FAILURE`, `AGENT_ROLE_FAILURE`, `INTER_AGENT_CONFLICT`, `MESSAGE_LOSS` |
| `GOAL_VERIFICATION` | `GoalVerifier` | `GOAL_VERIFICATION_FAILURE`, `GOAL_NOT_ACHIEVED`, `PARTIAL_COMPLETION`, `PREMATURE_TERMINATION` |
| `SECURITY` | `ObservationEvaluator` | `PROMPT_INJECTION`, `TOOL_OUTPUT_INJECTION`, `SECRET_LEAKAGE`, `UNAUTHORIZED_TOOL` |

---

## 5. Integration Bridges

### Phase 34 Intelligence Bridge
Normalizes agent failures into `FailureReport`s, clusters recurring agent mistakes (e.g. repeated schema invalidation), identifies cross-run correlations, and synthesizes prioritized `ReliabilityRecommendation`s.

### Phase 35 Knowledge Graph Bridge
Registers `AgentRun`, `AgentStep`, `ToolCall`, `Observation`, and `AgentFailure` entities into the Knowledge Graph, building directed edges (`EXECUTED`, `USED_TOOL`, `PRODUCED`, `FAILED`). Enables bidirectional provenance traversal from failing actions back to query constraints.

### Phase 36 Automated Test Generation Bridge
Transforms diagnosed trajectory anti-patterns (such as repeated invalid retries or runaway loops) into deterministic regression test cases executed by `TestGenerationEngine`.

### Phase 37 Self-Healing Bridge
Maps diagnosed agent failures (such as schema mismatches or missing tools) to `RemediationProposal`s containing prompt patches or configuration adjustments, subjected to verification gates and rollback controllers.

### Phase 38 Multi-Objective Optimization Bridge
Formulates Pareto optimization problems tuning agent hyperparameters (e.g. `max_steps`, `max_retries`, tool confidence cutoffs) balancing goal success against execution latency and token cost.

### Phase 39 RAG Subsystem Attribution Bridge
Disentangles whether a failure occurred in agent tool routing vs. internal RAG retrieval/grounding, ensuring clear root-cause accountability.

---

## 6. CLI Reference

Phase 40 provides 21 CLI subcommands under `airel agent`:
- `airel agent evaluate`: Full agent trajectory reliability evaluation.
- `airel agent analyze`: Analyze task complexity, constraints, and ambiguity.
- `airel agent trajectory`: Inspect step-by-step execution timeline.
- `airel agent plan`: Evaluate plan validity, completeness, and deviation.
- `airel agent tools`: Validate tool selection, schema arguments, and risk tiers.
- `airel agent loops`: Detect cyclic trajectory patterns and runaway loops.
- `airel agent retries`: Analyze retry efficacy and retry storms.
- `airel agent memory`: Audit memory read/write/retrieve operations.
- `airel agent state`: Validate state transition consistency.
- `airel agent goals`: Verify goal criteria satisfaction independently.
- `airel agent handoffs`: Analyze multi-agent communication and task transfers.
- `airel agent failures`: Explain root-cause failure attributions.
- `airel agent drift`: Detect behavioral, tool, and trajectory drift.
- `airel agent security`: Audit tool output injection and credential exposure.
- `airel agent regression`: Execute golden trajectory test suites.
- `airel agent diagnose`: Run root-cause diagnostic engine.
- `airel agent tests`: Generate automated regression tests from failures.
- `airel agent heal`: Propose self-healing remediation patches.
- `airel agent optimize`: Formulate Pareto optimization problems.
- `airel agent report`: Generate multi-format evaluation summaries.
- `airel agent inspect`: Inspect serialized run diagnostics.
