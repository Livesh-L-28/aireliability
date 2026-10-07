"""Agent State Transition Tracker and Integrity Evaluator for Phase 40.

Tracks discrete transitions: state_before -> action -> observation -> state_after.
Detects invalid transitions, missing state updates, stale state, overwrites,
and corrupt state variables using deterministic SHA-256 state fingerprints.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
    AgentState,
    AgentStep,
)
from aireliability.core.models import FailureSeverity


def compute_state_fingerprint(variables: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 fingerprint for state variables."""
    try:
        canonical_json = json.dumps(variables, sort_keys=True, default=str)
    except Exception:
        canonical_json = str(sorted(variables.items()))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]


class StateTracker:
    """Tracks state transitions across steps and detects state corruption or anomalies."""

    def __init__(
        self, allowed_status_transitions: dict[str, list[str]] | None = None
    ) -> None:
        # Default allowed state machine transitions
        self.allowed_transitions = allowed_status_transitions or {
            "active": [
                "active",
                "waiting",
                "replanning",
                "completed",
                "failed",
                "blocked",
            ],
            "waiting": ["active", "waiting", "completed", "failed"],
            "replanning": ["active", "replanning", "failed"],
            "completed": ["completed"],
            "failed": ["failed"],
            "blocked": ["active", "failed", "blocked"],
        }

    def evaluate_step_transition(
        self,
        step: AgentStep,
        previous_state: AgentState | None = None,
    ) -> list[AgentFailure]:
        """Evaluate state transition for a discrete step."""
        failures: list[AgentFailure] = []

        before = step.state_before or previous_state
        after = step.state_after

        # 1. Missing state update: if step resulted in stateful tool result or observation, but after is None
        if before is not None and after is None and step.tool_result is not None:
            failures.append(
                AgentFailure(
                    stage=AgentStage.STATE,
                    category=AgentFailureCategory.MISSING_STATE_UPDATE,
                    severity=FailureSeverity.MEDIUM,
                    message=f"Step {step.sequence} executed tool '{step.tool_result.tool_name}' but state_after is missing",
                    affected_component="state_manager",
                    step_index=step.sequence,
                    confidence=0.85,
                )
            )
            return failures

        if before is None or after is None:
            return failures

        # 2. Invalid status transition check
        before_status = before.status.lower()
        after_status = after.status.lower()
        allowed_next = self.allowed_transitions.get(before_status, [])
        if allowed_next and after_status not in allowed_next:
            failures.append(
                AgentFailure(
                    stage=AgentStage.STATE,
                    category=AgentFailureCategory.INVALID_STATE_TRANSITION,
                    severity=FailureSeverity.HIGH,
                    message=f"Invalid state transition from '{before_status}' to '{after_status}' at step {step.sequence}",
                    affected_component="state_machine",
                    step_index=step.sequence,
                    confidence=0.92,
                    metadata={"from_status": before_status, "to_status": after_status},
                )
            )

        # 3. Overwritten state: previously present essential keys suddenly removed
        before_keys = set(before.variables.keys())
        after_keys = set(after.variables.keys())
        removed_keys = before_keys - after_keys
        if removed_keys:
            failures.append(
                AgentFailure(
                    stage=AgentStage.STATE,
                    category=AgentFailureCategory.OVERWRITTEN_STATE,
                    severity=FailureSeverity.HIGH,
                    message=f"State variables dropped without explicit cleanup at step {step.sequence}: {', '.join(sorted(removed_keys))}",
                    affected_component="state_variables",
                    step_index=step.sequence,
                    confidence=0.88,
                    metadata={"removed_keys": sorted(removed_keys)},
                )
            )

        # 4. Inconsistent state: type changes for existing variables
        for key in before_keys.intersection(after_keys):
            val_before = before.variables[key]
            val_after = after.variables[key]
            if (
                val_before is not None
                and val_after is not None
                and type(val_before) is not type(val_after)
            ):
                failures.append(
                    AgentFailure(
                        stage=AgentStage.STATE,
                        category=AgentFailureCategory.INCONSISTENT_STATE,
                        severity=FailureSeverity.MEDIUM,
                        message=(
                            f"Variable '{key}' changed type from {type(val_before).__name__} "
                            f"to {type(val_after).__name__} at step {step.sequence}"
                        ),
                        affected_component=f"state_var_{key}",
                        step_index=step.sequence,
                        confidence=0.82,
                    )
                )

        # 5. Stale state: fingerprint unchanged despite a successful state-modifying action
        fp_before = before.fingerprint or compute_state_fingerprint(before.variables)
        fp_after = after.fingerprint or compute_state_fingerprint(after.variables)
        if (
            step.action_type.value in ("state_update", "memory_op")
            and fp_before == fp_after
        ):
            failures.append(
                AgentFailure(
                    stage=AgentStage.STATE,
                    category=AgentFailureCategory.STALE_STATE,
                    severity=FailureSeverity.LOW,
                    message=f"Action '{step.action}' did not update state variables at step {step.sequence}",
                    affected_component="state_variables",
                    step_index=step.sequence,
                    confidence=0.75,
                )
            )

        return failures

    def evaluate_trajectory_states(
        self,
        steps: list[AgentStep],
    ) -> tuple[list[AgentFailure], AgentStageScore]:
        """Audit all state transitions across a complete trajectory."""
        all_failures: list[AgentFailure] = []
        prev_state: AgentState | None = None

        for step in sorted(steps, key=lambda s: s.sequence):
            step_failures = self.evaluate_step_transition(
                step, previous_state=prev_state
            )
            all_failures.extend(step_failures)
            prev_state = step.state_after or step.state_before or prev_state

        score = 1.0
        for f in all_failures:
            if f.severity == FailureSeverity.CRITICAL:
                score -= 0.50
            elif f.severity == FailureSeverity.HIGH:
                score -= 0.25
            elif f.severity == FailureSeverity.MEDIUM:
                score -= 0.10
            else:
                score -= 0.05
        score = max(0.0, min(1.0, score))

        stage_score = AgentStageScore(
            stage=AgentStage.STATE,
            score=score,
            confidence=0.90,
            metrics={
                "state_consistency_score": score,
                "transition_count": float(len(steps)),
                "failures_count": float(len(all_failures)),
            },
            failures=all_failures,
            explanation=(
                "All state transitions valid and consistent"
                if not all_failures
                else f"Detected {len(all_failures)} state transition anomalies"
            ),
        )

        return all_failures, stage_score
