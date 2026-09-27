"""Provider-neutral replay protection and nonce tracking for Phase 28."""

import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ReplayRecord(BaseModel):
    """Record of an evaluated request or nonce."""

    model_config = ConfigDict(frozen=True)

    record_id: str = Field(default_factory=lambda: f"rep_{uuid4().hex[:16]}")
    request_id: str
    nonce: str | None = None
    principal_id: str = "anonymous"
    timestamp: float = Field(default_factory=time.time)


class ReplayProtection:
    """Detects repeated request IDs, nonces, and timestamp skew within a sliding window.

    Provider-neutral in-memory implementation with storage interface support.
    Does not require Redis or external infrastructure.
    """

    def __init__(
        self,
        window_seconds: float = 300.0,  # 5 minutes replay window
        max_skew_seconds: float = 60.0,  # Allow 60s future/past clock drift
        storage: Any | None = None,
    ) -> None:
        self.window_seconds = window_seconds
        self.max_skew_seconds = max_skew_seconds
        self.storage = storage
        self._seen_requests: dict[str, float] = {}
        self._seen_nonces: dict[str, float] = {}
        self._last_cleanup = 0.0

    def _cleanup_expired(self, current_time: float) -> None:
        """Evict records older than window_seconds if interval elapsed."""
        if current_time - self._last_cleanup < 1.0:
            return
        self._last_cleanup = current_time
        cutoff = current_time - self.window_seconds
        self._seen_requests = {
            rid: ts for rid, ts in self._seen_requests.items() if ts > cutoff
        }
        self._seen_nonces = {
            n: ts for n, ts in self._seen_nonces.items() if ts > cutoff
        }

    def check_and_record(
        self,
        request_id: str,
        nonce: str | None = None,
        request_timestamp: float | None = None,
        principal_id: str = "anonymous",
    ) -> tuple[bool, str | None]:
        """Validate request against replay window and record nonce.

        Returns:
            (is_valid, rejection_reason_if_any)
        """
        now = time.time()
        self._cleanup_expired(now)

        # 1. Timestamp validation (prevent stale or far-future replays)
        if request_timestamp is not None:
            if request_timestamp < (now - self.window_seconds):
                age = now - request_timestamp
                return (
                    False,
                    f"Request timestamp expired ({age:.1f}s older than "
                    f"window {self.window_seconds}s).",
                )
            if request_timestamp > (now + self.max_skew_seconds):
                drift = request_timestamp - now
                return (
                    False,
                    f"Request timestamp in future ({drift:.1f}s exceeds "
                    f"max skew {self.max_skew_seconds}s).",
                )

        # 2. Duplicate Request ID check
        if request_id in self._seen_requests:
            return False, f"Replay detected: duplicate request_id '{request_id}'."

        # 3. Duplicate Nonce check (scoped by principal if provided)
        if nonce is not None:
            nonce_key = f"{principal_id}:{nonce}"
            if nonce_key in self._seen_nonces:
                return False, f"Replay detected: duplicate nonce '{nonce}'."
            self._seen_nonces[nonce_key] = now

        # Record accepted request ID
        self._seen_requests[request_id] = now

        # Optionally persist replay record
        if self.storage and hasattr(self.storage, "save_replay_record"):
            rec = ReplayRecord(
                request_id=request_id,
                nonce=nonce,
                principal_id=principal_id,
                timestamp=now,
            )
            self.storage.save_replay_record(rec)

        return True, None

    def get_stats(self) -> dict[str, Any]:
        """Return memory statistics for replay protection."""
        return {
            "tracked_requests": len(self._seen_requests),
            "tracked_nonces": len(self._seen_nonces),
            "window_seconds": self.window_seconds,
        }
