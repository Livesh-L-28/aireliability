"""Strongly typed data models for Phase 38 AI Reliability Optimization."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "opt") -> str:
    """Generate a unique identifier with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return the current datetime in UTC timezone."""
    return datetime.now(UTC)


class ObjectiveDirection(StrEnum):
    """Direction of optimization for an objective."""

    MAXIMIZE = "MAXIMIZE"
    MINIMIZE = "MINIMIZE"
    TARGET = "TARGET"


class ConstraintOperator(StrEnum):
    """Mathematical operator for an optimization constraint."""

    LE = "<="
    GE = ">="
    EQ = "=="
    LT = "<"
    GT = ">"


class VariableDomain(StrEnum):
    """Data domain of an optimizable variable."""

    FLOAT = "float"
    INT = "int"
    CHOICE = "choice"
    BOOL = "bool"


class ComponentCategory(StrEnum):
    """Component category for an optimizable variable."""

    MODEL = "model"
    GENERATION = "generation"
    RETRIEVAL = "retrieval"
    RAG = "rag"
    PROMPT = "prompt"
    TOOL = "tool"
    AGENT = "agent"
    INFRASTRUCTURE = "infrastructure"


class CandidateStatus(StrEnum):
    """Evaluation and lifecycle status of an optimization candidate."""

    PENDING = "PENDING"
    EVALUATED = "EVALUATED"
    INVALID = "INVALID"
    DOMINATED = "DOMINATED"
    PARETO_OPTIMAL = "PARETO_OPTIMAL"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"


class StoppingReason(StrEnum):
    """Termination condition for an optimization search run."""

    COMPLETED = "COMPLETED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    CONVERGENCE = "CONVERGENCE"
    NO_IMPROVEMENT = "NO_IMPROVEMENT"
    TARGET_ACHIEVED = "TARGET_ACHIEVED"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"
    NO_FEASIBLE_CONFIGURATION = "NO_FEASIBLE_CONFIGURATION"


class SelectionStrategy(StrEnum):
    """Policy strategy for selecting a single candidate from the Pareto frontier."""

    BALANCED = "balanced_score"
    HIGHEST_QUALITY = "highest_quality"
    LOWEST_COST = "lowest_cost"
    LOWEST_LATENCY = "lowest_latency"
    WEIGHTED_PREFERENCE = "weighted_preference"
    TARGET_OBJECTIVE = "target_objective"
    EXPLICIT_SELECTION = "explicit_selection"


class OptimizationObjective(BaseModel):
    """Specification of an optimization objective."""

    model_config = ConfigDict(frozen=True)

    objective_id: str
    metric: str
    direction: ObjectiveDirection = ObjectiveDirection.MAXIMIZE
    target_value: float | None = None
    weight: float = 1.0
    min_threshold: float | None = None
    max_threshold: float | None = None
    is_hard_constraint: bool = False
    importance: float = 1.0
    safety_classification: str = "standard"


class OptimizationConstraint(BaseModel):
    """Hard or soft threshold constraint on a system metric."""

    model_config = ConfigDict(frozen=True)

    constraint_id: str
    metric: str
    operator: ConstraintOperator = ConstraintOperator.GE
    threshold: float
    is_hard: bool = True
    description: str = ""

    def evaluate(self, value: float) -> bool:
        """Check whether a measured value satisfies this constraint."""
        if self.operator == ConstraintOperator.GE:
            return value >= self.threshold
        if self.operator == ConstraintOperator.LE:
            return value <= self.threshold
        if self.operator == ConstraintOperator.GT:
            return value > self.threshold
        if self.operator == ConstraintOperator.LT:
            return value < self.threshold
        if self.operator == ConstraintOperator.EQ:
            return abs(value - self.threshold) < 1e-6
        return False


class OptimizationVariable(BaseModel):
    """Definition of an explicitly registered optimizable parameter."""

    model_config = ConfigDict(frozen=True)

    variable_id: str
    name: str
    component: ComponentCategory = ComponentCategory.GENERATION
    domain: VariableDomain = VariableDomain.FLOAT
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    choices: list[Any] = Field(default_factory=list)
    default_value: Any = None
    description: str = ""


class OptimizationConfiguration(BaseModel):
    """Concrete values for a set of optimizable parameters with deterministic fingerprint."""

    model_config = ConfigDict(frozen=True)

    values: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = ""
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class OptimizationCandidate(BaseModel):
    """Candidate configuration with evaluation outcomes, Pareto status, and deltas."""

    model_config = ConfigDict(frozen=False)

    candidate_id: str = Field(default_factory=lambda: _generate_id("cand"))
    configuration: OptimizationConfiguration
    fingerprint: str
    parent_candidate_id: str | None = None
    generation_strategy: str = "initial"
    generation_params: dict[str, Any] = Field(default_factory=dict)
    status: CandidateStatus = CandidateStatus.PENDING
    objective_values: dict[str, float] = Field(default_factory=dict)
    normalized_values: dict[str, float] = Field(default_factory=dict)
    metric_stats: dict[str, dict[str, float]] = Field(default_factory=dict)
    constraint_violations: list[str] = Field(default_factory=list)
    baseline_deltas: dict[str, dict[str, float]] = Field(default_factory=dict)
    is_feasible: bool = True
    is_pareto: bool = False
    pareto_rank: int = 0
    crowding_distance: float | None = 0.0
    confidence: float = 1.0
    explanation: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class ParetoPoint(BaseModel):
    """Single candidate projection on the multi-objective Pareto trade-off surface."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    configuration_values: dict[str, Any] = Field(default_factory=dict)
    objective_values: dict[str, float] = Field(default_factory=dict)
    normalized_values: dict[str, float] = Field(default_factory=dict)
    rank: int = 1
    crowding_distance: float | None = 0.0
    is_dominated: bool = False


class ParetoFrontier(BaseModel):
    """Calculated non-dominated frontier and dominated candidate summary."""

    model_config = ConfigDict(frozen=True)

    frontier_id: str = Field(default_factory=lambda: _generate_id("pareto"))
    points: list[ParetoPoint] = Field(default_factory=list)
    objective_ids: list[str] = Field(default_factory=list)
    non_dominated_candidate_ids: list[str] = Field(default_factory=list)
    dominated_candidate_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OptimizationProblem(BaseModel):
    """Formal problem definition binding baseline, variables, objectives, and constraints."""

    model_config = ConfigDict(frozen=True)

    problem_id: str = Field(default_factory=lambda: _generate_id("prob"))
    name: str
    description: str = ""
    baseline_config: OptimizationConfiguration
    baseline_metrics: dict[str, float] = Field(default_factory=dict)
    variables: list[OptimizationVariable] = Field(default_factory=list)
    objectives: list[OptimizationObjective] = Field(default_factory=list)
    constraints: list[OptimizationConstraint] = Field(default_factory=list)
    dataset_id: str = ""
    model_version: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class OptimizationBudget(BaseModel):
    """Resource, evaluation count, and runtime constraints governing the search."""

    model_config = ConfigDict(frozen=True)

    max_candidates: int = 50
    max_evaluations: int = 100
    max_generations: int = 10
    max_runtime_seconds: float = 300.0
    max_cost: float = 100.0
    max_tokens: int = 500000
    max_concurrent: int = 1


class OptimizationPolicy(BaseModel):
    """Governance policy dictating candidate selection, risk limits, and rollout safety."""

    model_config = ConfigDict(frozen=True)

    policy_id: str = "default_policy"
    selection_strategy: SelectionStrategy = SelectionStrategy.BALANCED
    preference_weights: dict[str, float] = Field(default_factory=dict)
    required_quality: float = 0.8
    required_safety: float = 0.95
    required_security: float = 0.95
    allowed_risk: str = "LOW"
    minimum_improvement: float = 0.01
    auto_select: bool = False
    auto_deploy: bool = False
    repeated_evaluations: int = 1
    canary_required: bool = True
    max_rollouts_per_target: int = 3
    cooldown_seconds: float = 3600.0


class OptimizationExperiment(BaseModel):
    """Reproducible experiment record capturing per-candidate evaluation outcomes."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str = Field(default_factory=lambda: _generate_id("exp"))
    optimization_id: str
    candidate_id: str
    configuration: dict[str, Any]
    run_index: int = 0
    metrics: dict[str, float] = Field(default_factory=dict)
    objective_scores: dict[str, float] = Field(default_factory=dict)
    execution_duration: float = 0.0
    resource_cost: float = 0.0
    seed: int = 42
    timestamp: datetime = Field(default_factory=_utc_now)


class OptimizationDecision(BaseModel):
    """Formal audit decision recording candidate selection and deployment rationale."""

    model_config = ConfigDict(frozen=True)

    decision_id: str = Field(default_factory=lambda: _generate_id("dec"))
    optimization_id: str
    selected_candidate_id: str
    rationale: str
    risk_tier: str = "LOW"
    approved_by: str = ""
    approval_token: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)


class OptimizationResult(BaseModel):
    """Complete results of an optimization run including Pareto frontier and selection."""

    model_config = ConfigDict(frozen=False)

    optimization_id: str = Field(default_factory=lambda: _generate_id("opt"))
    problem: OptimizationProblem
    baseline_config: OptimizationConfiguration
    baseline_metrics: dict[str, float] = Field(default_factory=dict)
    candidates: list[OptimizationCandidate] = Field(default_factory=list)
    pareto_frontier: ParetoFrontier
    selected_candidate: OptimizationCandidate | None = None
    stopping_reason: StoppingReason = StoppingReason.COMPLETED
    budget_used: dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    confidence: float = 1.0
    experiments: list[OptimizationExperiment] = Field(default_factory=list)
    decision: OptimizationDecision | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
