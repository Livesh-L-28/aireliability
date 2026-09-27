"""Configurable privacy policies and recursive data sanitization for telemetry."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "token",
        "secret",
        "password",
        "authorization",
        "auth",
        "access_token",
        "refresh_token",
        "private_key",
        "bearer",
        "credentials",
        "client_secret",
    }
)


@dataclass(frozen=True)
class SanitizationPolicy:
    """Policy rules governing what sensitive data is redacted or omitted in telemetry.

    Attributes:
        sensitive_keys: Set of lowercase field names that must be redacted.
        redaction_text: Replacement text for redacted values.
        log_full_prompts: If False (default), prompts are truncated or omitted.
        log_full_completions: If False (default), completions are truncated or omitted.
        max_string_length: Maximum length for string attributes before truncation.
    """

    sensitive_keys: frozenset[str] = DEFAULT_SENSITIVE_KEYS
    redaction_text: str = "[REDACTED]"
    log_full_prompts: bool = False
    log_full_completions: bool = False
    max_string_length: int = 2000

    def is_sensitive_key(self, key: str) -> bool:
        """Check if key name matches any known sensitive keyword."""
        lowered = key.lower()
        if lowered in self.sensitive_keys:
            return True
        return any(sens in lowered for sens in self.sensitive_keys)

    def sanitize(self, data: Any, key_context: str | None = None) -> Any:
        """Recursively sanitize data structures (dicts, lists, primitives)."""
        if data is None:
            return None

        # Check key context if provided
        if key_context and self.is_sensitive_key(key_context):
            return self.redaction_text

        if isinstance(data, str):
            # Check if this string contains auth headers or tokens
            if key_context and self.is_sensitive_key(key_context):
                return self.redaction_text
            if len(data) > self.max_string_length:
                return data[: self.max_string_length] + " [TRUNCATED]"
            return data

        if isinstance(data, Mapping):
            sanitized: dict[str, Any] = {}
            for k, v in data.items():
                k_str = str(k)
                if self.is_sensitive_key(k_str):
                    sanitized[k_str] = self.redaction_text
                else:
                    sanitized[k_str] = self.sanitize(v, key_context=k_str)
            return sanitized

        if isinstance(data, (list, tuple, set)):
            return [self.sanitize(item, key_context=key_context) for item in data]

        if hasattr(data, "model_dump") and callable(data.model_dump):
            return self.sanitize(data.model_dump(), key_context=key_context)

        if hasattr(data, "__dict__"):
            return self.sanitize(vars(data), key_context=key_context)

        return data
