"""LLM Provider abstraction and contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract interface for LLM providers used in the demo."""

    @abstractmethod
    def generate(self, prompt: str, scenario: str = "NORMAL", **kwargs: Any) -> str:
        """Generate text from a prompt under an optional controlled scenario."""
        raise NotImplementedError

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        scenario: str = "NORMAL",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate structured JSON output from a prompt."""
        raise NotImplementedError
