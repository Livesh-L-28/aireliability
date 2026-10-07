"""Runaway Execution and Resource Limit Detector for Phase 40.

Evaluates trajectories against operational budgets and ceilings:
- max_steps
- max_tool_calls
- max_retries
- max_cost
- max_runtime_seconds

Detects LIMIT_EXCEEDED and RUNAWAY_RISK without terminating actual execution environments.
"""

from __future__ import annotations

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
    AgentStep,
)
from aireliability.core.models import FailureSeverity


class RunawayDetector:
    """Monitors resource consumption and detects runaway agent trajectories."""

    def __init__(
        self,
        max_steps: int = 50,
        max_tool_calls: int = 30,
        max_retries: int = 5,
        max_cost: float = 5.0,
        max_runtime_seconds: float = 120.0,
        risk_threshold_ratio: float = 0.85,
    ) -> None:
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.max_retries = max_retries
        self.max_cost = max_cost
        self.max_runtime_seconds = max_runtime_seconds
        self.risk_threshold_ratio = risk_threshold_ratio

    def evaluate_trajectory_limits(
        self,
        steps: list[AgentStep],
        total_cost: float | None = None,
        total_latency_seconds: float | None = None,
    ) -> tuple[list[AgentFailure], AgentStageScore]:
        """Audit trajectory metrics against resource boundaries."""
        failures: list[AgentFailure] = []

        step_count = len(steps)
        tool_call_count = sum(1 for s in steps if s.tool_call is not None)
        cost = total_cost if total_cost is not None else sum(s.cost for s in steps)
        latency = (
            total_latency_seconds
            if total_latency_seconds is not None
            else sum(s.latency_seconds for s in steps)
        )

        # 1. Step budget check
        if step_count > self.max_steps:
            failures.append(
                AgentFailure(
                    stage=AgentStage.RUNAWAY,
                    category=AgentFailureCategory.LIMIT_EXCEEDED,
                    severity=FailureSeverity.CRITICAL,
                    message=f"Trajectory steps ({step_count}) exceeded ceiling ({self.max_steps})",
                    affected_component="trajectory_budget",
                    confidence=1.0,
                    metadata={"step_count": step_count, "limit": self.max_steps},
                )
            )
        elif step_count >= int(self.max_steps * self.risk_threshold_ratio):
            failures.append(
                AgentFailure(
                    stage=AgentStage.RUNAWAY,
                    category=AgentFailureCategory.RUNAWAY_RISK,
                    severity=FailureSeverity.MEDIUM,
                    message=f"Trajectory steps ({step_count}) approached {int(self.risk_threshold_ratio * 100)}% of ceiling ({self.max_steps})",
                    affected_component="trajectory_budget",
                    confidence=0.85,
                )
            )

        # 2. Tool call budget check
        if tool_call_count > self.max_tool_calls:
            failures.append(
                AgentFailure(
                    stage=AgentStage.RUNAWAY,
                    category=AgentFailureCategory.LIMIT_EXCEEDED,
                    severity=FailureSeverity.HIGH,
                    message=f"Tool calls ({tool_call_count}) exceeded budget ({self.max_tool_calls})",
                    affected_component="tool_budget",
                    confidence=1.0,
                    metadata={
                        "tool_calls": tool_call_count,
                        "limit": self.max_tool_calls,
                    },
                )
            )
        elif tool_call_count >= int(self.max_tool_calls * self.risk_threshold_ratio):
            failures.append(
                AgentFailure(
                    stage=AgentStage.RUNAWAY,
                    category=AgentFailureCategory.RUNAWAY_RISK,
                    severity=FailureSeverity.LOW,
                    message=f"Tool calls ({tool_call_count}) approached ceiling ({self.max_tool_calls})",
                    affected_component="tool_budget",
                    confidence=0.80,
                )
            )

        # 3. Cost budget check
        if cost > self.max_cost:
            failures.append(
                AgentFailure(
                    stage=AgentStage.COST,
                    category=AgentFailureCategory.COST_FAILURE,
                    severity=FailureSeverity.HIGH,
                    message=f"Total cost (${cost:.4f}) exceeded budget (${self.max_cost:.4f})",
                    affected_component="cost_budget",
                    confidence=1.0,
                    metadata={"cost": cost, "limit": self.max_cost},
                )
            )

        # 4. Latency budget check
        if latency > self.max_runtime_seconds:
            failures.append(
                AgentFailure(
                    stage=AgentStage.LATENCY,
                    category=AgentFailureCategory.LATENCY_FAILURE,
                    severity=FailureSeverity.MEDIUM,
                    message=f"Total runtime ({latency:.2f}s) exceeded budget ({self.max_runtime_seconds:.2f}s)",
                    affected_component="latency_budget",
                    confidence=1.0,
                    metadata={"runtime": latency, "limit": self.max_runtime_seconds},
                )
            )

        # Score calculation
        score = 1.0
        for f in failures:
            if f.severity == FailureSeverity.CRITICAL:
                score -= 0.60
            elif f.severity == FailureSeverity.HIGH:
                score -= 0.30
            elif f.severity == FailureSeverity.MEDIUM:
                score -= 0.15
            else:
                score -= 0.05
        score = max(0.0, min(1.0, score))

        stage_score = AgentStageScore(
            stage=AgentStage.RUNAWAY,
            score=score,
            confidence=0.95,
            metrics={
                "runaway_score": score,
                "step_count": float(step_count),
                "tool_call_count": float(tool_call_count),
                "cost": float(cost),
                "latency_seconds": float(latency),
            },
            failures=failures,
            explanation=(
                "Execution within defined resource limits"
                if not failures
                else f"Resource limit warnings or violations detected: {len(failures)}"
            ),
        )

        return failures, stage_score
