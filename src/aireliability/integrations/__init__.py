"""Optional framework integrations for AI Reliability Engine.

Integrations are lazy-loaded and require optional extras (e.g.
`aireliability[langgraph]`, `aireliability[langchain]`). Core functionality
remains independent of these packages.
"""

from typing import Any


def get_langgraph_adapter(*args: Any, **kwargs: Any) -> Any:
    """Convenience factory to import and instantiate LangGraphAdapter."""
    from aireliability.integrations.langgraph import LangGraphAdapter

    return LangGraphAdapter(*args, **kwargs)


def get_langchain_adapter(*args: Any, **kwargs: Any) -> Any:
    """Convenience factory to import and instantiate LangChainAdapter."""
    from aireliability.integrations.langchain import LangChainAdapter

    return LangChainAdapter(*args, **kwargs)


def get_openai_adapter(*args: Any, **kwargs: Any) -> Any:
    """Convenience factory to import and instantiate OpenAICompatibleAdapter."""
    from aireliability.integrations.openai_compatible import OpenAICompatibleAdapter

    return OpenAICompatibleAdapter(*args, **kwargs)


def get_opentelemetry_exporter(*args: Any, **kwargs: Any) -> Any:
    """Convenience factory to import and instantiate OpenTelemetryExporter."""
    from aireliability.integrations.opentelemetry import OpenTelemetryExporter

    return OpenTelemetryExporter(*args, **kwargs)


def get_prometheus_exporter(*args: Any, **kwargs: Any) -> Any:
    """Convenience factory to import and instantiate PrometheusMetricsExporter."""
    from aireliability.integrations.prometheus import PrometheusMetricsExporter

    return PrometheusMetricsExporter(*args, **kwargs)


__all__ = [
    "get_langchain_adapter",
    "get_langgraph_adapter",
    "get_openai_adapter",
    "get_opentelemetry_exporter",
    "get_prometheus_exporter",
]
