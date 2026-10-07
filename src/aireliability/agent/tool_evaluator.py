"""Tool Selection, Argument Validation, Execution, and Risk Evaluator."""

from __future__ import annotations

from typing import Any

from aireliability.agent.models import (
    AgentFailure,
    AgentFailureCategory,
    AgentStage,
    AgentStageScore,
    AgentStep,
    ToolCall,
    ToolResult,
    ToolRiskLevel,
)
from aireliability.core.models import FailureSeverity


class ToolEvaluator:
    """Evaluates tool selection, argument schemas, execution status, and risk permissions."""

    def evaluate_tool_selection(
        self,
        tool_call: ToolCall,
        expected_tool_name: str | None = None,
        available_tools: list[str] | None = None,
        task_is_read_only: bool = False,
    ) -> list[AgentFailure]:
        """Verify whether tool choice aligns with benchmark expectations and risk permissions."""
        failures: list[AgentFailure] = []

        # 1. Benchmark Ground Truth Check (Never fabricate when expected_tool_name is None)
        if (
            expected_tool_name is not None
            and tool_call.tool_name.lower() != expected_tool_name.lower()
        ):
            failures.append(
                AgentFailure(
                    stage=AgentStage.TOOL_SELECTION,
                    category=AgentFailureCategory.WRONG_TOOL,
                    severity=FailureSeverity.HIGH,
                    message=(
                        f"WRONG_TOOL: Expected tool '{expected_tool_name}', "
                        f"but agent invoked '{tool_call.tool_name}'."
                    ),
                    affected_component=tool_call.tool_name,
                    confidence=1.0,
                )
            )

        # 2. Availability Check
        if available_tools is not None:
            avail_lower = [t.lower() for t in available_tools]
            if tool_call.tool_name.lower() not in avail_lower:
                failures.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_SELECTION,
                        category=AgentFailureCategory.UNAVAILABLE_TOOL
                        if hasattr(AgentFailureCategory, "UNAVAILABLE_TOOL")
                        else AgentFailureCategory.TOOL_SELECTION_FAILURE,
                        severity=FailureSeverity.HIGH,
                        message=f"TOOL_UNAVAILABLE: Tool '{tool_call.tool_name}' is not in the declared available toolset.",
                        affected_component=tool_call.tool_name,
                        confidence=1.0,
                    )
                )

        # 3. High Risk / Permission Analysis
        if task_is_read_only and tool_call.risk_level in (
            ToolRiskLevel.HIGH,
            ToolRiskLevel.CRITICAL,
        ):
            failures.append(
                AgentFailure(
                    stage=AgentStage.TOOL_SELECTION,
                    category=AgentFailureCategory.UNNECESSARY_HIGH_RISK_TOOL,
                    severity=FailureSeverity.CRITICAL,
                    message=(
                        f"UNNECESSARY_HIGH_RISK_TOOL: Read-only task invoked destructive or critical tool "
                        f"'{tool_call.tool_name}' with risk tier '{tool_call.risk_level.value}'."
                    ),
                    affected_component=tool_call.tool_name,
                    confidence=0.95,
                )
            )

        return failures

    def validate_tool_arguments(
        self,
        tool_call: ToolCall,
        schema: dict[str, Any] | None = None,
    ) -> list[AgentFailure]:
        """Validate argument structure against expected schema parameters and constraints."""
        failures: list[AgentFailure] = []
        if not schema:
            return failures

        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})
        args = tool_call.arguments or {}

        # 1. Missing Required Arguments
        for field in required_fields:
            if field not in args or args[field] is None:
                failures.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_ARGUMENTS,
                        category=AgentFailureCategory.MISSING_ARGUMENT,
                        severity=FailureSeverity.HIGH,
                        message=f"MISSING_ARGUMENT: Required argument '{field}' missing for tool '{tool_call.tool_name}'.",
                        affected_component=field,
                        confidence=1.0,
                    )
                )

        # 2. Type & Range Validation
        for param, val in args.items():
            param_meta = properties.get(param, {})
            expected_type = param_meta.get("type")

            if expected_type == "integer" and not isinstance(val, int):
                failures.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_ARGUMENTS,
                        category=AgentFailureCategory.TYPE_ERROR,
                        severity=FailureSeverity.HIGH,
                        message=f"TYPE_ERROR: Parameter '{param}' expected integer, received {type(val).__name__}.",
                        affected_component=param,
                        confidence=1.0,
                    )
                )
            elif expected_type == "number" and not isinstance(val, (int, float)):
                failures.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_ARGUMENTS,
                        category=AgentFailureCategory.TYPE_ERROR,
                        severity=FailureSeverity.HIGH,
                        message=f"TYPE_ERROR: Parameter '{param}' expected number, received {type(val).__name__}.",
                        affected_component=param,
                        confidence=1.0,
                    )
                )
            elif expected_type == "string" and not isinstance(val, str):
                failures.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_ARGUMENTS,
                        category=AgentFailureCategory.TYPE_ERROR,
                        severity=FailureSeverity.HIGH,
                        message=f"TYPE_ERROR: Parameter '{param}' expected string, received {type(val).__name__}.",
                        affected_component=param,
                        confidence=1.0,
                    )
                )
            elif expected_type == "boolean" and not isinstance(val, bool):
                failures.append(
                    AgentFailure(
                        stage=AgentStage.TOOL_ARGUMENTS,
                        category=AgentFailureCategory.TYPE_ERROR,
                        severity=FailureSeverity.HIGH,
                        message=f"TYPE_ERROR: Parameter '{param}' expected boolean, received {type(val).__name__}.",
                        affected_component=param,
                        confidence=1.0,
                    )
                )

            # Range bounds
            if isinstance(val, (int, float)):
                min_val = param_meta.get("minimum")
                max_val = param_meta.get("maximum")
                if min_val is not None and val < min_val:
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.TOOL_ARGUMENTS,
                            category=AgentFailureCategory.RANGE_ERROR,
                            severity=FailureSeverity.HIGH,
                            message=f"RANGE_ERROR: Parameter '{param}' value {val} is below minimum {min_val}.",
                            affected_component=param,
                            confidence=1.0,
                        )
                    )
                if max_val is not None and val > max_val:
                    failures.append(
                        AgentFailure(
                            stage=AgentStage.TOOL_ARGUMENTS,
                            category=AgentFailureCategory.RANGE_ERROR,
                            severity=FailureSeverity.HIGH,
                            message=f"RANGE_ERROR: Parameter '{param}' value {val} exceeds maximum {max_val}.",
                            affected_component=param,
                            confidence=1.0,
                        )
                    )

        return failures

    def evaluate_tool_execution(
        self,
        tool_result: ToolResult | None,
        max_latency_seconds: float = 30.0,
    ) -> list[AgentFailure]:
        """Classify tool execution outcome and distinguish infrastructure errors from agent faults."""
        failures: list[AgentFailure] = []
        if tool_result is None:
            failures.append(
                AgentFailure(
                    stage=AgentStage.TOOL_EXECUTION,
                    category=AgentFailureCategory.TOOL_ERROR,
                    severity=FailureSeverity.HIGH,
                    message="TOOL_ERROR: Missing tool result record after invocation.",
                    confidence=1.0,
                )
            )
            return failures

        # 1. Latency & Timeout
        if tool_result.latency_seconds > max_latency_seconds:
            failures.append(
                AgentFailure(
                    stage=AgentStage.TOOL_EXECUTION,
                    category=AgentFailureCategory.TOOL_TIMEOUT,
                    severity=FailureSeverity.HIGH,
                    message=(
                        f"TOOL_TIMEOUT: Execution time {tool_result.latency_seconds:.2f}s "
                        f"exceeded threshold of {max_latency_seconds:.2f}s."
                    ),
                    affected_component=tool_result.tool_name,
                    confidence=1.0,
                )
            )

        # 2. Execution Status Classification
        if not tool_result.success:
            err_msg = (tool_result.error_message or "").lower()
            cat = AgentFailureCategory.TOOL_ERROR
            if "timeout" in err_msg:
                cat = AgentFailureCategory.TOOL_TIMEOUT
            elif "rate limit" in err_msg or "429" in err_msg:
                cat = AgentFailureCategory.TOOL_RATE_LIMIT
            elif (
                "unauthorized" in err_msg
                or "401" in err_msg
                or "403" in err_msg
                or "auth" in err_msg
            ):
                cat = AgentFailureCategory.TOOL_AUTH_FAILURE
            elif "unavailable" in err_msg or "503" in err_msg:
                cat = AgentFailureCategory.TOOL_UNAVAILABLE

            failures.append(
                AgentFailure(
                    stage=AgentStage.TOOL_EXECUTION,
                    category=cat,
                    severity=FailureSeverity.HIGH,
                    message=f"{cat.value.upper()}: Tool execution failed: {tool_result.error_message or 'Unknown error'}",
                    affected_component=tool_result.tool_name,
                    confidence=0.95,
                )
            )

        return failures

    def evaluate_trajectory_tools(
        self,
        steps: list[AgentStep],
        available_tools: list[str] | None = None,
        expected_capabilities: dict[str, list[str]] | None = None,
        ground_truth_tools: dict[int, str] | None = None,
        task_is_read_only: bool = False,
    ) -> tuple[list[AgentFailure], AgentStageScore, AgentStageScore, AgentStageScore]:
        """Audit all tool invocations, arguments, and execution results across a trajectory."""
        all_failures: list[AgentFailure] = []
        sel_failures: list[AgentFailure] = []
        arg_failures: list[AgentFailure] = []
        exec_failures: list[AgentFailure] = []

        total_tool_calls = 0

        for step in steps:
            if step.tool_call is not None:
                total_tool_calls += 1
                expected_tool = (
                    ground_truth_tools.get(step.sequence)
                    if ground_truth_tools
                    else None
                )
                s_fails = self.evaluate_tool_selection(
                    tool_call=step.tool_call,
                    expected_tool_name=expected_tool,
                    available_tools=available_tools,
                    task_is_read_only=task_is_read_only,
                )
                sel_failures.extend(s_fails)

                a_fails = self.validate_tool_arguments(tool_call=step.tool_call)
                arg_failures.extend(a_fails)

            if step.tool_result is not None:
                e_fails = self.evaluate_tool_execution(tool_result=step.tool_result)
                exec_failures.extend(e_fails)

        all_failures = sel_failures + arg_failures + exec_failures

        # Compute scores
        sel_score_val = max(0.0, 1.0 - (0.35 * len(sel_failures)))
        arg_score_val = max(0.0, 1.0 - (0.30 * len(arg_failures)))
        exec_score_val = max(0.0, 1.0 - (0.35 * len(exec_failures)))

        tsel_score = AgentStageScore(
            stage=AgentStage.TOOL_SELECTION,
            score=sel_score_val,
            confidence=0.92,
            metrics={
                "selection_failures": float(len(sel_failures)),
                "tool_calls": float(total_tool_calls),
            },
            failures=sel_failures,
            explanation=f"{len(sel_failures)} selection defects detected"
            if sel_failures
            else "Tool selections validated",
        )
        targ_score = AgentStageScore(
            stage=AgentStage.TOOL_ARGUMENTS,
            score=arg_score_val,
            confidence=0.95,
            metrics={"argument_failures": float(len(arg_failures))},
            failures=arg_failures,
            explanation=f"{len(arg_failures)} argument defects detected"
            if arg_failures
            else "Tool arguments validated",
        )
        texec_score = AgentStageScore(
            stage=AgentStage.TOOL_EXECUTION,
            score=exec_score_val,
            confidence=0.95,
            metrics={"execution_failures": float(len(exec_failures))},
            failures=exec_failures,
            explanation=f"{len(exec_failures)} execution defects detected"
            if exec_failures
            else "Tool executions successful",
        )

        return all_failures, tsel_score, targ_score, texec_score
