"""Comprehensive agent and trajectory evaluator."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    TestCase,
)
from aireliability.evaluation.agents.tools import ToolUsageEvaluator
from aireliability.evaluation.agents.trajectory import TrajectoryEvaluator
from aireliability.evaluation.expectations import BaseExpectation


class AgentEvaluator(BaseExpectation):
    """End-to-end autonomous agent evaluator assessing task completion, tool metrics, and trajectory."""

    def __init__(
        self,
        *,
        required_tools: list[str] | None = None,
        forbidden_tools: list[str] | None = None,
        max_steps: int = 15,
        max_loops: int = 0,
        name: str | None = None,
        **metadata: Any,
    ) -> None:
        super().__init__(name=name or "AgentEvaluator", **metadata)
        self.tool_eval = ToolUsageEvaluator(
            required_tools=required_tools,
            forbidden_tools=forbidden_tools,
            **metadata,
        )
        self.trajectory_eval = TrajectoryEvaluator(
            max_steps=max_steps,
            max_allowed_loops=max_loops,
            **metadata,
        )

    def evaluate(
        self,
        trace: ExecutionTrace,
        test_case: TestCase | None = None,
    ) -> EvaluationResult:
        # Check trace status
        task_completed = (trace.status != ExecutionStatus.FAILED) and (
            trace.output is not None or len(trace.steps) > 0
        )

        res_tools = self.tool_eval.evaluate(trace, test_case)
        res_traj = self.trajectory_eval.evaluate(trace, test_case)

        passed = task_completed and res_tools.passed and res_traj.passed

        # Composite agent score: 40% task completion, 30% tools, 30% trajectory
        task_score = 1.0 if task_completed else 0.0
        score = round(
            (task_score * 0.40)
            + ((res_tools.score or 0.0) * 0.30)
            + ((res_traj.score or 0.0) * 0.30),
            4,
        )

        msg = (
            f"Agent completed task with score {score:.2f} (Tools: {res_tools.score:.2f}, "
            f"Trajectory: {res_traj.score:.2f})."
            if passed
            else f"Agent evaluation FAILED: task_completed={task_completed}, "
            f"tools_passed={res_tools.passed}, trajectory_passed={res_traj.passed}."
        )

        evidence = {
            "task_completed": task_completed,
            "tool_success_rate": res_tools.evidence.get("tool_success_rate", 1.0),
            "tool_error_rate": res_tools.evidence.get("tool_error_rate", 0.0),
            "loop_count": res_traj.evidence.get("loop_count", 0),
            "retry_count": res_traj.evidence.get("retry_count", 0),
            "total_steps": res_traj.evidence.get("total_steps", 0),
            "tool_evidence": res_tools.evidence,
            "trajectory_evidence": res_traj.evidence,
        }

        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            metric="agent_success_rate",
            threshold=0.80,
            confidence=1.0,
            message=msg,
            evidence=evidence,
            metadata={
                **self.metadata,
                "failure_category": "task"
                if not task_completed
                else res_tools.metadata.get("failure_category", "tool"),
                "failure_type": "task_incomplete"
                if not task_completed
                else res_tools.metadata.get("failure_type", "task_incomplete"),
                **evidence,
            },
        )
