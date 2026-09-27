"""LangChain execution adapter for AI Reliability Engine."""

from typing import Any


def _check_langchain_dependency() -> None:
    """Verify that langchain is installed or raise a descriptive error."""
    try:
        import langchain_core  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "LangChain integration requires the optional dependency.\n"
            "Install with:\n"
            '    pip install "aireliability[langchain]"'
        ) from exc


def __getattr__(name: str) -> Any:
    if name == "LangChainAdapter":
        _check_langchain_dependency()
        from aireliability.integrations.langchain.adapter import LangChainAdapter

        return LangChainAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["LangChainAdapter"]
