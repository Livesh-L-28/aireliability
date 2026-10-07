"""Task Understanding and Ambiguity Analyzer for autonomous agents."""

from __future__ import annotations

import re
from typing import Any

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
    AgentTask,
    Goal,
    GoalCriterion,
)
from aireliability.core.models import FailureSeverity

# Common constraint indicator words
CONSTRAINT_KEYWORDS = [
    "must",
    "must not",
    "cannot",
    "should not",
    "never",
    "only",
    "within",
    "limit",
    "at most",
    "at least",
    "before",
    "after",
    "under",
    "restricted",
    "required",
]

# Ambiguity indicator patterns
AMBIGUITY_PATTERNS = [
    re.compile(
        r"\b(maybe|perhaps|somehow|etc|and so on|as appropriate|roughly|whenever)\b",
        re.I,
    ),
    re.compile(r"\b(good|better|fast|clean|nice|proper)\b", re.I),
]


class TaskAnalyzer:
    """Analyzes incoming task specifications, extracting objectives, constraints, and ambiguity."""

    def __init__(self, ambiguity_threshold: float = 0.60) -> None:
        self.ambiguity_threshold = ambiguity_threshold

    def analyze_task(
        self,
        request_text: str,
        expected_constraints: list[str] | None = None,
        expected_goals: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AgentTask, list[AgentFailure], AgentStageScore]:
        """Analyze task request text, extracting objectives and detecting comprehension defects."""
        failures: list[AgentFailure] = []
        text = request_text.strip()

        if not text:
            fail = AgentFailure(
                stage=AgentStage.TASK_ANALYSIS,
                category=AgentFailureCategory.TASK_UNDERSTANDING_FAILURE,
                severity=FailureSeverity.CRITICAL,
                message="TASK_UNDERSTANDING_FAILURE: Received empty task request.",
                confidence=1.0,
            )
            failures.append(fail)
            task = AgentTask(
                request_text="",
                ambiguity_score=1.0,
                completeness_score=0.0,
            )
            stage_score = AgentStageScore(
                stage=AgentStage.TASK_ANALYSIS,
                score=0.0,
                failures=failures,
                explanation="Empty request provided.",
            )
            return task, failures, stage_score

        # 1. Extract objectives & sentences
        sentences = [
            s.strip() for s in re.split(r"[.!?\n]+", text) if len(s.strip()) > 3
        ]
        objectives: list[str] = []
        for s in sentences:
            if re.search(
                r"\b(find|search|calculate|send|refund|create|delete|update|analyze|deploy|train|fetch)\b",
                s,
                re.I,
            ):
                objectives.append(s)
        if not objectives and sentences:
            objectives.append(sentences[0])

        # 2. Extract constraints
        extracted_constraints: list[str] = []
        for s in sentences:
            if any(kw in s.lower() for kw in CONSTRAINT_KEYWORDS):
                extracted_constraints.append(s)

        # 3. Compute ambiguity score
        ambiguity_hits = sum(len(pat.findall(text)) for pat in AMBIGUITY_PATTERNS)
        token_count = max(1, len(text.split()))
        ambiguity_score = round(min(1.0, ambiguity_hits / (token_count * 0.15)), 2)

        # 4. Completeness score
        has_action = len(objectives) > 0
        has_target = bool(
            re.search(
                r"\b(order|user|model|file|data|email|server|customer|account|database)\b",
                text,
                re.I,
            )
        )
        completeness_score = 0.5
        if has_action:
            completeness_score += 0.3
        if has_target:
            completeness_score += 0.2
        completeness_score = round(min(1.0, completeness_score), 2)

        # 5. Check against expected benchmark constraints & goals if provided
        if expected_constraints:
            for exp_c in expected_constraints:
                found = any(
                    exp_c.lower() in ec.lower() or ec.lower() in exp_c.lower()
                    for ec in extracted_constraints
                )
                if not found and exp_c.lower() not in text.lower():
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.TASK_ANALYSIS,
                            category=AgentFailureCategory.MISSING_CONSTRAINT,
                            severity=FailureSeverity.HIGH,
                            message=f"MISSING_CONSTRAINT: Task specification omitted critical constraint '{exp_c}'.",
                            affected_component="task_specification",
                            confidence=0.95,
                        )
                    )

        if expected_goals:
            for exp_g in expected_goals:
                found = any(exp_g.lower() in obj.lower() for obj in objectives)
                if not found and exp_g.lower() not in text.lower():
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.TASK_ANALYSIS,
                            category=AgentFailureCategory.MISINTERPRETED_GOAL,
                            severity=FailureSeverity.HIGH,
                            message=f"MISINTERPRETED_GOAL: Target goal '{exp_g}' not recognized in task understanding.",
                            affected_component="goal_formulation",
                            confidence=0.90,
                        )
                    )

        # Check excessive ambiguity
        if ambiguity_score > self.ambiguity_threshold:
            failures.append(
                AgentFailure(
                    stage=AgentStage.TASK_ANALYSIS,
                    category=AgentFailureCategory.TASK_UNDERSTANDING_FAILURE,
                    severity=FailureSeverity.MEDIUM,
                    message=f"TASK_AMBIGUITY_HIGH: Ambiguity score {ambiguity_score:.2f} exceeds threshold {self.ambiguity_threshold:.2f}.",
                    confidence=0.85,
                )
            )

        goals = [
            Goal(
                description=obj,
                criteria=[GoalCriterion(description=f"Complete: {obj}")],
            )
            for obj in objectives
        ]

        task = AgentTask(
            request_text=text,
            goals=goals,
            constraints=extracted_constraints,
            extracted_objectives=objectives,
            ambiguity_score=ambiguity_score,
            completeness_score=completeness_score,
            metadata=metadata or {},
        )

        score = round(max(0.0, completeness_score * (1.0 - 0.5 * ambiguity_score)), 2)
        if any(f.severity == FailureSeverity.CRITICAL for f in failures):
            score = min(score, 0.20)

        stage_score = AgentStageScore(
            stage=AgentStage.TASK_ANALYSIS,
            score=score,
            confidence=0.95,
            metrics={
                "ambiguity_score": ambiguity_score,
                "completeness_score": completeness_score,
                "extracted_objectives_count": float(len(objectives)),
                "extracted_constraints_count": float(len(extracted_constraints)),
            },
            failures=failures,
            explanation=(
                f"Task completeness: {completeness_score:.2f}, Ambiguity: {ambiguity_score:.2f}, "
                f"Extracted {len(objectives)} objective(s) and {len(extracted_constraints)} constraint(s)."
            ),
        )

        return task, failures, stage_score
