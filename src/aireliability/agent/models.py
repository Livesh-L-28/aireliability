"""Data models and enums for Phase 40 Advanced Agent Reliability Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aireliability.core.models import FailureSeverity


def _generate_id(prefix: str = "agent") -> str:
    """Generate a unique identifier with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return the current datetime in UTC timezone."""
    return datetime.now(UTC)


class AgentStage(StrEnum):
    """Lifecycle stages of autonomous AI agent execution."""

    TASK_ANALYSIS = "task_analysis"
    DECOMPOSITION = "decomposition"
    PLANNING = "planning"
    ACTION_SELECTION = "action_selection"
    TOOL_SELECTION = "tool_selection"
    TOOL_ARGUMENTS = "tool_arguments"
    TOOL_EXECUTION = "tool_execution"
    OBSERVATION = "observation"
    STATE = "state"
    MEMORY = "memory"
    REASONING = "reasoning"
    REPLANNING = "replanning"
    LOOP = "loop"
    RETRY = "retry"
    RUNAWAY = "runaway"
    MULTI_AGENT = "multi_agent"
    GOAL_VERIFICATION = "goal_verification"
    FINAL_RESPONSE = "final_response"
    SECURITY = "security"
    COST = "cost"
    LATENCY = "latency"


class AgentFailureCategory(StrEnum):
    """Fine-grained failure taxonomy for autonomous agents."""

    # Task & Understanding
    TASK_FAILURE = "task_failure"
    TASK_UNDERSTANDING_FAILURE = "task_understanding_failure"
    MISSING_CONSTRAINT = "missing_constraint"
    MISINTERPRETED_GOAL = "misinterpreted_goal"
    UNSUPPORTED_OBJECTIVE = "unsupported_objective"

    # Decomposition
    DECOMPOSITION_FAILURE = "decomposition_failure"
    MISSING_SUBTASK = "missing_subtask"
    UNNECESSARY_SUBTASK = "unnecessary_subtask"
    DUPLICATE_SUBTASK = "duplicate_subtask"
    DEPENDENCY_VIOLATION = "dependency_violation"
    CIRCULAR_DEPENDENCY = "circular_dependency"

    # Planning
    PLANNING_FAILURE = "planning_failure"
    PLAN_INCOMPLETE = "plan_incomplete"
    PLAN_INCONSISTENT = "plan_inconsistent"
    PLAN_UNFEASIBLE = "plan_unfeasible"
    PLAN_REDUNDANCY = "plan_redundancy"
    PLAN_DEPENDENCY_FAILURE = "plan_dependency_failure"

    # Tool Selection
    TOOL_SELECTION_FAILURE = "tool_selection_failure"
    WRONG_TOOL = "wrong_tool"
    UNNECESSARY_TOOL = "unnecessary_tool"
    MISSING_TOOL = "missing_tool"
    UNSAFE_TOOL = "unsafe_tool"
    TOOL_SELECTION_REGRESSION = "tool_selection_regression"
    UNNECESSARY_HIGH_RISK_TOOL = "unnecessary_high_risk_tool"

    # Tool Arguments
    TOOL_ARGUMENT_FAILURE = "tool_argument_failure"
    INVALID_ARGUMENTS = "invalid_arguments"
    MISSING_ARGUMENT = "missing_argument"
    TYPE_ERROR = "type_error"
    RANGE_ERROR = "range_error"
    DEPENDENCY_ERROR = "dependency_error"
    UNSAFE_ARGUMENT = "unsafe_argument"

    # Tool Execution
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_ERROR = "tool_error"
    TOOL_UNAVAILABLE = "tool_unavailable"
    TOOL_AUTH_FAILURE = "tool_auth_failure"
    TOOL_RATE_LIMIT = "tool_rate_limit"
    TOOL_INVALID_RESPONSE = "tool_invalid_response"
    TOOL_PARTIAL_FAILURE = "tool_partial_failure"

    # Tool Results & Observations
    TOOL_RESULT_FAILURE = "tool_result_failure"
    MALFORMED_TOOL_RESULT = "malformed_tool_result"
    INCOMPLETE_TOOL_RESULT = "incomplete_tool_result"
    CONTRADICTORY_TOOL_RESULT = "contradictory_tool_result"
    UNTRUSTED_TOOL_RESULT = "untrusted_tool_result"
    OBSERVATION_FAILURE = "observation_failure"
    OBSERVATION_INTERPRETATION_FAILURE = "observation_interpretation_failure"

    # State & Memory
    STATE_FAILURE = "state_failure"
    INVALID_STATE_TRANSITION = "invalid_state_transition"
    MISSING_STATE_UPDATE = "missing_state_update"
    STALE_STATE = "stale_state"
    INCONSISTENT_STATE = "inconsistent_state"
    OVERWRITTEN_STATE = "overwritten_state"
    CORRUPTED_STATE = "corrupted_state"

    MEMORY_FAILURE = "memory_failure"
    MEMORY_MISS = "memory_miss"
    MEMORY_STALENESS = "memory_staleness"
    MEMORY_CONTRADICTION = "memory_contradiction"
    MEMORY_DUPLICATION = "memory_duplication"
    MEMORY_CORRUPTION = "memory_corruption"
    MEMORY_OVERWRITE = "memory_overwrite"

    # Reasoning, Actions & Replanning
    REASONING_ACTION_FAILURE = "reasoning_action_failure"
    REASONING_ACTION_MISMATCH = "reasoning_action_mismatch"
    REPLANNING_FAILURE = "replanning_failure"
    FAILED_REPLAN = "failed_replan"
    REPEATED_REPLAN = "repeated_replan"
    NO_ADAPTATION = "no_adaptation"

    # Loops, Runaway & Retries
    LOOP_FAILURE = "loop_failure"
    RECOVERABLE_LOOP = "recoverable_loop"
    RUNAWAY_LOOP = "runaway_loop"
    INFINITE_LOOP_RISK = "infinite_loop_risk"
    RUNAWAY_FAILURE = "runaway_failure"
    LIMIT_EXCEEDED = "limit_exceeded"
    RUNAWAY_RISK = "runaway_risk"
    RETRY_FAILURE = "retry_failure"
    REDUNDANT_RETRY = "redundant_retry"
    RETRY_STORM = "retry_storm"

    # Goal & Completion
    GOAL_DRIFT = "goal_drift"
    GOAL_VERIFICATION_FAILURE = "goal_verification_failure"
    GOAL_NOT_ACHIEVED = "goal_not_achieved"
    PARTIAL_COMPLETION = "partial_completion"
    PREMATURE_TERMINATION = "premature_termination"

    # Multi-Agent Coordination
    AGENT_HANDOFF_FAILURE = "agent_handoff_failure"
    AGENT_ROLE_FAILURE = "agent_role_failure"
    INTER_AGENT_CONFLICT = "inter_agent_conflict"
    DUPLICATE_WORK = "duplicate_work"
    MESSAGE_LOSS = "message_loss"
    CONTEXT_LOSS = "context_loss"
    MESSAGE_CORRUPTION = "message_corruption"
    STALE_MESSAGE = "stale_message"
    WRONG_RECIPIENT = "wrong_recipient"

    # Safety & Security
    SAFETY_FAILURE = "safety_failure"
    SECURITY_FAILURE = "security_failure"
    PROMPT_INJECTION = "prompt_injection"
    TOOL_OUTPUT_INJECTION = "tool_output_injection"
    UNTRUSTED_INSTRUCTION = "untrusted_instruction"
    UNAUTHORIZED_TOOL = "unauthorized_tool"
    SECRET_LEAKAGE = "secret_leakage"

    # FinOps & Performance
    COST_FAILURE = "cost_failure"
    LATENCY_FAILURE = "latency_failure"

    UNKNOWN = "unknown"


class GoalStatus(StrEnum):
    """Independent verification status of an agent goal."""

    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class CriterionStatus(StrEnum):
    """Satisfaction status of an individual goal criterion."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"


class ActionType(StrEnum):
    """Taxonomy of discrete actions executed in an agent trajectory."""

    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    OBSERVATION = "observation"
    STATE_UPDATE = "state_update"
    MEMORY_OP = "memory_op"
    REASON = "reason"
    REPLAN = "replan"
    HANDOFF = "handoff"
    GOAL_CHECK = "goal_check"
    FINAL_RESPONSE = "final_response"


class ToolRiskLevel(StrEnum):
    """Risk and permission tier of a tool."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrajectoryDeviationType(StrEnum):
    """Classification of plan-to-execution deviations."""

    EXPECTED_ADAPTATION = "expected_adaptation"
    BENIGN_DEVIATION = "benign_deviation"
    RISKY_DEVIATION = "risky_deviation"
    FAILURE = "failure"


class LoopClassification(StrEnum):
    """Classification of cyclic or repeated execution patterns."""

    NO_LOOP = "no_loop"
    FINITE_RETRY = "finite_retry"
    RECOVERABLE_LOOP = "recoverable_loop"
    RUNAWAY_LOOP = "runaway_loop"
    INFINITE_LOOP_RISK = "infinite_loop_risk"


class AgentConfidenceLevel(StrEnum):
    """Calibrated confidence level for reliability diagnostics."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Core Entities
# ---------------------------------------------------------------------------


class AgentAction(BaseModel):
    """Discrete action performed or proposed by an agent."""

    model_config = ConfigDict(frozen=True)

    action_id: str = Field(default_factory=lambda: _generate_id("act"))
    action_type: ActionType = ActionType.TOOL_CALL
    name: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)


class ToolCall(BaseModel):
    """Invocation of an external or local tool by an agent."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    call_id: str = Field(default_factory=lambda: _generate_id("call"))
    arguments: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utc_now)
    authorization_scope: str = "default"
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW


class ToolResult(BaseModel):
    """Output received from an executed tool."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    tool_name: str
    output: Any = None
    success: bool = True
    error_message: str | None = None
    latency_seconds: float = 0.0
    cost: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    """Agent perception or interpretation of external tool results/events."""

    model_config = ConfigDict(frozen=True)

    observation_id: str = Field(default_factory=lambda: _generate_id("obs"))
    source: str = "tool"
    raw_data: Any = None
    interpreted_content: str = ""
    is_safe: bool = True
    confidence: float = 1.0
    timestamp: datetime = Field(default_factory=_utc_now)


class AgentState(BaseModel):
    """Snapshot of agent internal state at a discrete step."""

    model_config = ConfigDict(frozen=True)

    state_id: str = Field(default_factory=lambda: _generate_id("state"))
    variables: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    step_index: int = 0
    timestamp: datetime = Field(default_factory=_utc_now)
    fingerprint: str = ""


class MemoryEvent(BaseModel):
    """Memory operation recorded during agent execution."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: _generate_id("mem"))
    operation: str = "read"  # read, write, update, delete, retrieve
    key: str = ""
    value: Any = None
    previous_value: Any = None
    success: bool = True
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GoalCriterion(BaseModel):
    """Individual verifiable success condition of a task goal."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str = Field(default_factory=lambda: _generate_id("crit"))
    description: str
    status: CriterionStatus = CriterionStatus.UNKNOWN
    evidence: str = ""
    is_mandatory: bool = True


class Goal(BaseModel):
    """Explicit objective or milestone expected of the agent."""

    model_config = ConfigDict(frozen=True)

    goal_id: str = Field(default_factory=lambda: _generate_id("goal"))
    description: str
    priority: int = 1
    required_outcome: str = ""
    constraints: list[str] = Field(default_factory=list)
    criteria: list[GoalCriterion] = Field(default_factory=list)
    parent_goal_id: str | None = None


class GoalVerification(BaseModel):
    """Independent audit of goal achievement based on trajectory evidence."""

    model_config = ConfigDict(frozen=True)

    goal_id: str
    overall_status: GoalStatus = GoalStatus.UNKNOWN
    completion_ratio: float = 0.0
    criteria_results: list[GoalCriterion] = Field(default_factory=list)
    explanation: str = ""
    evidence: list[str] = Field(default_factory=list)


class AgentPlan(BaseModel):
    """Intended procedural decomposition formulated by the agent."""

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=lambda: _generate_id("plan"))
    steps: list[str] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    estimated_cost: float = 0.0
    estimated_latency: float = 0.0
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW


class AgentFailure(BaseModel):
    """Specific diagnosed failure within an agent run."""

    model_config = ConfigDict(frozen=True)

    failure_id: str = Field(default_factory=lambda: _generate_id("afail"))
    stage: AgentStage
    category: AgentFailureCategory
    severity: FailureSeverity
    message: str
    affected_component: str = ""
    step_index: int | None = None
    confidence: float = 0.90
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStep(BaseModel):
    """Discrete transition point along an agent trajectory."""

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(default_factory=lambda: _generate_id("step"))
    sequence: int
    stage: AgentStage = AgentStage.ACTION_SELECTION
    action: str = ""
    action_type: ActionType = ActionType.TOOL_CALL
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    observation: Observation | None = None
    state_before: AgentState | None = None
    state_after: AgentState | None = None
    latency_seconds: float = 0.0
    cost: float = 0.0
    status: str = "success"
    failures: list[AgentFailure] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTrajectory(BaseModel):
    """Ordered chronological sequence of steps executed by an agent."""

    model_config = ConfigDict(frozen=True)

    steps: list[AgentStep] = Field(default_factory=list)
    total_steps: int = 0
    total_cost: float = 0.0
    total_latency_seconds: float = 0.0
    is_truncated: bool = False

    @model_validator(mode="before")
    @classmethod
    def sync_trajectory_totals(cls, data: Any) -> Any:
        if isinstance(data, dict):
            steps = data.get("steps") or []
            if "total_steps" not in data or data["total_steps"] == 0:
                data["total_steps"] = len(steps)
            if "total_cost" not in data or data["total_cost"] == 0.0:
                data["total_cost"] = sum(
                    (s.cost if hasattr(s, "cost") else s.get("cost", 0.0))
                    for s in steps
                )
            if (
                "total_latency_seconds" not in data
                or data["total_latency_seconds"] == 0.0
            ):
                data["total_latency_seconds"] = sum(
                    (
                        s.latency_seconds
                        if hasattr(s, "latency_seconds")
                        else s.get("latency_seconds", 0.0)
                    )
                    for s in steps
                )
        return data


class AgentTask(BaseModel):
    """Incoming user request and task specification."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(default_factory=lambda: _generate_id("task"))
    request_text: str
    goals: list[Goal] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    extracted_objectives: list[str] = Field(default_factory=list)
    ambiguity_score: float = 0.0
    completeness_score: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStageScore(BaseModel):
    """Reliability score for a specific agent execution stage."""

    model_config = ConfigDict(frozen=True)

    stage: AgentStage
    score: float
    confidence: float = 1.0
    metrics: dict[str, float] = Field(default_factory=dict)
    failures: list[AgentFailure] = Field(default_factory=list)
    explanation: str = ""


class AgentReliabilityScore(BaseModel):
    """Comprehensive composite reliability score for an agent run."""

    model_config = ConfigDict(frozen=True)

    overall_score: float = 1.0
    component_scores: dict[str, float] = Field(default_factory=dict)
    stage_scores: dict[str, AgentStageScore] = Field(default_factory=dict)
    safety_passed: bool = True
    security_passed: bool = True
    efficiency_score: float = 1.0
    summary: str = ""


class AgentRecommendation(BaseModel):
    """Prescriptive recommendation for remediation or optimization."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: str = Field(default_factory=lambda: _generate_id("arec"))
    title: str
    description: str
    priority: str = "high"
    action: str = ""
    rationale: str = ""
    affected_components: list[str] = Field(default_factory=list)


class AgentHandoff(BaseModel):
    """Task or message transfer between cooperating agents in a team."""

    model_config = ConfigDict(frozen=True)

    handoff_id: str = Field(default_factory=lambda: _generate_id("hoff"))
    from_agent_id: str
    to_agent_id: str
    task_context: str
    message: str
    correlation_id: str = ""
    required_fields: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utc_now)
    success: bool = True


class AgentMessage(BaseModel):
    """Structured message communicated between agents."""

    model_config = ConfigDict(frozen=True)

    message_id: str = Field(default_factory=lambda: _generate_id("msg"))
    sender: str
    recipient: str
    content: str
    context: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)


class ToolDependency(BaseModel):
    """Dependency link between tools in an agent workflow."""

    model_config = ConfigDict(frozen=True)

    source_tool: str
    target_tool: str
    is_critical: bool = False
    failure_propagation_rate: float = 0.0


class AgentRun(BaseModel):
    """Complete structured record of an agent execution lifecycle."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(default_factory=lambda: _generate_id("arun"))
    task: AgentTask
    agent_id: str = "default_agent"
    agent_version: str = "1.0.0"
    model: str = "llm-agent"
    model_version: str = "1.0.0"
    prompt_version: str = "1.0.0"
    tools: list[str] = Field(default_factory=list)
    plan: AgentPlan | None = None
    trajectory: AgentTrajectory = Field(default_factory=AgentTrajectory)
    state: AgentState | None = None
    memory_events: list[MemoryEvent] = Field(default_factory=list)
    handoffs: list[AgentHandoff] = Field(default_factory=list)
    final_response: str = ""
    goal_verification: GoalVerification = Field(
        default_factory=lambda: GoalVerification(goal_id="default")
    )
    reliability_score: AgentReliabilityScore = Field(
        default_factory=AgentReliabilityScore
    )
    stage_scores: dict[str, AgentStageScore] = Field(default_factory=dict)
    failures: list[AgentFailure] = Field(default_factory=list)
    recommendations: list[AgentRecommendation] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    environment: str = "production"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvaluationResult(BaseModel):
    """Batch evaluation outcome across multiple agent runs."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(default_factory=lambda: _generate_id("aeval"))
    runs: list[AgentRun] = Field(default_factory=list)
    mean_stage_scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 1.0
    total_failures: int = 0
    critical_failures_count: int = 0
    passed_release_gates: bool = True
    summary: str = ""
    created_at: datetime = Field(default_factory=_utc_now)

    @property
    def total_runs(self) -> int:
        """Return total count of evaluated agent runs."""
        return len(self.runs)


class AgentDriftResult(BaseModel):
    """Statistical drift analysis for agent behaviors across time/versions."""

    model_config = ConfigDict(frozen=True)

    drift_type: str
    drift_detected: bool
    distance: float
    p_value: float = 1.0
    threshold: float = 0.05
    baseline_mean: float = 0.0
    current_mean: float = 0.0
    message: str = ""


__all__ = [
    "ActionType",
    "AgentAction",
    "AgentConfidenceLevel",
    "AgentDriftResult",
    "AgentEvaluationResult",
    "AgentFailure",
    "AgentFailureCategory",
    "AgentHandoff",
    "AgentMessage",
    "AgentPlan",
    "AgentRecommendation",
    "AgentReliabilityScore",
    "AgentRun",
    "AgentStage",
    "AgentStageScore",
    "AgentState",
    "AgentStep",
    "AgentTask",
    "AgentTrajectory",
    "CriterionStatus",
    "Goal",
    "GoalCriterion",
    "GoalStatus",
    "GoalVerification",
    "LoopClassification",
    "MemoryEvent",
    "Observation",
    "ToolCall",
    "ToolDependency",
    "ToolResult",
    "ToolRiskLevel",
    "TrajectoryDeviationType",
]
