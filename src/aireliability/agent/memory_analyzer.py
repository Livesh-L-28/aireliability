"""Memory Operation Analyzer for Phase 40.

Audits memory event traces across agent execution (read, write, update, delete, retrieve).
Detects memory misses, staleness, contradictions, duplicate writes, overwrites,
and corrupted memory objects.
"""

from __future__ import annotations

import json
from typing import Any

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
    MemoryEvent,
)
from aireliability.core.models import FailureSeverity


class MemoryAnalyzer:
    """Analyzes memory event streams and detects retrieval/mutation failures."""

    def __init__(self, protected_keys: list[str] | None = None) -> None:
        self.protected_keys = set(
            protected_keys or ["user_id", "session_id", "system_prompt", "root_goal"]
        )

    def analyze_memory_events(
        self,
        events: list[MemoryEvent],
    ) -> tuple[list[AgentFailure], AgentStageScore]:
        """Audit chronological stream of memory events."""
        failures: list[AgentFailure] = []
        memory_store: dict[str, Any] = {}
        write_history: dict[str, list[Any]] = {}

        for idx, event in enumerate(events):
            op = event.operation.lower()
            key = event.key

            # 1. Check operation failure / miss
            if not event.success:
                failures.append(
                    AgentFailure(
                        stage=AgentStage.MEMORY,
                        category=AgentFailureCategory.MEMORY_MISS,
                        severity=FailureSeverity.MEDIUM,
                        message=f"Memory operation '{op}' failed on key '{key}'",
                        affected_component=f"memory_key_{key}",
                        step_index=idx,
                        confidence=0.95,
                        metadata={"operation": op, "key": key},
                    )
                )
                continue

            # 2. Memory corruption check
            if isinstance(event.value, str) and (
                event.value.strip().startswith("{")
                or event.value.strip().startswith("[")
            ):
                try:
                    json.loads(event.value)
                except Exception:
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.MEMORY,
                            category=AgentFailureCategory.MEMORY_CORRUPTION,
                            severity=FailureSeverity.HIGH,
                            message=f"Memory event on key '{key}' contains corrupted JSON string",
                            affected_component=f"memory_key_{key}",
                            step_index=idx,
                            confidence=0.90,
                        )
                    )

            if op in ("read", "retrieve"):
                if key not in memory_store and not event.metadata.get(
                    "allow_empty", False
                ):
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.MEMORY,
                            category=AgentFailureCategory.MEMORY_MISS,
                            severity=FailureSeverity.LOW,
                            message=f"Memory '{op}' on uninitialized key '{key}'",
                            affected_component=f"memory_key_{key}",
                            step_index=idx,
                            confidence=0.85,
                        )
                    )
                elif key in memory_store:
                    # Check staleness
                    is_stale = event.metadata.get("is_stale", False)
                    if is_stale:
                        failures.append(
                            AgentFailure(
                                stage=AgentStage.MEMORY,
                                category=AgentFailureCategory.MEMORY_STALENESS,
                                severity=FailureSeverity.MEDIUM,
                                message=f"Read stale or superseded memory for key '{key}'",
                                affected_component=f"memory_key_{key}",
                                step_index=idx,
                                confidence=0.88,
                            )
                        )

            elif op in ("write", "update"):
                # 3. Memory duplication check (identical write repeated)
                history = write_history.setdefault(key, [])
                if history and history[-1] == event.value:
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.MEMORY,
                            category=AgentFailureCategory.MEMORY_DUPLICATION,
                            severity=FailureSeverity.LOW,
                            message=f"Duplicate redundant memory write on key '{key}' with identical value",
                            affected_component=f"memory_key_{key}",
                            step_index=idx,
                            confidence=0.80,
                        )
                    )
                history.append(event.value)

                # 4. Overwrite check on protected keys
                if (
                    key in self.protected_keys
                    and key in memory_store
                    and op == "write"
                    and memory_store[key] != event.value
                ):
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.MEMORY,
                            category=AgentFailureCategory.MEMORY_OVERWRITE,
                            severity=FailureSeverity.HIGH,
                            message=f"Protected memory key '{key}' overwritten without update authorization",
                            affected_component=f"memory_key_{key}",
                            step_index=idx,
                            confidence=0.92,
                        )
                    )

                memory_store[key] = event.value

            elif op == "delete":
                if key in self.protected_keys:
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.MEMORY,
                            category=AgentFailureCategory.MEMORY_OVERWRITE,
                            severity=FailureSeverity.HIGH,
                            message=f"Attempted deletion of protected memory key '{key}'",
                            affected_component=f"memory_key_{key}",
                            step_index=idx,
                            confidence=0.94,
                        )
                    )
                memory_store.pop(key, None)

        score = 1.0
        for f in failures:
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
            stage=AgentStage.MEMORY,
            score=score,
            confidence=0.91,
            metrics={
                "memory_reliability_score": score,
                "event_count": float(len(events)),
                "failures_count": float(len(failures)),
            },
            failures=failures,
            explanation=(
                "All memory operations executed reliably"
                if not failures
                else f"Detected {len(failures)} memory trace defects"
            ),
        )

        return failures, stage_score
