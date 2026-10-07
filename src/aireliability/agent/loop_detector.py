"""Deterministic Trajectory Loop Detector for Phase 40.

Detects repetitive tool calls, cyclic action sequences (e.g. A -> B -> A -> B),
and state oscillation using deterministic SHA-256 step fingerprints.
Classifies patterns into FINITE_RETRY, RECOVERABLE_LOOP, RUNAWAY_LOOP, and INFINITE_LOOP_RISK.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
    AgentStep,
    LoopClassification,
)
from aireliability.core.models import FailureSeverity


def compute_step_action_fingerprint(step: AgentStep) -> str:
    """Compute a deterministic SHA-256 fingerprint representing the core action of a step."""
    payload: dict[str, Any] = {
        "action_type": step.action_type.value,
        "tool_name": step.tool_call.tool_name if step.tool_call else "",
        "arguments": step.tool_call.arguments if step.tool_call else {},
        "action": step.action,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class LoopDetector:
    """Detects cycles, repeated actions, and runaway loops in trajectories in O(N) time."""

    def __init__(
        self,
        finite_retry_threshold: int = 2,
        runaway_loop_threshold: int = 4,
        cycle_window_size: int = 4,
    ) -> None:
        self.finite_retry_threshold = finite_retry_threshold
        self.runaway_loop_threshold = runaway_loop_threshold
        self.cycle_window_size = cycle_window_size

    def detect_loops(
        self,
        steps: list[AgentStep],
    ) -> tuple[LoopClassification, list[AgentFailure], AgentStageScore]:
        """Analyze trajectory step sequence for repetitive or cyclic patterns."""
        failures: list[AgentFailure] = []
        classification = LoopClassification.NO_LOOP

        if len(steps) < 2:
            return (
                LoopClassification.NO_LOOP,
                [],
                AgentStageScore(
                    stage=AgentStage.LOOP,
                    score=1.0,
                    confidence=1.0,
                    metrics={"loop_count": 0.0, "max_repetition": 0.0},
                    failures=[],
                    explanation="Trajectory too short for loops",
                ),
            )

        fingerprints = [compute_step_action_fingerprint(s) for s in steps]

        # 1. Check consecutive identical action repetitions
        max_consecutive = 1
        current_consecutive = 1
        repeat_fp = ""
        repeat_step_idx = 0

        for i in range(1, len(fingerprints)):
            if fingerprints[i] == fingerprints[i - 1]:
                current_consecutive += 1
                if current_consecutive > max_consecutive:
                    max_consecutive = current_consecutive
                    repeat_fp = fingerprints[i]
                    repeat_step_idx = steps[i].sequence
            else:
                current_consecutive = 1

        # 2. Check 2-step oscillating cycles (A -> B -> A -> B ...)
        cycle_count = 0
        if len(fingerprints) >= 4:
            for i in range(len(fingerprints) - 3):
                if (
                    fingerprints[i] == fingerprints[i + 2]
                    and fingerprints[i + 1] == fingerprints[i + 3]
                    and fingerprints[i] != fingerprints[i + 1]
                ):
                    cycle_count += 1

        # 3. Frequency count
        counts = Counter(fingerprints)
        most_common_fp, most_common_cnt = counts.most_common(1)[0]

        # Determine classification
        if max_consecutive >= self.runaway_loop_threshold or cycle_count >= 3:
            classification = LoopClassification.RUNAWAY_LOOP
            failures.append(
                AgentFailure(
                    stage=AgentStage.LOOP,
                    category=AgentFailureCategory.RUNAWAY_LOOP,
                    severity=FailureSeverity.CRITICAL,
                    message=(
                        f"Detected runaway loop: {max_consecutive} consecutive identical actions "
                        f"or {cycle_count} alternating cycles at step {repeat_step_idx}"
                    ),
                    affected_component="trajectory_executor",
                    step_index=repeat_step_idx,
                    confidence=0.98,
                    metadata={"consecutive": max_consecutive, "cycles": cycle_count},
                )
            )
        elif cycle_count >= 1 or most_common_cnt > self.finite_retry_threshold + 1:
            # Check if trajectory recovered after the cycle
            last_is_loop = (
                fingerprints[-1] == repeat_fp or fingerprints[-1] == fingerprints[-2]
            )
            if last_is_loop:
                classification = LoopClassification.INFINITE_LOOP_RISK
                failures.append(
                    AgentFailure(
                        stage=AgentStage.LOOP,
                        category=AgentFailureCategory.INFINITE_LOOP_RISK,
                        severity=FailureSeverity.HIGH,
                        message=f"Risk of infinite loop detected: oscillating actions with no termination at step {repeat_step_idx}",
                        affected_component="trajectory_executor",
                        step_index=repeat_step_idx,
                        confidence=0.90,
                    )
                )
            else:
                classification = LoopClassification.RECOVERABLE_LOOP
                failures.append(
                    AgentFailure(
                        stage=AgentStage.LOOP,
                        category=AgentFailureCategory.RECOVERABLE_LOOP,
                        severity=FailureSeverity.MEDIUM,
                        message=f"Recoverable loop detected: repeated action pattern broken after {most_common_cnt} occurrences",
                        affected_component="trajectory_executor",
                        step_index=repeat_step_idx,
                        confidence=0.85,
                    )
                )
        elif max_consecutive == self.finite_retry_threshold:
            classification = LoopClassification.FINITE_RETRY
            # Finite retry is typically benign or low severity
            failures.append(
                AgentFailure(
                    stage=AgentStage.LOOP,
                    category=AgentFailureCategory.LOOP_FAILURE,
                    severity=FailureSeverity.LOW,
                    message=f"Finite retry observed: 2 consecutive identical actions at step {repeat_step_idx}",
                    affected_component="trajectory_executor",
                    step_index=repeat_step_idx,
                    confidence=0.80,
                )
            )
        else:
            classification = LoopClassification.NO_LOOP

        # Score computation
        if classification == LoopClassification.RUNAWAY_LOOP:
            score = 0.0
        elif classification == LoopClassification.INFINITE_LOOP_RISK:
            score = 0.30
        elif classification == LoopClassification.RECOVERABLE_LOOP:
            score = 0.70
        elif classification == LoopClassification.FINITE_RETRY:
            score = 0.90
        else:
            score = 1.0

        stage_score = AgentStageScore(
            stage=AgentStage.LOOP,
            score=score,
            confidence=0.95,
            metrics={
                "loop_score": score,
                "max_consecutive": float(max_consecutive),
                "cycle_count": float(cycle_count),
            },
            failures=failures,
            explanation=f"Loop classification: {classification.value}",
        )

        return classification, failures, stage_score
