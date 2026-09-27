"""LangGraph execution adapter for AI Reliability Engine."""

from typing import Any


def _check_langgraph_dependency() -> None:
    """Verify that langgraph is installed or raise a descriptive error."""
    try:
        import langgraph  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "LangGraph integration requires the optional dependency.\n"
            "Install with:\n"
            '    pip install "aireliability[langgraph]"'
        ) from exc


def __getattr__(name: str) -> Any:
    if name == "LangGraphAdapter":
        _check_langgraph_dependency()
        from aireliability.integrations.langgraph.adapter import LangGraphAdapter

        return LangGraphAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["LangGraphAdapter"]
