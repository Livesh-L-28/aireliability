"""Builder and translator to convert RunResults and ExecutionTraces into
TelemetryTraces.

Translates the normalized agent execution lifecycle:
Execution (Root Span)
└── Agent / Adapter
    ├── Model Calls (Model Spans + Token Usage)
    ├── Tool Calls & Results (Tool Spans)
    ├── Retrieval / Custom Steps
    ├── Evaluation (Evaluation Spans)
    ├── Failures & Root Causes (Failure Events / Attributes)
    └── Regression Tracking
"""

from typing import Any

from aireliability.core.models import (
    RunResult,
    StepType,
)
from aireliability.diagnosis.models import RootCauseReport
from aireliability.telemetry.models import (
    SpanKind,
    TelemetryEvent,
    TelemetrySpan,
    TelemetryStatus,
    TelemetryTrace,
)
from aireliability.telemetry.sanitizer import SanitizationPolicy


class TelemetryBuilder:
    """Constructs structured TelemetryTraces from execution and evaluation objects."""

    def __init__(self, sanitizer: SanitizationPolicy | None = None) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()

    def build_trace(
        self,
        run_result: RunResult,
        *,
        trace_id: str | None = None,
        root_cause_report: RootCauseReport | None = None,
        regression_test_id: str | None = None,
        baseline_status: str | None = None,
    ) -> TelemetryTrace:
        """Translate a completed RunResult into a rich TelemetryTrace."""
        trace = run_result.trace
        test_case = run_result.test

        # Resolve trace ID: caller provided or execution trace_id
        resolved_trace_id = trace_id or trace.trace_id

        # Determine overall status
        telemetry_status = (
            TelemetryStatus.OK if run_result.passed else TelemetryStatus.ERROR
        )

        spans: list[TelemetrySpan] = []

        # 1. Root Agent Execution Span
        root_span_id = f"span_{resolved_trace_id}_root"
        root_attributes: dict[str, Any] = {
            "test.id": test_case.id,
            "test.name": test_case.name,
            "execution.status": trace.status.value,
            "token.prompt_tokens": trace.token_usage.get(
                "prompt_tokens", trace.token_usage.get("input_tokens", 0)
            ),
            "token.completion_tokens": trace.token_usage.get(
                "completion_tokens", trace.token_usage.get("output_tokens", 0)
            ),
            "token.total_tokens": trace.token_usage.get(
                "total_tokens", sum(trace.token_usage.values())
            ),
            "cost": trace.cost,
            "passed": run_result.passed,
        }
        if baseline_status:
            root_attributes["baseline.status"] = baseline_status
        if regression_test_id:
            root_attributes["regression.test_id"] = regression_test_id

        # Root events
        root_events: list[TelemetryEvent] = [
            TelemetryEvent(
                name="execution.started",
                timestamp=trace.started_at,
                attributes={"test_id": test_case.id},
            )
        ]
        if trace.completed_at:
            root_events.append(
                TelemetryEvent(
                    name="execution.completed",
                    timestamp=trace.completed_at,
                    attributes={"passed": run_result.passed},
                )
            )

        # Attach Failures as events on root span
        if run_result.failures:
            for fail in run_result.failures:
                fail_event = TelemetryEvent(
                    name="reliability.failure_detected",
                    timestamp=trace.completed_at or trace.started_at,
                    attributes={
                        "failure.id": fail.failure_id,
                        "failure.category": fail.category,
                        "failure.type": fail.type,
                        "failure.severity": fail.severity.value,
                        "failure.message": fail.message,
                        "failure.confidence": fail.confidence,
                    },
                )
                root_events.append(fail_event)

        root_span = TelemetrySpan(
            span_id=root_span_id,
            trace_id=resolved_trace_id,
            parent_span_id=None,
            name=f"agent.{test_case.name}",
            kind=SpanKind.AGENT,
            status=telemetry_status,
            status_message=None
            if run_result.passed
            else f"Test failed with {len(run_result.failures)} failure(s)",
            started_at=trace.started_at,
            completed_at=trace.completed_at,
            duration_ms=trace.latency_ms,
            attributes=root_attributes,
            events=root_events,
        )
        spans.append(root_span)

        # 2. Translate Steps (Model Calls, Tools, Retrieval)
        for idx, step in enumerate(trace.steps):
            span_kind = self._map_step_type_to_kind(step.type)
            step_status = (
                TelemetryStatus.ERROR
                if step.metadata.get("status") == "failed"
                or (isinstance(step.output, dict) and "error" in step.output)
                else TelemetryStatus.OK
            )

            step_attributes: dict[str, Any] = {
                "step.type": step.type.value,
                "step.name": step.name,
                "step.index": idx,
            }

            # Map Tool attributes
            if step.type == StepType.TOOL:
                step_attributes["tool.name"] = step.name
                if "call_id" in step.metadata:
                    step_attributes["tool.call_id"] = step.metadata["call_id"]
                step_attributes["tool.input"] = step.input
                step_attributes["tool.output"] = step.output

            # Map Model attributes
            elif step.type == StepType.LLM:
                step_attributes["model.name"] = step.metadata.get("model") or step.name
                if "call_id" in step.metadata:
                    step_attributes["model.call_id"] = step.metadata["call_id"]
                if "latency_ms" in step.metadata:
                    step_attributes["model.latency_ms"] = step.metadata["latency_ms"]
                if "streamed" in step.metadata:
                    step_attributes["model.streamed"] = step.metadata["streamed"]
                if "retries" in step.metadata:
                    step_attributes["model.retries"] = step.metadata["retries"]
                if "usage" in step.metadata:
                    usage = step.metadata["usage"]
                    if isinstance(usage, dict):
                        step_attributes["model.input_tokens"] = usage.get(
                            "input_tokens", usage.get("prompt_tokens")
                        )
                        step_attributes["model.output_tokens"] = usage.get(
                            "output_tokens", usage.get("completion_tokens")
                        )
                        step_attributes["model.total_tokens"] = usage.get(
                            "total_tokens"
                        )
                        step_attributes["model.cached_tokens"] = usage.get(
                            "cached_tokens"
                        )

            # Metadata attributes
            for k, v in step.metadata.items():
                if k not in (
                    "model",
                    "call_id",
                    "usage",
                    "streamed",
                    "retries",
                    "latency_ms",
                ):
                    step_attributes[f"step.meta.{k}"] = v

            step_span = TelemetrySpan(
                span_id=f"span_{step.id}",
                trace_id=resolved_trace_id,
                parent_span_id=root_span_id,
                name=f"{step.type.value}.{step.name}",
                kind=span_kind,
                status=step_status,
                started_at=step.started_at,
                completed_at=step.completed_at,
                duration_ms=step.duration_ms,
                attributes=step_attributes,
            )
            spans.append(step_span)

        # 3. Translate Evaluations as child spans
        for ev_idx, ev in enumerate(run_result.evaluations):
            ev_status = TelemetryStatus.OK if ev.passed else TelemetryStatus.ERROR
            ev_attributes: dict[str, Any] = {
                "evaluator.name": ev.evaluator,
                "evaluator.passed": ev.passed,
                "evaluator.score": ev.score,
                "evaluator.message": ev.message,
            }
            if ev.evidence is not None:
                ev_attributes["evaluator.evidence"] = ev.evidence
            for k, v in ev.metadata.items():
                ev_attributes[f"evaluator.meta.{k}"] = v

            ev_span = TelemetrySpan(
                span_id=f"span_eval_{ev_idx}_{resolved_trace_id}",
                trace_id=resolved_trace_id,
                parent_span_id=root_span_id,
                name=f"eval.{ev.evaluator}",
                kind=SpanKind.EVALUATION,
                status=ev_status,
                status_message=None if ev.passed else ev.message,
                started_at=trace.completed_at or trace.started_at,
                completed_at=trace.completed_at or trace.started_at,
                duration_ms=0.0,
                attributes=ev_attributes,
            )
            spans.append(ev_span)

        # 4. Attach Root-Cause Analysis as an analysis span if provided

        # If a RootCauseReport is attached, add an analysis span
        if root_cause_report is not None:
            report_id = getattr(root_cause_report, "id", None) or getattr(
                root_cause_report, "report_id", None
            )
            analysis_attrs: dict[str, Any] = {
                "diagnosis.report_id": report_id,
                "diagnosis.primary_cause": root_cause_report.primary_cause.type.value
                if root_cause_report.primary_cause
                else None,
                "diagnosis.category": root_cause_report.primary_cause.category.value
                if root_cause_report.primary_cause
                else None,
                "diagnosis.summary": root_cause_report.summary,
            }
            analysis_span = TelemetrySpan(
                span_id=f"span_rca_{resolved_trace_id}",
                trace_id=resolved_trace_id,
                parent_span_id=root_span_id,
                name="analysis.root_cause",
                kind=SpanKind.ANALYSIS,
                status=TelemetryStatus.OK,
                started_at=trace.completed_at or trace.started_at,
                completed_at=trace.completed_at or trace.started_at,
                duration_ms=0.0,
                attributes=analysis_attrs,
            )
            spans.append(analysis_span)

        # Assemble full trace
        telemetry_trace = TelemetryTrace(
            trace_id=resolved_trace_id,
            execution_id=run_result.metadata.get("execution_id"),
            test_id=test_case.id,
            name=f"test.{test_case.name}",
            status=telemetry_status,
            started_at=trace.started_at,
            completed_at=trace.completed_at,
            duration_ms=trace.latency_ms,
            spans=spans,
            attributes=root_attributes,
        )

        return telemetry_trace

    @staticmethod
    def _map_step_type_to_kind(step_type: StepType) -> SpanKind:
        if step_type == StepType.LLM:
            return SpanKind.MODEL
        if step_type == StepType.TOOL:
            return SpanKind.TOOL
        if step_type == StepType.RETRIEVAL:
            return SpanKind.RETRIEVAL
        if step_type == StepType.AGENT:
            return SpanKind.AGENT
        return SpanKind.INTERNAL
