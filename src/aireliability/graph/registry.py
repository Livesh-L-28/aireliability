"""Registry managing pluggable graph store backend implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aireliability.graph.store import GraphStore, InMemoryGraphStore


class GraphStoreRegistry:
    """Registry allowing registration and creation of graph storage backends."""

    _backends: dict[str, Callable[..., GraphStore]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        factory: Callable[..., GraphStore],
        override: bool = False,
    ) -> None:
        """Register a backend store factory under a given name."""
        key = name.strip().lower()
        if key in cls._backends and not override:
            raise ValueError(f"Graph store backend '{key}' is already registered.")
        cls._backends[key] = factory

    @classmethod
    def create(cls, name: str = "memory", **kwargs: Any) -> GraphStore:
        """Instantiate a GraphStore backend by name."""
        key = name.strip().lower()
        if key not in cls._backends:
            available = ", ".join(cls.list_available())
            raise KeyError(
                f"Graph store backend '{key}' not found. Available backends: [{available}]"
            )
        return cls._backends[key](**kwargs)

    @classmethod
    def list_available(cls) -> list[str]:
        """List registered graph store backend names."""
        return sorted(cls._backends.keys())

    @classmethod
    def reset_defaults(cls) -> None:
        """Reset registry back to default in-memory implementations."""
        cls._backends.clear()
        cls.register("memory", lambda **kw: InMemoryGraphStore())
        cls.register("in_memory", lambda **kw: InMemoryGraphStore())


# Initialize default backend
GraphStoreRegistry.reset_defaults()
