"""Controlled autonomous AI Agent supporting deterministic failure scenarios."""

from __future__ import annotations

from uuid import uuid4

from aireliability.agent.models import (
    ActionType,
    AgentFailure,
    AgentFailureCategory,
    AgentPlan,
    AgentRun,
    AgentStage,
    AgentStep,
    AgentTask,
    AgentTrajectory,
    CriterionStatus,
    Goal,
    GoalCriterion,
    GoalStatus,
    GoalVerification,
    Observation,
    ToolCall,
    ToolResult,
    ToolRiskLevel,
)
from aireliability.core.models import FailureSeverity
from aireliability_demo.app.agent.state import AgentState
from aireliability_demo.app.agent.tools import DEMO_TOOL_REGISTRY


class ControlledAgent:
    """Demonstration autonomous AI agent with deterministic planning, execution, and scenario control."""

    def __init__(self, name: str = "DemoAgent") -> None:
        self.name = name

    def execute_task(
        self,
        task_text: str,
        scenario: str = "NORMAL_AGENT",
        task_id: str | None = None,
        constraints: list[str] | None = None,
    ) -> AgentRun:
        """Execute task through planning, tool selection, execution, and verification."""
        t_id = task_id or f"task_{uuid4().hex[:8]}"
        scenario_upper = scenario.upper()
        state = AgentState(task_id=t_id)

        # 1. TASK CREATION
        goals = [
            Goal(
                goal_id=f"g_{t_id}",
                description=f"Complete user request: {task_text[:60]}",
                criteria=[
                    GoalCriterion(
                        criterion_id="crit_exec",
                        description="Execute required tool operations",
                        is_mandatory=True,
                    ),
                    GoalCriterion(
                        criterion_id="crit_goal",
                        description="Fulfill primary user intent",
                        is_mandatory=True,
                    ),
                ],
            )
        ]
        agent_task = AgentTask(
            task_id=t_id,
            request_text=task_text,
            constraints=constraints
            or ["never leak credentials", "verify math results"],
            goals=goals,
        )

        # 2. PLAN CREATION
        plan_steps = [
            "Analyze request",
            "Select and invoke tool",
            "Synthesize findings",
        ]
        plan = AgentPlan(
            plan_id=f"plan_{t_id}",
            steps=plan_steps,
            dependencies={"Select and invoke tool": ["Analyze request"]},
            estimated_cost=0.01,
        )

        steps: list[AgentStep] = []
        failures: list[AgentFailure] = []

        # 3. TRAJECTORY GENERATION BY SCENARIO
        if scenario_upper == "RUNAWAY_LOOP":
            # Generate 4 consecutive identical tool calls
            for i in range(1, 5):
                t_call = ToolCall(
                    tool_name="status_lookup",
                    arguments={"component": "evaluation"},
                    risk_level=ToolRiskLevel.LOW,
                )
                t_res = ToolResult(
                    call_id=f"c_{i}",
                    tool_name="status_lookup",
                    output="COMPONENT_STATUS: {'status': 'HEALTHY'}",
                    latency_ms=10.0,
                )
                obs = Observation(
                    source="tool",
                    raw_data={"loop_step": i},
                    interpreted_content="Status is healthy",
                )
                step = AgentStep(
                    sequence=i,
                    action="status_lookup",
                    action_type=ActionType.TOOL_CALL,
                    tool_call=t_call,
                    tool_result=t_res,
                    observation=obs,
                )
                steps.append(step)

        elif scenario_upper == "RETRY_LOOP":
            # 2 consecutive identical failing tool calls
            for i in range(1, 3):
                t_call = ToolCall(
                    tool_name="calculator",
                    arguments={"expression": "10 / 0"},
                    risk_level=ToolRiskLevel.LOW,
                )
                t_res = ToolResult(
                    call_id=f"c_{i}",
                    tool_name="calculator",
                    output="CALCULATION_ERROR: division by zero",
                    is_error=True,
                    error_message="division by zero",
                )
                obs = Observation(
                    source="tool",
                    raw_data={"error": "division by zero"},
                    interpreted_content="Error during calculation",
                    is_safe=True,
                )
                step = AgentStep(
                    sequence=i,
                    action="calculator",
                    action_type=ActionType.TOOL_CALL,
                    tool_call=t_call,
                    tool_result=t_res,
                    observation=obs,
                )
                steps.append(step)

        elif scenario_upper == "WRONG_TOOL":
            # Requested math calculation, but called knowledge_search instead
            t_call = ToolCall(
                tool_name="knowledge_search",
                arguments={"query": "Calculate 0.80 * 1.15"},
                risk_level=ToolRiskLevel.LOW,
            )
            t_res = ToolResult(
                call_id="c_wrong",
                tool_name="knowledge_search",
                output="No matching documentation found.",
            )
            step = AgentStep(
                sequence=1,
                action="knowledge_search",
                action_type=ActionType.TOOL_CALL,
                tool_call=t_call,
                tool_result=t_res,
            )
            steps.append(step)
            failures.append(
                AgentFailure(
                    stage=AgentStage.TOOL_SELECTION,
                    category=AgentFailureCategory.TOOL_SELECTION_FAILURE,
                    message="Selected search tool instead of arithmetic calculator",
                    severity=FailureSeverity.HIGH,
                )
            )

        elif scenario_upper == "TOOL_FAILURE":
            t_call = ToolCall(
                tool_name="document_lookup",
                arguments={"doc_id": "nonexistent_secret_file.md"},
                risk_level=ToolRiskLevel.LOW,
            )
            t_res = ToolResult(
                call_id="c_fail",
                tool_name="document_lookup",
                output="DOCUMENT_NOT_FOUND: nonexistent_secret_file.md",
                is_error=True,
                error_message="Document not found",
            )
            step = AgentStep(
                sequence=1,
                action="document_lookup",
                action_type=ActionType.TOOL_CALL,
                tool_call=t_call,
                tool_result=t_res,
            )
            steps.append(step)

        elif scenario_upper == "OBSERVATION_ERROR":
            step = AgentStep(
                sequence=1,
                action="status_lookup",
                action_type=ActionType.TOOL_CALL,
                tool_call=ToolCall(
                    tool_name="status_lookup", arguments={"component": "evaluation"}
                ),
                tool_result=ToolResult(
                    call_id="c_obs",
                    tool_name="status_lookup",
                    output="HEALTHY",
                ),
                observation=Observation(
                    source="corrupted_stream",
                    raw_data={"corrupted": True},
                    interpreted_content="INVALID_PARSING_ENCOUNTERED",
                    confidence=0.1,
                ),
            )
            steps.append(step)
            failures.append(
                AgentFailure(
                    stage=AgentStage.OBSERVATION,
                    category=AgentFailureCategory.OBSERVATION_INTERPRETATION_FAILURE,
                    message="Observation interpretation failed due to invalid stream format",
                    severity=FailureSeverity.MEDIUM,
                )
            )

        elif scenario_upper == "MEMORY_ERROR":
            state.corrupted = True
            step = AgentStep(
                sequence=1,
                action="calculator",
                action_type=ActionType.TOOL_CALL,
                tool_call=ToolCall(
                    tool_name="calculator", arguments={"expression": "2+2"}
                ),
                tool_result=ToolResult(
                    call_id="c_mem", tool_name="calculator", output="4.0"
                ),
            )
            steps.append(step)
            failures.append(
                AgentFailure(
                    stage=AgentStage.STATE,
                    category=AgentFailureCategory.CORRUPTED_STATE,
                    message="Memory register conflicted with preceding state snapshot",
                    severity=FailureSeverity.HIGH,
                )
            )

        else:
            # NORMAL_AGENT execution
            if "calculate" in task_text.lower() or "0.80" in task_text:
                expr = "0.80 * 1.15"
                tool_output = DEMO_TOOL_REGISTRY["calculator"]["function"](expr)
                t_call = ToolCall(
                    tool_name="calculator", arguments={"expression": expr}
                )
                t_res = ToolResult(
                    call_id="c_calc_norm",
                    tool_name="calculator",
                    output=tool_output,
                    latency_ms=5.0,
                )
                obs = Observation(
                    source="tool",
                    raw_data={"result": tool_output},
                    interpreted_content=f"Calculation evaluated to {tool_output}",
                )
                step = AgentStep(
                    sequence=1,
                    action="calculator",
                    action_type=ActionType.TOOL_CALL,
                    tool_call=t_call,
                    tool_result=t_res,
                    observation=obs,
                )
                steps.append(step)
                state.update_variable("calculated_score", tool_output)
            elif "status" in task_text.lower():
                tool_output = DEMO_TOOL_REGISTRY["status_lookup"]["function"](
                    "evaluation"
                )
                t_call = ToolCall(
                    tool_name="status_lookup", arguments={"component": "evaluation"}
                )
                t_res = ToolResult(
                    call_id="c_stat", tool_name="status_lookup", output=tool_output
                )
                obs = Observation(
                    source="tool",
                    raw_data={"status": tool_output},
                    interpreted_content="Evaluation component verified healthy",
                )
                step = AgentStep(
                    sequence=1,
                    action="status_lookup",
                    action_type=ActionType.TOOL_CALL,
                    tool_call=t_call,
                    tool_result=t_res,
                    observation=obs,
                )
                steps.append(step)
            else:
                tool_output = DEMO_TOOL_REGISTRY["knowledge_search"]["function"](
                    "hard safety veto"
                )
                t_call = ToolCall(
                    tool_name="knowledge_search",
                    arguments={"query": "hard safety veto"},
                )
                t_res = ToolResult(
                    call_id="c_know", tool_name="knowledge_search", output=tool_output
                )
                obs = Observation(
                    source="tool",
                    raw_data={"snippets": 1},
                    interpreted_content="Retrieved safety veto documentation",
                )
                step = AgentStep(
                    sequence=1,
                    action="knowledge_search",
                    action_type=ActionType.TOOL_CALL,
                    tool_call=t_call,
                    tool_result=t_res,
                    observation=obs,
                )
                steps.append(step)

        # 4. GOAL VERIFICATION
        if scenario_upper == "GOAL_FAILURE":
            goal_status = GoalStatus.FAILED
            completion_ratio = 0.0
            failures.append(
                AgentFailure(
                    stage=AgentStage.GOAL_VERIFICATION,
                    category=AgentFailureCategory.PREMATURE_TERMINATION,
                    message="Final response provided but mandatory task criteria were unfulfilled",
                    severity=FailureSeverity.CRITICAL,
                )
            )
        elif len(failures) > 0 or scenario_upper in (
            "RUNAWAY_LOOP",
            "RETRY_LOOP",
            "WRONG_TOOL",
            "TOOL_FAILURE",
        ):
            goal_status = GoalStatus.FAILED
            completion_ratio = 0.5
        else:
            goal_status = GoalStatus.COMPLETED
            completion_ratio = 1.0

        goal_verification = GoalVerification(
            overall_status=goal_status,
            completion_ratio=completion_ratio,
            goal_id=goals[0].goal_id,
            criteria_status={
                "crit_exec": CriterionStatus.SATISFIED
                if completion_ratio == 1.0
                else CriterionStatus.UNSATISFIED,
                "crit_goal": CriterionStatus.SATISFIED
                if completion_ratio == 1.0
                else CriterionStatus.UNSATISFIED,
            },
        )

        trajectory = AgentTrajectory(
            steps=steps,
            total_steps=len(steps),
        )

        final_resp = (
            "Task execution finished successfully with verified results."
            if goal_status == GoalStatus.COMPLETED
            else "Task execution halted due to scenario constraints or errors."
        )

        return AgentRun(
            run_id=f"run_{t_id}",
            agent_id=self.name,
            task=agent_task,
            plan=plan,
            trajectory=trajectory,
            tools=list(DEMO_TOOL_REGISTRY.keys()),
            final_response=final_resp,
            goal_verification=goal_verification,
            failures=failures,
        )
