"""Task Decomposition and Subtask Dependency Graph Analyzer."""

from __future__ import annotations

from typing import Any

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
)
from aireliability.core.models import FailureSeverity


class TaskDecompositionAnalyzer:
    """Evaluates task decomposition into subtasks, detecting ordering, duplicates, and cyclic dependencies."""

    def analyze_decomposition(
        self,
        subtasks: list[str],
        dependencies: dict[str, list[str]] | None = None,
        expected_subtasks: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[AgentFailure], AgentStageScore]:
        """Validate decomposition for cycles, dependency violations, duplicates, and completeness."""
        failures: list[AgentFailure] = []
        deps = dependencies or {}
        is_valid = True

        # 1. Empty decomposition check
        if not subtasks:
            failures.append(
                AgentFailure(
                    stage=AgentStage.DECOMPOSITION,
                    category=AgentFailureCategory.DECOMPOSITION_FAILURE,
                    severity=FailureSeverity.CRITICAL,
                    message="DECOMPOSITION_FAILURE: Task contains zero decomposed subtasks.",
                    confidence=1.0,
                )
            )
            score_obj = AgentStageScore(
                stage=AgentStage.DECOMPOSITION,
                score=0.0,
                confidence=1.0,
                failures=failures,
                explanation="No subtasks provided in decomposition.",
            )
            return False, failures, score_obj

        # 2. Check duplicate subtasks
        seen: set[str] = set()
        duplicates: set[str] = set()
        for st in subtasks:
            norm = st.strip().lower()
            if norm in seen:
                duplicates.add(st)
            seen.add(norm)

        if duplicates:
            failures.append(
                AgentFailure(
                    stage=AgentStage.DECOMPOSITION,
                    category=AgentFailureCategory.DUPLICATE_SUBTASK,
                    severity=FailureSeverity.MEDIUM,
                    message=f"DUPLICATE_SUBTASK: Redundant subtasks detected: {sorted(duplicates)}.",
                    affected_component="subtask_planner",
                    confidence=0.95,
                )
            )

        # 3. Check for circular dependencies
        has_cycle, cycle_path = self._detect_cycle(subtasks, deps)
        if has_cycle:
            is_valid = False
            failures.append(
                AgentFailure(
                    stage=AgentStage.DECOMPOSITION,
                    category=AgentFailureCategory.CIRCULAR_DEPENDENCY,
                    severity=FailureSeverity.CRITICAL,
                    message=f"CIRCULAR_DEPENDENCY: Detected deadlocking cycle in subtask dependencies: {' -> '.join(cycle_path)}.",
                    affected_component="dependency_graph",
                    confidence=1.0,
                )
            )

        # 4. Check for dependency ordering violations
        # Each prerequisite must appear BEFORE the dependent subtask in sequence
        subtask_indices = {st.lower(): idx for idx, st in enumerate(subtasks)}
        order_violations = []

        for subtask, prereqs in deps.items():
            curr_idx = subtask_indices.get(subtask.lower())
            if curr_idx is None:
                continue
            for pre in prereqs:
                pre_idx = subtask_indices.get(pre.lower())
                if pre_idx is None:
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.DECOMPOSITION,
                            category=AgentFailureCategory.DEPENDENCY_VIOLATION,
                            severity=FailureSeverity.HIGH,
                            message=f"DEPENDENCY_VIOLATION: Subtask '{subtask}' requires missing prerequisite '{pre}'.",
                            affected_component=subtask,
                            confidence=0.95,
                        )
                    )
                    is_valid = False
                elif pre_idx >= curr_idx:
                    order_violations.append((pre, subtask))
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.DECOMPOSITION,
                            category=AgentFailureCategory.DEPENDENCY_VIOLATION,
                            severity=FailureSeverity.HIGH,
                            message=(
                                f"DEPENDENCY_VIOLATION: Subtask '{subtask}' scheduled at step {curr_idx + 1} "
                                f"before prerequisite '{pre}' at step {pre_idx + 1}."
                            ),
                            affected_component=subtask,
                            confidence=0.95,
                        )
                    )
                    is_valid = False

        # 5. Check against expected benchmark subtasks if provided
        if expected_subtasks:
            missing = [
                exp
                for exp in expected_subtasks
                if not any(exp.lower() in s.lower() for s in subtasks)
            ]
            if missing:
                failures.append(
                    AgentFailure(
                        stage=AgentStage.DECOMPOSITION,
                        category=AgentFailureCategory.MISSING_SUBTASK,
                        severity=FailureSeverity.HIGH,
                        message=f"MISSING_SUBTASK: Decomposition omitted required subtasks: {missing}.",
                        confidence=0.90,
                    )
                )

        score = 1.0
        if has_cycle:
            score -= 0.50
        if order_violations:
            score -= min(0.40, len(order_violations) * 0.20)
        if duplicates:
            score -= 0.15
        if not is_valid:
            score = min(score, 0.40)
        score = round(max(0.0, score), 2)

        stage_score = AgentStageScore(
            stage=AgentStage.DECOMPOSITION,
            score=score,
            confidence=0.95,
            metrics={
                "subtasks_count": float(len(subtasks)),
                "dependency_violations": float(len(order_violations)),
                "has_circular_dependency": 1.0 if has_cycle else 0.0,
            },
            failures=failures,
            explanation=(
                f"Decomposition validated {len(subtasks)} subtask(s). "
                f"Status: {'VALID' if is_valid else 'INVALID'}. Failures: {len(failures)}."
            ),
        )

        return is_valid, failures, stage_score

    def _detect_cycle(
        self, nodes: list[str], edges: dict[str, list[str]]
    ) -> tuple[bool, list[str]]:
        """Run DFS cycle detection returning (has_cycle, cycle_path)."""
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        parent: dict[str, str | None] = {}
        all_nodes = {n.lower() for n in nodes} | {k.lower() for k in edges}

        def dfs(curr: str, path: list[str]) -> tuple[bool, list[str]]:
            visited[curr] = 1
            for nxt in edges.get(curr, []) + edges.get(curr.lower(), []):
                nxt_lower = nxt.lower()
                if visited.get(nxt_lower, 0) == 1:
                    cycle = path + [nxt]
                    return True, cycle
                if visited.get(nxt_lower, 0) == 0:
                    parent[nxt_lower] = curr
                    found, c_path = dfs(nxt_lower, path + [nxt])
                    if found:
                        return True, c_path
            visited[curr] = 2
            return False, []

        for node in all_nodes:
            if visited.get(node, 0) == 0:
                found, path = dfs(node, [node])
                if found:
                    return True, path

        return False, []
