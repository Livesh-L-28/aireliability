"""Retry Efficacy and Storm Analyzer for Phase 40.

Analyzes retry attempts across trajectories, separating productive retries
(e.g., temporary network timeout -> backoff -> success) from redundant retries
(e.g., repeating identical invalid arguments) and retry storms.
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


class RetryAnalyzer:
    """Evaluates retry behavior, recovery rates, and redundant retry storms."""

    def __init__(self, storm_threshold: int = 3) -> None:
        self.storm_threshold = storm_threshold

    def analyze_retries(
        self,
        steps: list[AgentStep],
    ) -> tuple[list[AgentFailure], AgentStageScore]:
        """Audit all retry patterns in the trajectory."""
        failures: list[AgentFailure] = []

        total_retries = 0
        successful_retries = 0
        redundant_retries = 0

        # Scan for retries: consecutive tool calls to the same tool following a failure
        i = 1
        consecutive_tool_fails = 0

        while i < len(steps):
            prev_step = steps[i - 1]
            curr_step = steps[i]

            prev_tool = prev_step.tool_call
            prev_result = prev_step.tool_result
            curr_tool = curr_step.tool_call
            curr_result = curr_step.tool_result

            # Check if previous was a tool failure and current is calling same tool
            if (
                prev_tool is not None
                and prev_result is not None
                and not prev_result.success
                and curr_tool is not None
                and curr_tool.tool_name == prev_tool.tool_name
            ):
                total_retries += 1

                # Check if arguments were identical
                identical_args = curr_tool.arguments == prev_tool.arguments

                if identical_args and not (curr_result and curr_result.success):
                    # Redundant retry with unchanged arguments that also failed
                    redundant_retries += 1
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.RETRY,
                            category=AgentFailureCategory.REDUNDANT_RETRY,
                            severity=FailureSeverity.MEDIUM,
                            message=(
                                f"Redundant retry on tool '{curr_tool.tool_name}' at step {curr_step.sequence} "
                                f"with identical failing arguments without correction"
                            ),
                            affected_component=curr_tool.tool_name,
                            step_index=curr_step.sequence,
                            confidence=0.92,
                        )
                    )

                if curr_result and curr_result.success:
                    successful_retries += 1
                    consecutive_tool_fails = 0
                else:
                    consecutive_tool_fails += 1
                    if consecutive_tool_fails >= self.storm_threshold:
                        failures.append(
                            AgentFailure(
                                stage=AgentStage.RETRY,
                                category=AgentFailureCategory.RETRY_STORM,
                                severity=FailureSeverity.HIGH,
                                message=(
                                    f"Retry storm on tool '{curr_tool.tool_name}': "
                                    f"{consecutive_tool_fails} failed consecutive retry attempts"
                                ),
                                affected_component=curr_tool.tool_name,
                                step_index=curr_step.sequence,
                                confidence=0.95,
                            )
                        )
            else:
                consecutive_tool_fails = 0

            i += 1

        recovery_rate = (
            float(successful_retries) / float(total_retries)
            if total_retries > 0
            else 1.0
        )
        redundant_retry_rate = (
            float(redundant_retries) / float(total_retries)
            if total_retries > 0
            else 0.0
        )

        # Score calculation
        score = 1.0
        if total_retries > 0:
            # Score penalizes redundant retries heavily, rewards recovery
            score = max(0.0, recovery_rate - (redundant_retry_rate * 0.5))

        stage_score = AgentStageScore(
            stage=AgentStage.RETRY,
            score=min(1.0, score),
            confidence=0.92,
            metrics={
                "retry_count": float(total_retries),
                "recovery_rate": float(recovery_rate),
                "redundant_retry_rate": float(redundant_retry_rate),
            },
            failures=failures,
            explanation=(
                f"Retries analyzed: {total_retries} total, {successful_retries} recovered, {redundant_retries} redundant"
                if total_retries > 0
                else "No retries needed in trajectory"
            ),
        )

        return failures, stage_score
