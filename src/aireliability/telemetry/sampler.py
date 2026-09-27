"""Configurable sampling strategies for telemetry collection."""

import random
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class TelemetrySampler(Protocol):
    """Protocol for deciding whether an execution trace should be recorded."""

    def should_sample(self, trace_id: str | None = None) -> bool:
        """Return True if the execution should be recorded, False otherwise."""
        ...


@dataclass(frozen=True)
class AlwaysOnSampler:
    """Always sample every execution."""

    def should_sample(self, trace_id: str | None = None) -> bool:
        return True


@dataclass(frozen=True)
class AlwaysOffSampler:
    """Never sample any execution (telemetry disabled)."""

    def should_sample(self, trace_id: str | None = None) -> bool:
        return False


class RatioSampler:
    """Sample traces based on a configured probability ratio between 0.0 and 1.0.

    Supports an optional seed for deterministic evaluation in tests and CI.
    """

    def __init__(
        self,
        ratio: float = 1.0,
        *,
        seed: int | None = None,
    ) -> None:
        if not (0.0 <= ratio <= 1.0):
            raise ValueError(f"Sampling ratio must be between 0.0 and 1.0, got {ratio}")
        self.ratio = ratio
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self.seed = seed

    def should_sample(self, trace_id: str | None = None) -> bool:
        if self.ratio >= 1.0:
            return True
        if self.ratio <= 0.0:
            return False
        # If deterministic trace ID is provided and no random seed was set, we can hash
        if trace_id is not None and self.seed is None:
            # Deterministic hash-based sampling on trace_id
            hash_val = sum(ord(c) for c in trace_id) % 10000
            return (hash_val / 10000.0) < self.ratio
        return self._rng.random() < self.ratio
