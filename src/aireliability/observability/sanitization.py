"""Privacy-aware telemetry sanitization."""

from __future__ import annotations

from typing import Any

from aireliability.telemetry.sanitizer import DEFAULT_SENSITIVE_KEYS, SanitizationPolicy


class TelemetrySanitizer:
    """Sanitizer for observability attributes, payloads, and events."""

    def __init__(
        self,
        policy: SanitizationPolicy | None = None,
        extra_sensitive_keys: set[str] | None = None,
    ) -> None:
        self.policy = policy or SanitizationPolicy()
        self.sensitive_keys = set(DEFAULT_SENSITIVE_KEYS)
        if extra_sensitive_keys:
            self.sensitive_keys.update(k.lower() for k in extra_sensitive_keys)

    def sanitize(self, value: Any, depth: int = 0, max_depth: int = 8) -> Any:
        """Recursively sanitize data structures."""
        if depth > max_depth or value is None:
            return value

        # Delegate to underlying SanitizationPolicy
        return self.policy.sanitize(value)
