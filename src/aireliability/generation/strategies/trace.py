"""Production-trace-driven test generation with mandatory sanitization and trajectory capture."""

from __future__ import annotations

from typing import Any

from aireliability.core.models import ExecutionTrace, StepType
from aireliability.evaluation.online.bridge import ProductionSampler
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
    TestType,
)
from aireliability.telemetry.sanitizer import SanitizationPolicy


class TraceTestGenerator:
    """Converts sanitized production execution traces into reproducible test cases."""

    strategy = GenerationStrategy.PRODUCTION_TRACE_DRIVEN

    def __init__(
        self,
        sanitizer: SanitizationPolicy | None = None,
        sampler: ProductionSampler | None = None,
    ) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.sampler = sampler or ProductionSampler()

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        traces: list[ExecutionTrace] = []

        if isinstance(source, ExecutionTrace):
            traces = [source]
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, ExecutionTrace):
                    traces.append(item)

        # Apply sampling limit
        sampled_traces = [t for t in traces if self.sampler.should_sample(t)][
            : config.max_production_samples
        ]
        if not sampled_traces and traces:
            # If sampler filtered everything, take at least the first trace if within budget
            sampled_traces = traces[: min(len(traces), config.max_production_samples)]

        tests: list[GeneratedTest] = []
        for tr in sampled_traces[: config.max_candidates]:
            tests.append(self._from_trace(tr, config))

        return tests

    def _from_trace(
        self,
        trace: ExecutionTrace,
        config: TestGenerationConfig,
    ) -> GeneratedTest:
        # Mandatory sanitization of all trace payloads
        sanitized_input = self.sanitizer.sanitize(trace.input)
        sanitized_output = self.sanitizer.sanitize(trace.output)
        sanitized_meta = self.sanitizer.sanitize(dict(trace.metadata)) or {}

        # Extract step constraints & tool calls
        tool_calls: list[dict[str, Any]] = []
        trajectory_constraints: list[str] = []

        for step in trace.steps:
            if step.type == StepType.TOOL:
                tool_calls.append(
                    {
                        "name": step.name,
                        "input": self.sanitizer.sanitize(step.input),
                    }
                )
            trajectory_constraints.append(f"step_{step.type.value}:{step.name}")

        criteria: list[str] = [
            "execution must complete successfully without unhandled errors",
        ]
        if trace.latency_ms is not None:
            max_latency = trace.latency_ms * 1.5
            criteria.append(f"latency must remain below {max_latency:.1f}ms")

        prov = TestProvenance(
            source_type=GenerationSourceType.PRODUCTION_TRACE,
            source_id=trace.trace_id,
            source_trace_id=trace.trace_id,
            generator_name="TraceTestGenerator",
            deterministic_seed=config.deterministic_seed,
            rationale=f"Harvested from production trace {trace.trace_id} (status={trace.status.value}, steps={len(trace.steps)})",
            metadata={"status": trace.status.value, "steps_count": len(trace.steps)},
        )

        test_type = TestType.AGENT if tool_calls else TestType.INTEGRATION

        return GeneratedTest(
            name=f"trace_replay_{trace.trace_id[:8]}",
            test_type=test_type,
            strategy=self.strategy,
            input=sanitized_input or "Sanitized trace input query",
            expected_output=sanitized_output,
            expected_criteria=criteria,
            reference_answer=str(sanitized_output)
            if sanitized_output is not None
            else None,
            has_ground_truth=sanitized_output is not None,
            expected_tool_calls=tool_calls,
            expected_trajectory_constraints=trajectory_constraints,
            provenance=prov,
            confidence=0.90,
            risk_level=TestRiskLevel.LOW,
            priority=TestPriority.MEDIUM,
            tags=["production_trace_driven", f"status:{trace.status.value}"],
            metadata=sanitized_meta,
            deterministic_seed=config.deterministic_seed,
        )
