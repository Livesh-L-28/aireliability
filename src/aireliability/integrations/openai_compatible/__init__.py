"""OpenAI-compatible execution adapter for AI Reliability Engine."""

from typing import Any


def _check_openai_dependency() -> None:
    """Verify that openai is installed or raise a descriptive error."""
    try:
        import openai  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "OpenAI integration requires the optional dependency.\n"
            "Install with:\n"
            '    pip install "aireliability[openai]"'
        ) from exc


def __getattr__(name: str) -> Any:
    if name == "OpenAICompatibleAdapter":
        # The adapter works without openai installed (e.g. duck-typed clients),
        # but importing through the integration namespace checks or provides it.
        from aireliability.integrations.openai_compatible.adapter import (
            OpenAICompatibleAdapter,
        )

        return OpenAICompatibleAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["OpenAICompatibleAdapter"]
