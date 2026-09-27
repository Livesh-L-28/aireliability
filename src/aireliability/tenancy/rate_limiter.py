"""Deterministic rate limiting algorithms: fixed window, sliding window,
and token bucket.
"""

import asyncio
import time
from collections import deque

from aireliability.tenancy.models import (
    RateLimitAlgorithm,
    RateLimitDecision,
    RateLimitPolicy,
)


class RateLimiter:
    """Multi-scope rate limiter supporting fixed-window, sliding-window,
    and token-bucket.
    """

    def __init__(self, default_policy: RateLimitPolicy | None = None) -> None:
        self.default_policy = default_policy or RateLimitPolicy()
        self._policies: dict[str, RateLimitPolicy] = {}

        # State storage
        self._fixed_windows: dict[str, tuple[float, int]] = {}
        self._sliding_windows: dict[str, deque[float]] = {}
        self._token_buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    def set_policy(self, scope_key: str, policy: RateLimitPolicy) -> None:
        """Assign a specific rate limiting policy to a tenant or scope."""
        self._policies[scope_key] = policy

    def get_policy(self, scope_key: str) -> RateLimitPolicy:
        """Retrieve rate limit policy for scope, falling back to default."""
        return self._policies.get(scope_key, self.default_policy)

    def check_sync(
        self, scope_key: str, cost: float = 1.0, now: float | None = None
    ) -> RateLimitDecision:
        """Synchronously inspect and consume rate limit tokens for a scope."""
        current_time = now if now is not None else time.time()
        policy = self.get_policy(scope_key)

        if policy.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            return self._check_fixed_window(scope_key, policy, cost, current_time)
        elif policy.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            return self._check_sliding_window(scope_key, policy, cost, current_time)
        else:
            return self._check_token_bucket(scope_key, policy, cost, current_time)

    async def check(
        self, scope_key: str, cost: float = 1.0, now: float | None = None
    ) -> RateLimitDecision:
        """Inspect and consume rate limit tokens for a scope."""
        async with self._lock:
            return self.check_sync(scope_key, cost, now)

    def _check_fixed_window(
        self, scope_key: str, policy: RateLimitPolicy, cost: float, now: float
    ) -> RateLimitDecision:
        window_start, count = self._fixed_windows.get(scope_key, (now, 0))
        if now - window_start >= policy.window_seconds:
            window_start = now
            count = 0

        if count + cost > policy.rate:
            reset_after = max(0.0, policy.window_seconds - (now - window_start))
            return RateLimitDecision(
                allowed=False,
                remaining_tokens=max(0.0, policy.rate - count),
                reset_after_seconds=reset_after,
                reason=(
                    f"Fixed-window rate limit exceeded "
                    f"({count + cost:.0f}/{policy.rate:.0f} "
                    f"per {policy.window_seconds:.0f}s)"
                ),
            )

        count += int(cost)
        self._fixed_windows[scope_key] = (window_start, count)
        return RateLimitDecision(
            allowed=True,
            remaining_tokens=max(0.0, policy.rate - count),
            reset_after_seconds=max(0.0, policy.window_seconds - (now - window_start)),
        )

    def _check_sliding_window(
        self, scope_key: str, policy: RateLimitPolicy, cost: float, now: float
    ) -> RateLimitDecision:
        if scope_key not in self._sliding_windows:
            self._sliding_windows[scope_key] = deque()
        timestamps = self._sliding_windows[scope_key]

        cutoff = now - policy.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) + cost > policy.rate:
            oldest = timestamps[0] if timestamps else now
            reset_after = max(0.0, policy.window_seconds - (now - oldest))
            return RateLimitDecision(
                allowed=False,
                remaining_tokens=max(0.0, policy.rate - len(timestamps)),
                reset_after_seconds=reset_after,
                reason=(
                    f"Sliding-window rate limit exceeded ({len(timestamps) + cost:.0f}/"
                    f"{policy.rate:.0f} in rolling {policy.window_seconds:.0f}s)"
                ),
            )

        for _ in range(int(cost)):
            timestamps.append(now)
        return RateLimitDecision(
            allowed=True,
            remaining_tokens=max(0.0, policy.rate - len(timestamps)),
            reset_after_seconds=0.0,
        )

    def _check_token_bucket(
        self, scope_key: str, policy: RateLimitPolicy, cost: float, now: float
    ) -> RateLimitDecision:
        burst = policy.burst_capacity or policy.rate
        refill_rate = policy.rate / policy.window_seconds  # tokens per second

        tokens, last_refill = self._token_buckets.get(scope_key, (burst, now))
        elapsed = max(0.0, now - last_refill)
        tokens = min(burst, tokens + elapsed * refill_rate)
        last_refill = now

        if tokens < cost:
            deficit = cost - tokens
            reset_after = deficit / refill_rate if refill_rate > 0 else 0.0
            self._token_buckets[scope_key] = (tokens, last_refill)
            return RateLimitDecision(
                allowed=False,
                remaining_tokens=max(0.0, tokens),
                reset_after_seconds=reset_after,
                reason=(
                    f"Token-bucket capacity exhausted ({tokens:.2f} tokens available, "
                    f"{cost:.2f} requested)"
                ),
            )

        tokens -= cost
        self._token_buckets[scope_key] = (tokens, last_refill)
        return RateLimitDecision(
            allowed=True,
            remaining_tokens=tokens,
            reset_after_seconds=0.0,
        )

    async def reset(self, scope_key: str | None = None) -> None:
        """Reset rate limiter state for a scope or entirely."""
        async with self._lock:
            if scope_key:
                self._fixed_windows.pop(scope_key, None)
                self._sliding_windows.pop(scope_key, None)
                self._token_buckets.pop(scope_key, None)
            else:
                self._fixed_windows.clear()
                self._sliding_windows.clear()
                self._token_buckets.clear()
