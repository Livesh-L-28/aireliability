"""Provider-neutral and worker-safe Circuit Breaker."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from aireliability.resilience.models import CircuitState


class CircuitBreakerOpenError(RuntimeError):
    """Raised when an operation is rejected because the circuit breaker is OPEN."""


class CircuitBreaker:
    """Standard 3-state Circuit Breaker (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)."""

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_probe_count: int = 2,
        success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout_seconds = max(0.001, recovery_timeout_seconds)
        self.half_open_probe_count = max(1, half_open_probe_count)
        self.success_threshold = max(1, success_threshold)

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_state_change: datetime = datetime.now(UTC)
        self._probes_in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current state, dynamically evaluating recovery timeout if OPEN."""
        if self._state == CircuitState.OPEN:
            elapsed = (datetime.now(UTC) - self._last_state_change).total_seconds()
            if elapsed >= self.recovery_timeout_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    async def can_execute(self) -> bool:
        """Check if an execution attempt is allowed under current circuit state."""
        async with self._lock:
            current = self.state
            if current == CircuitState.CLOSED:
                return True
            if current == CircuitState.OPEN:
                return False
            # HALF_OPEN: allow bounded number of probe executions
            if self._state == CircuitState.OPEN:
                # Transition internally to HALF_OPEN
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                self._probes_in_flight = 0

            if self._probes_in_flight < self.half_open_probe_count:
                self._probes_in_flight += 1
                return True
            return False

    async def record_success(self) -> None:
        """Record successful execution attempt."""
        async with self._lock:
            current = self.state
            if (
                current == CircuitState.HALF_OPEN
                or self._state == CircuitState.HALF_OPEN
            ):
                self._success_count += 1
                if self._probes_in_flight > 0:
                    self._probes_in_flight -= 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif current == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self, error: Any = None) -> None:
        """Record a failed execution attempt."""
        async with self._lock:
            current = self.state
            if (
                current in (CircuitState.HALF_OPEN, CircuitState.OPEN)
                or self._state == CircuitState.HALF_OPEN
            ):
                # Failure in HALF_OPEN resets back to OPEN
                self._transition_to(CircuitState.OPEN)
            else:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        self._state = new_state
        self._last_state_change = datetime.now(UTC)
        self._probes_in_flight = 0
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.OPEN:
            self._success_count = 0

    def reset(self) -> None:
        """Manually reset the circuit breaker back to CLOSED state."""
        self._transition_to(CircuitState.CLOSED)
