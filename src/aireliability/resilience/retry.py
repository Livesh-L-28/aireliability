"""Resilient retry policies and backoff calculations with jitter."""

import random
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from aireliability.resilience.models import DetailedFailureRecord


class ResilienceBackoffStrategy(StrEnum):
    """Backoff strategies for resilient job retries."""

    NONE = "none"
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


class ResilientRetryPolicy(BaseModel):
    """Production-grade retry policy with configurable backoff and failure checks."""

    model_config = ConfigDict(frozen=True)

    max_retries: int = 3
    strategy: ResilienceBackoffStrategy = ResilienceBackoffStrategy.EXPONENTIAL_JITTER
    initial_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 60.0
    jitter_factor: float = 0.25  # +/- 25% jitter

    def is_retryable(self, failure: DetailedFailureRecord) -> bool:
        """Evaluate whether a structured failure record is eligible for retry."""
        return bool(failure.retryable and failure.attempt <= self.max_retries)

    def compute_delay(self, attempt: int, seed: int | None = None) -> float:
        """Compute the backoff delay in seconds for an attempt number."""
        if self.strategy == ResilienceBackoffStrategy.NONE or attempt <= 1:
            return 0.0

        if self.strategy == ResilienceBackoffStrategy.FIXED:
            return min(self.initial_delay_seconds, self.max_delay_seconds)

        if self.strategy == ResilienceBackoffStrategy.LINEAR:
            delay = self.initial_delay_seconds * max(1, attempt - 1)
            return min(delay, self.max_delay_seconds)

        if self.strategy in (
            ResilienceBackoffStrategy.EXPONENTIAL,
            ResilienceBackoffStrategy.EXPONENTIAL_JITTER,
        ):
            exponent = max(0, attempt - 2)
            base_delay = self.initial_delay_seconds * (self.backoff_factor**exponent)
            capped_delay = min(base_delay, self.max_delay_seconds)

            if self.strategy == ResilienceBackoffStrategy.EXPONENTIAL_JITTER:
                rng = random.Random(seed) if seed is not None else random
                jitter_range = capped_delay * self.jitter_factor
                jitter = rng.uniform(-jitter_range, jitter_range)
                return max(0.0, min(self.max_delay_seconds, capped_delay + jitter))

            return capped_delay

        return 0.0
