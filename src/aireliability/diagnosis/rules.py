"""Deterministic diagnostic rules for mapping evidence to RootCause diagnoses."""

from aireliability.core.models import (
    EvaluationResult,
    ExecutionStatus,
    ExecutionTrace,
    FailureReport,
    FailureSeverity,
    TestCase,
)
from aireliability.diagnosis.evidence import Evidence
from aireliability.diagnosis.models import (
    CausalLink,
    RootCause,
    RootCauseCategory,
    RootCauseType,
)


def diagnose_failure_report(
    failure: FailureReport,
    trace: ExecutionTrace,
    test_case: TestCase | None = None,
    eval_result: EvaluationResult | None = None,
) -> RootCause:
    """Diagnose a single FailureReport using empirical trace evidence.

    Reuses existing evaluator evidence and trace telemetry rather than speculating.
    """
    ev_list: list[Evidence] = []
    category = RootCauseCategory.UNKNOWN
    cause_type = RootCauseType.UNKNOWN
    desc = failure.message
    confidence = failure.confidence
    severity = failure.severity
    affected_step: str | None = None
    causal_links: list[CausalLink] = []

    cat_str = str(failure.category).lower()
    type_str = str(failure.type).lower()
    ev_dict = failure.evidence if isinstance(failure.evidence, dict) else {}

    # 1. TOOL FAILURES
    if cat_str == "tool" or type_str in (
        "wrong_tool",
        "wrong_argument",
        "wrong_order",
        "unnecessary_tool",
    ):
        category = RootCauseCategory.TOOL

        if type_str == "wrong_order":
            cause_type = RootCauseType.WRONG_ORDER
            expected_order = ev_dict.get("expected_order")
            actual_order = ev_dict.get("actual_order")
            if not actual_order and trace.steps:
                actual_order = [s.name for s in trace.steps if s.type == "tool"]

            # Locate the first step in trace that violated the expected sequence
            if expected_order and actual_order:
                for idx, (exp, act) in enumerate(
                    zip(expected_order, actual_order, strict=False)
                ):
                    if exp != act and idx < len(trace.steps):
                        affected_step = trace.steps[idx].id or f"step_{idx + 1}"
                        break
            if affected_step is None and trace.steps:
                affected_step = trace.steps[-1].id

            exp_str = (
                " → ".join(expected_order)
                if isinstance(expected_order, list)
                else str(expected_order)
            )
            act_str = (
                " → ".join(actual_order)
                if isinstance(actual_order, list)
                else str(actual_order)
            )
            desc = (
                f"Tool sequence ordering violation: expected '{exp_str}', "
                f"observed '{act_str}'."
            )

            ev_list.append(
                Evidence(
                    source="evaluator_result",
                    trace_id=trace.trace_id,
                    step_id=affected_step,
                    field="tool_order",
                    expected=exp_str,
                    actual=act_str,
                    explanation=(
                        f"Tools were executed in order '{act_str}' violating "
                        f"expected sequence '{exp_str}'."
                    ),
                )
            )

        elif type_str == "wrong_argument":
            cause_type = RootCauseType.WRONG_ARGUMENT
            tool_name = ev_dict.get("tool_name", "unknown")
            expected_args = ev_dict.get("expected_arguments", {})
            actual_args = ev_dict.get("actual_arguments", {})

            # Locate affected step
            for s in trace.steps:
                if s.type == "tool" and s.name == tool_name:
                    affected_step = s.id
                    break

            desc = (
                f"Tool '{tool_name}' invoked with incorrect arguments: "
                f"expected {expected_args}, received {actual_args}."
            )
            ev_list.append(
                Evidence(
                    source="evaluator_result",
                    trace_id=trace.trace_id,
                    step_id=affected_step,
                    field="arguments",
                    expected=expected_args,
                    actual=actual_args,
                    explanation=f"Argument mismatch for tool '{tool_name}'.",
                )
            )

        elif type_str == "wrong_tool":
            cause_type = RootCauseType.WRONG_TOOL
            expected_tool = ev_dict.get("expected_tool") or ev_dict.get(
                "forbidden_tool"
            )
            actual_tools = ev_dict.get("called_tools") or [
                s.name for s in trace.steps if s.type == "tool"
            ]

            # Missing or substituted
            if expected_tool and expected_tool not in actual_tools:
                cause_type = RootCauseType.MISSING_TOOL
                desc = f"Required tool '{expected_tool}' was never invoked."
                # Substituted tool as affected step
                if trace.steps:
                    for s in trace.steps:
                        if s.type == "tool":
                            affected_step = s.id
                            break
                ev_list.append(
                    Evidence(
                        source="evaluator_result",
                        trace_id=trace.trace_id,
                        step_id=affected_step,
                        field="tool_called",
                        expected=f"Tool '{expected_tool}' called >= 1 time(s)",
                        actual=f"Called {actual_tools}",
                        explanation=f"Trace omitted required tool '{expected_tool}'.",
                    )
                )
            else:
                if trace.steps:
                    for s in trace.steps:
                        if s.type == "tool":
                            affected_step = s.id
                            break
                desc = f"Tool assertion failed. Called tools: {actual_tools}."
                ev_list.append(
                    Evidence(
                        source="evaluator_result",
                        trace_id=trace.trace_id,
                        step_id=affected_step,
                        field="tool_called",
                        expected=expected_tool,
                        actual=actual_tools,
                        explanation=failure.message,
                    )
                )

        elif type_str == "unnecessary_tool":
            cause_type = RootCauseType.WRONG_TOOL
            forbidden = ev_dict.get("forbidden_tool")
            desc = f"Unnecessary or forbidden tool '{forbidden}' was invoked."
            ev_list.append(
                Evidence(
                    source="evaluator_result",
                    trace_id=trace.trace_id,
                    field="tool_not_called",
                    expected=f"Tool '{forbidden}' not called",
                    actual="Called",
                    explanation=f"Tool '{forbidden}' executed despite constraint.",
                )
            )

    # 2. OUTPUT & TASK FAILURES
    elif cat_str in ("output", "task"):
        category = RootCauseCategory.OUTPUT

        if (
            type_str
            in ("semantic_violation", "semantic_relevance", "semantic_similarity")
            or "semantic" in type_str
        ):
            cause_type = RootCauseType.SEMANTIC_MISMATCH
            score = ev_dict.get("score")
            threshold = ev_dict.get("threshold")
            reasoning = (
                ev_dict.get("reasoning")
                or ev_dict.get("judge_explanation")
                or failure.message
            )

            desc = (
                f"Semantic evaluation mismatch (score {score} < threshold "
                f"{threshold}). Reason: {reasoning}"
            )
            ev_list.append(
                Evidence(
                    source="semantic_evaluator",
                    trace_id=trace.trace_id,
                    field="output_semantics",
                    expected=f"Score >= {threshold}",
                    actual=f"Score {score}",
                    explanation=str(reasoning),
                    metadata={
                        "provider": ev_dict.get("provider", ""),
                        "model": ev_dict.get("model", ""),
                        "criteria": ev_dict.get("criteria_results", {}),
                    },
                )
            )

        elif type_str == "schema_error":
            cause_type = RootCauseType.UNEXPECTED_OUTPUT
            desc = f"Output failed schema conformance: {failure.message}"
            ev_list.append(
                Evidence(
                    source="evaluator_result",
                    trace_id=trace.trace_id,
                    field="schema",
                    expected="Conform to target schema",
                    actual=trace.output,
                    explanation=failure.message,
                )
            )

        else:
            # Exact or Contains output mismatch
            cause_type = RootCauseType.UNEXPECTED_OUTPUT
            exp_out = test_case.expected_output if test_case else None
            desc = (
                f"Output discrepancy: expected '{exp_out}', observed '{trace.output}'."
            )
            ev_list.append(
                Evidence(
                    source="evaluator_result",
                    trace_id=trace.trace_id,
                    field="output",
                    expected=exp_out,
                    actual=trace.output,
                    explanation=failure.message,
                )
            )

    # 3. PERFORMANCE FAILURES
    elif cat_str == "performance" or type_str in ("latency", "cost", "token_overuse"):
        category = RootCauseCategory.PERFORMANCE
        cause_type = RootCauseType.LATENCY_REGRESSION
        max_lat = ev_dict.get("max_latency_ms")
        act_lat = ev_dict.get("actual_latency_ms") or trace.latency_ms or 0.0
        max_lat_val = float(max_lat) if max_lat is not None else 1000.0
        act_lat_val = float(act_lat) if act_lat is not None else 0.0
        delta_lat = act_lat_val - max_lat_val

        desc = (
            f"Execution latency regression: measured {act_lat_val:.1f}ms "
            f"exceeding budget of {max_lat_val:.1f}ms."
        )
        ev_list.append(
            Evidence(
                source="execution_trace",
                trace_id=trace.trace_id,
                field="latency_ms",
                expected=f"<= {max_lat}ms",
                actual=f"{act_lat:.1f}ms",
                explanation=(
                    f"Execution elapsed time exceeded target by {delta_lat:.1f}ms."
                ),
            )
        )

    # 4. EXECUTION CRASHES
    elif trace.status == ExecutionStatus.FAILED:
        category = RootCauseCategory.EXECUTION
        cause_type = RootCauseType.EXCEPTION
        severity = FailureSeverity.CRITICAL
        err_msg = str(trace.output) if trace.output else failure.message
        desc = f"Agent execution terminated with unhandled exception: {err_msg}"
        ev_list.append(
            Evidence(
                source="execution_trace",
                trace_id=trace.trace_id,
                field="execution_status",
                expected="COMPLETED",
                actual="FAILED",
                explanation=err_msg,
            )
        )

    # Fallback
    else:
        category = RootCauseCategory.UNKNOWN
        cause_type = RootCauseType.UNKNOWN
        ev_list.append(
            Evidence(
                source="failure_report",
                trace_id=trace.trace_id,
                field="message",
                expected="Pass",
                actual="Fail",
                explanation=failure.message,
            )
        )

    return RootCause(
        category=category,
        type=cause_type,
        description=desc,
        confidence=confidence,
        evidence=ev_list,
        affected_step=affected_step,
        severity=severity,
        causal_links=causal_links,
        metadata={"source_failure_id": failure.failure_id},
    )
