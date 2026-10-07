"""Unit tests for State Tracking and Memory Reliability in Phase 40."""

from __future__ import annotations

from aireliability.agent.memory_analyzer import MemoryAnalyzer
from aireliability.agent.models import (
    ActionType,
    AgentFailureCategory,
    AgentState,
    AgentStep,
    MemoryEvent,
)
from aireliability.agent.state_tracker import StateTracker


def test_state_tracker_valid_transitions():
    """Verify clean state transitions without anomalies."""
    tracker = StateTracker()
    s1 = AgentState(variables={"count": 1}, status="active")
    s2 = AgentState(variables={"count": 2}, status="active")
    step = AgentStep(
        sequence=1,
        action="increment",
        action_type=ActionType.STATE_UPDATE,
        state_before=s1,
        state_after=s2,
    )
    fails = tracker.evaluate_step_transition(step)
    assert len(fails) == 0


def test_state_tracker_invalid_transition():
    """Verify state machine checks flag invalid transitions."""
    tracker = StateTracker()
    s1 = AgentState(variables={}, status="completed")
    s2 = AgentState(
        variables={}, status="active"
    )  # completed cannot transition back to active
    step = AgentStep(
        sequence=1,
        action="resume",
        state_before=s1,
        state_after=s2,
    )
    fails = tracker.evaluate_step_transition(step)
    assert any(
        f.category == AgentFailureCategory.INVALID_STATE_TRANSITION for f in fails
    )


def test_state_tracker_overwritten_and_inconsistent_variables():
    """Verify dropped variables and type mutations are flagged."""
    tracker = StateTracker()
    s1 = AgentState(variables={"auth_token": "secret_abc", "user_id": 100})
    # auth_token dropped, user_id changed type from int to string
    s2 = AgentState(variables={"user_id": "100_string"})
    step = AgentStep(sequence=1, action="update", state_before=s1, state_after=s2)
    fails = tracker.evaluate_step_transition(step)

    assert any(f.category == AgentFailureCategory.OVERWRITTEN_STATE for f in fails)
    assert any(f.category == AgentFailureCategory.INCONSISTENT_STATE for f in fails)


def test_memory_analyzer_operations():
    """Verify memory operations audit: misses, duplicates, and protected key overwrites."""
    analyzer = MemoryAnalyzer(protected_keys=["session_id", "root_goal"])

    events = [
        # 1. Uninitialized read -> miss
        MemoryEvent(operation="read", key="non_existent", value=None),
        # 2. Write protected key
        MemoryEvent(operation="write", key="session_id", value="sess_1"),
        # 3. Unauthorized overwrite on protected key
        MemoryEvent(operation="write", key="session_id", value="sess_2"),
        # 4. Duplicate redundant write
        MemoryEvent(operation="write", key="counter", value=1),
        MemoryEvent(operation="write", key="counter", value=1),
    ]

    fails, score = analyzer.analyze_memory_events(events)

    assert any(f.category == AgentFailureCategory.MEMORY_MISS for f in fails)
    assert any(f.category == AgentFailureCategory.MEMORY_OVERWRITE for f in fails)
    assert any(f.category == AgentFailureCategory.MEMORY_DUPLICATION for f in fails)
    assert score.score < 1.0


def test_memory_analyzer_corrupted_json():
    """Verify corrupted JSON value is flagged."""
    analyzer = MemoryAnalyzer()
    event = MemoryEvent(
        operation="write", key="profile", value="{malformed: json, missing quotes"
    )
    fails, score = analyzer.analyze_memory_events([event])
    assert any(f.category == AgentFailureCategory.MEMORY_CORRUPTION for f in fails)
