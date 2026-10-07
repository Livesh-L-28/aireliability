"""Plan Reliability and Plan-vs-Execution Trajectory Evaluator."""

from __future__ import annotations

from typing import Any

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentPlan,
    AgentStage,
    AgentStageScore,
    AgentTrajectory,
    ToolRiskLevel,
    TrajectoryDeviationType,
)
from aireliability.core.models import FailureSeverity


class PlanEvaluator:
    """Evaluates planned steps, feasibility, and compares intended plans with actual execution trajectories."""

    def evaluate_plan(
        self,
        plan: AgentPlan | None,
        available_tools: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AgentPlan, list[AgentFailure], AgentStageScore]:
        """Assess the initial plan for completeness, feasibility, and tool availability."""
        failures: list[AgentFailure] = []
        tools_set = set(t.lower() for t in (available_tools or []))

        if not plan or not plan.steps:
            fail = AgentFailure(
                stage=AgentStage.PLANNING,
                category=AgentFailureCategory.PLAN_INCOMPLETE,
                severity=FailureSeverity.CRITICAL,
                message="PLAN_INCOMPLETE: Agent proceeded without formulating an execution plan.",
                confidence=1.0,
            )
            failures.append(fail)
            empty_plan = plan or AgentPlan()
            stage_score = AgentStageScore(
                stage=AgentStage.PLANNING,
                score=0.0,
                failures=failures,
                explanation="Agent executed without a plan.",
            )
            return empty_plan, failures, stage_score

        # 1. Check for redundant/duplicate plan steps
        seen = set()
        duplicates = []
        for s in plan.steps:
            s_norm = s.strip().lower()
            if s_norm in seen:
                duplicates.append(s)
            seen.add(s_norm)

        if duplicates:
            failures.append(
                AgentFailure(
                    stage=AgentStage.PLANNING,
                    category=AgentFailureCategory.PLAN_REDUNDANCY,
                    severity=FailureSeverity.LOW,
                    message=f"PLAN_REDUNDANCY: Plan contains duplicate planned actions: {duplicates}.",
                    confidence=0.90,
                )
            )

        # 2. Check tool availability if tool set provided
        if available_tools:
            unfeasible_steps = []
            for s in plan.steps:
                words = s.lower().split()
                # If step explicitly references an unknown tool
                for w in words:
                    if (
                        w.endswith("_tool") or w.endswith("_api")
                    ) and w not in tools_set:
                        unfeasible_steps.append((s, w))
            for st, tool in unfeasible_steps:
                failures.append(
                    AgentFailure(
                        stage=AgentStage.PLANNING,
                        category=AgentFailureCategory.PLAN_UNFEASIBLE,
                        severity=FailureSeverity.HIGH,
                        message=f"PLAN_UNFEASIBLE: Step '{st}' requires unavailable tool '{tool}'.",
                        affected_component=tool,
                        confidence=0.95,
                    )
                )

        score = 1.0 - (0.15 * len(duplicates))
        if any(f.category == AgentFailureCategory.PLAN_UNFEASIBLE for f in failures):
            score -= 0.35
        score = round(max(0.0, score), 2)

        stage_score = AgentStageScore(
            stage=AgentStage.PLANNING,
            score=score,
            confidence=0.95,
            metrics={"planned_steps_count": float(len(plan.steps))},
            failures=failures,
            explanation=f"Plan contains {len(plan.steps)} steps. Feasibility score: {score:.2f}.",
        )

        return plan, failures, stage_score

    def compare_plan_vs_trajectory(
        self,
        plan: AgentPlan | None,
        trajectory: AgentTrajectory,
    ) -> tuple[TrajectoryDeviationType, list[AgentFailure], dict[str, Any]]:
        """Compare planned actions against actual trajectory steps and classify deviations."""
        failures: list[AgentFailure] = []
        details: dict[str, Any] = {
            "planned_steps": plan.steps if plan else [],
            "actual_steps": [s.action for s in trajectory.steps],
            "skipped_steps": [],
            "unexpected_steps": [],
            "deviation_type": TrajectoryDeviationType.BENIGN_DEVIATION.value,
        }

        if not plan or not plan.steps:
            return TrajectoryDeviationType.BENIGN_DEVIATION, [], details

        actual_actions = [s.action.lower() for s in trajectory.steps]
        planned_actions = [s.lower() for s in plan.steps]

        # 1. Identify skipped steps
        skipped = []
        for p in planned_actions:
            matched = any(p in act or act in p for act in actual_actions)
            if not matched:
                skipped.append(p)
        details["skipped_steps"] = skipped

        # 2. Identify unexpected steps
        unexpected = []
        for s in trajectory.steps:
            act = s.action.lower()
            if not any(act in p or p in act for p in planned_actions):
                unexpected.append(s.action)
        details["unexpected_steps"] = unexpected

        # 3. Classify deviation
        # Check if unexpected actions were adaptations in response to earlier failures
        has_earlier_failures = any(
            not s.tool_result.success for s in trajectory.steps if s.tool_result
        )

        if not skipped and not unexpected or has_earlier_failures and unexpected:
            deviation_type = TrajectoryDeviationType.EXPECTED_ADAPTATION
        elif any(
            s.tool_call and s.tool_call.risk_level == ToolRiskLevel.CRITICAL
            for s in trajectory.steps
            if s.action in unexpected
        ):
            deviation_type = TrajectoryDeviationType.RISKY_DEVIATION
            failures.append(
                AgentFailure(
                    stage=AgentStage.ACTION_SELECTION,
                    category=AgentFailureCategory.PLAN_INCONSISTENT,
                    severity=FailureSeverity.CRITICAL,
                    message=f"RISKY_DEVIATION: Unplanned execution of critical actions: {unexpected}.",
                    confidence=0.95,
                )
            )
        elif skipped:
            deviation_type = TrajectoryDeviationType.FAILURE
            failures.append(
                AgentFailure(
                    stage=AgentStage.ACTION_SELECTION,
                    category=AgentFailureCategory.PLAN_INCONSISTENT,
                    severity=FailureSeverity.HIGH,
                    message=f"PLAN_DEVIATION: Agent omitted planned critical steps: {skipped}.",
                    confidence=0.90,
                )
            )
        else:
            deviation_type = TrajectoryDeviationType.BENIGN_DEVIATION

        details["deviation_type"] = deviation_type.value
        return deviation_type, failures, details
