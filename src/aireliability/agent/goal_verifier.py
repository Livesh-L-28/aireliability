"""Independent Goal Verification Engine for Phase 40.

Evaluates completion of agent goals against observable trajectory evidence,
tool execution outputs, and final responses.
Enforces the fundamental principle: FINAL ANSWER != TASK SUCCESS.
Outputs independent GoalVerification with criterion-level satisfaction records.
"""

from __future__ import annotations

import re

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
    AgentStep,
    CriterionStatus,
    Goal,
    GoalCriterion,
    GoalStatus,
    GoalVerification,
)
from aireliability.core.models import FailureSeverity


class GoalVerifier:
    """Independently verifies goal and criteria achievement across trajectory evidence."""

    def __init__(self, partial_threshold: float = 0.50) -> None:
        self.partial_threshold = partial_threshold

    def verify_criterion(
        self,
        criterion: GoalCriterion,
        steps: list[AgentStep],
        final_response: str,
    ) -> GoalCriterion:
        """Evaluate a single criterion against trajectory observations and tool results."""
        crit_desc = criterion.description.lower()
        evidence_found: list[str] = []

        # 1. Search tool execution results and observations
        trajectory_evidence = False
        for s in steps:
            if s.tool_result is not None and s.tool_result.success:
                out_str = str(s.tool_result.output).lower()
                keywords = [w for w in re.findall(r"\w+", crit_desc) if len(w) > 3]
                if keywords and all(kw in out_str for kw in keywords[:2]):
                    evidence_found.append(
                        f"Step {s.sequence} tool '{s.tool_result.tool_name}' output confirms: {s.tool_result.output}"
                    )
                    trajectory_evidence = True

            if s.observation is not None:
                obs_str = s.observation.interpreted_content.lower()
                keywords = [w for w in re.findall(r"\w+", crit_desc) if len(w) > 3]
                if (
                    keywords
                    and all(kw in obs_str for kw in keywords[:2])
                    and not (s.tool_result and not s.tool_result.success)
                ):
                    evidence_found.append(
                        f"Step {s.sequence} observation matches criterion: '{s.observation.interpreted_content[:60]}'"
                    )
                    trajectory_evidence = True

        # 2. Check final response as supporting evidence (not solely sufficient if mandatory tool action required)
        resp_lower = final_response.lower()
        keywords = [w for w in re.findall(r"\w+", crit_desc) if len(w) > 3]
        if keywords and all(kw in resp_lower for kw in keywords[:2]):
            evidence_found.append("Final response asserts criterion completion")
            if not steps:
                trajectory_evidence = True

        if evidence_found and (trajectory_evidence or not criterion.is_mandatory):
            status = CriterionStatus.SATISFIED
            evidence_str = "; ".join(evidence_found[:3])
        else:
            status = CriterionStatus.UNSATISFIED if steps else CriterionStatus.UNKNOWN
            evidence_str = (
                "; ".join(evidence_found)
                if evidence_found
                else "No confirming evidence found in execution trajectory"
            )

        return GoalCriterion(
            criterion_id=criterion.criterion_id,
            description=criterion.description,
            status=status,
            evidence=evidence_str,
            is_mandatory=criterion.is_mandatory,
        )

    def verify_goal(
        self,
        goal: Goal,
        steps: list[AgentStep],
        final_response: str = "",
    ) -> tuple[GoalVerification, list[AgentFailure], AgentStageScore]:
        """Audit complete goal achievement across criteria."""
        failures: list[AgentFailure] = []
        verified_criteria: list[GoalCriterion] = []

        # If goal has no explicit criteria, derive a default criterion from required_outcome or description
        criteria_to_check = goal.criteria
        if not criteria_to_check:
            desc = goal.required_outcome or goal.description
            criteria_to_check = [GoalCriterion(description=desc, is_mandatory=True)]

        for c in criteria_to_check:
            verified_c = self.verify_criterion(c, steps, final_response)
            verified_criteria.append(verified_c)

        satisfied_count = sum(
            1 for c in verified_criteria if c.status == CriterionStatus.SATISFIED
        )
        mandatory_satisfied = all(
            c.status == CriterionStatus.SATISFIED
            for c in verified_criteria
            if c.is_mandatory
        )
        total_criteria = len(verified_criteria)
        ratio = (
            float(satisfied_count) / float(total_criteria)
            if total_criteria > 0
            else 0.0
        )

        # Determine overall status
        if total_criteria == 0:
            overall_status = GoalStatus.UNKNOWN
        elif ratio == 1.0 and mandatory_satisfied:
            overall_status = GoalStatus.COMPLETED
        elif ratio >= self.partial_threshold or (
            satisfied_count > 0 and not mandatory_satisfied
        ):
            overall_status = GoalStatus.PARTIALLY_COMPLETED
            failures.append(
                AgentFailure(
                    stage=AgentStage.GOAL_VERIFICATION,
                    category=AgentFailureCategory.PARTIAL_COMPLETION,
                    severity=FailureSeverity.HIGH,
                    message=f"Goal '{goal.goal_id}' partially completed ({satisfied_count}/{total_criteria} criteria satisfied)",
                    affected_component=f"goal_{goal.goal_id}",
                    confidence=0.92,
                )
            )
        else:
            overall_status = GoalStatus.FAILED
            failures.append(
                AgentFailure(
                    stage=AgentStage.GOAL_VERIFICATION,
                    category=AgentFailureCategory.GOAL_NOT_ACHIEVED,
                    severity=FailureSeverity.CRITICAL,
                    message=f"Goal '{goal.goal_id}' failed: none of the required criteria were satisfied",
                    affected_component=f"goal_{goal.goal_id}",
                    confidence=0.95,
                )
            )

        # Check for premature termination: agent produced final response but failed goal
        if final_response and overall_status in (
            GoalStatus.FAILED,
            GoalStatus.PARTIALLY_COMPLETED,
        ):
            failures.append(
                AgentFailure(
                    stage=AgentStage.GOAL_VERIFICATION,
                    category=AgentFailureCategory.PREMATURE_TERMINATION,
                    severity=FailureSeverity.HIGH,
                    message=f"Agent produced final response despite incomplete goal '{goal.goal_id}'",
                    affected_component="agent_lifecycle",
                    confidence=0.94,
                )
            )

        # Score computation
        score = ratio if mandatory_satisfied else ratio * 0.5
        score = max(0.0, min(1.0, score))

        verification = GoalVerification(
            goal_id=goal.goal_id,
            overall_status=overall_status,
            completion_ratio=ratio,
            criteria_results=verified_criteria,
            explanation=f"Goal status: {overall_status.value} ({satisfied_count}/{total_criteria} criteria satisfied)",
            evidence=[c.evidence for c in verified_criteria if c.evidence],
        )

        stage_score = AgentStageScore(
            stage=AgentStage.GOAL_VERIFICATION,
            score=score,
            confidence=0.94,
            metrics={
                "completion_ratio": ratio,
                "satisfied_criteria": float(satisfied_count),
                "total_criteria": float(total_criteria),
            },
            failures=failures,
            explanation=verification.explanation,
        )

        return verification, failures, stage_score
