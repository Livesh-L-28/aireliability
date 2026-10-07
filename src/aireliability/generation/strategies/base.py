"""Base generator protocol for AI test generation strategies."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aireliability.generation.models import (
    GeneratedTest,
    GenerationStrategy,
    TestGenerationConfig,
)


@runtime_checkable
class BaseTestGenerator(Protocol):
    """Protocol implemented by all Phase 36 test generation strategies."""

    strategy: GenerationStrategy

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        """Generate test candidates from the provided evidence source."""
        ...
