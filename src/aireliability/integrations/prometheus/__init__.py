"""Optional Prometheus metrics integration for AI Reliability Engine.

This module is lazy-loaded and requires the optional `prometheus` extra:
    pip install "aireliability[prometheus]"

If prometheus_client is not installed, importing this module raises a helpful
ImportError with installation instructions.
"""

from typing import Any

from aireliability.telemetry.models import TelemetryStatus, TelemetryTrace


def _check_prometheus_installed() -> Any:
    """Check if prometheus_client is installed, raising ImportError if missing."""
    try:
        import prometheus_client

        return prometheus_client
    except ImportError as exc:
        raise ImportError(
            "Prometheus metrics integration requires the 'prometheus' extra.\n"
            "Install with: pip install 'aireliability[prometheus]'"
        ) from exc


class PrometheusMetricsExporter:
    """Records reliability metrics into Prometheus CollectorRegistry."""

    def __init__(self, registry: Any | None = None) -> None:
        self.prom = _check_prometheus_installed()
        self.registry = registry or self.prom.REGISTRY

        # Counters
        self.total_executions = self.prom.Counter(
            "aireliability_executions_total",
            "Total number of AI reliability test executions",
            ["test_name", "status"],
            registry=self.registry,
        )
        self.evaluation_failures = self.prom.Counter(
            "aireliability_evaluation_failures_total",
            "Total number of evaluation assertion failures",
            ["test_name", "evaluator"],
            registry=self.registry,
        )
        self.model_calls = self.prom.Counter(
            "aireliability_model_calls_total",
            "Total number of model API invocations",
            ["model", "status"],
            registry=self.registry,
        )
        self.tool_calls = self.prom.Counter(
            "aireliability_tool_calls_total",
            "Total number of tool invocations",
            ["tool_name", "status"],
            registry=self.registry,
        )
        self.token_usage = self.prom.Counter(
            "aireliability_tokens_total",
            "Total tokens consumed",
            ["test_name", "type"],
            registry=self.registry,
        )

        # Histograms
        self.execution_duration = self.prom.Histogram(
            "aireliability_execution_duration_seconds",
            "Reliability execution latency in seconds",
            ["test_name"],
            registry=self.registry,
        )
        self.model_duration = self.prom.Histogram(
            "aireliability_model_duration_seconds",
            "Model call latency in seconds",
            ["model"],
            registry=self.registry,
        )
        self.tool_duration = self.prom.Histogram(
            "aireliability_tool_duration_seconds",
            "Tool call latency in seconds",
            ["tool_name"],
            registry=self.registry,
        )

    def record_trace(self, trace: TelemetryTrace) -> None:
        """Extract and record metrics from a TelemetryTrace."""
        test_name = trace.attributes.get("test.name", trace.name)
        status_label = trace.status.value

        # Execution count & duration
        self.total_executions.labels(test_name=test_name, status=status_label).inc()
        if trace.duration_ms is not None:
            self.execution_duration.labels(test_name=test_name).observe(
                trace.duration_ms / 1000.0
            )

        # Token usage
        prompt_tokens = trace.attributes.get("token.prompt_tokens", 0)
        completion_tokens = trace.attributes.get("token.completion_tokens", 0)
        if prompt_tokens:
            self.token_usage.labels(test_name=test_name, type="prompt").inc(
                prompt_tokens
            )
        if completion_tokens:
            self.token_usage.labels(test_name=test_name, type="completion").inc(
                completion_tokens
            )

        # Iterate spans for tools, models, evaluations
        for span in trace.spans:
            # Model calls
            if span.kind.value == "model":
                model_name = span.attributes.get("model.name", span.name)
                m_status = span.status.value
                self.model_calls.labels(model=model_name, status=m_status).inc()
                if span.duration_ms is not None:
                    self.model_duration.labels(model=model_name).observe(
                        span.duration_ms / 1000.0
                    )

            # Tool calls
            elif span.kind.value == "tool":
                tool_name = span.attributes.get("tool.name", span.name)
                t_status = span.status.value
                self.tool_calls.labels(tool_name=tool_name, status=t_status).inc()
                if span.duration_ms is not None:
                    self.tool_duration.labels(tool_name=tool_name).observe(
                        span.duration_ms / 1000.0
                    )

            # Evaluation failures
            elif span.kind.value == "evaluation":
                if span.status == TelemetryStatus.ERROR:
                    ev_name = span.attributes.get("evaluator.name", span.name)
                    self.evaluation_failures.labels(
                        test_name=test_name, evaluator=ev_name
                    ).inc()
