"""Security event constants and structured telemetry emitters for Phase 28."""

from typing import Any

from aireliability.telemetry.collector import TelemetryCollector

# Security Event Types
EVT_AUTH_SUCCESS = "security.authentication_success"
EVT_AUTH_FAILURE = "security.authentication_failure"
EVT_AUTHZ_ALLOWED = "security.authorization_allowed"
EVT_AUTHZ_DENIED = "security.authorization_denied"
EVT_KEY_CREATED = "security.api_key_created"
EVT_KEY_REVOKED = "security.api_key_revoked"
EVT_KEY_ROTATED = "security.api_key_rotated"
EVT_REPLAY_DETECTED = "security.replay_detected"
EVT_RATE_LIMIT_TRIGGERED = "security.rate_limit_triggered"
EVT_BOUNDARY_VIOLATION = "security.tenant_boundary_violation"
EVT_VALIDATION_FAILURE = "security.request_validation_failure"


class SecurityTelemetry:
    """Emits structured security events to telemetry collectors and Prometheus."""

    def __init__(
        self,
        collector: TelemetryCollector | None = None,
        metrics: Any | None = None,
    ) -> None:
        self.collector = collector
        self.metrics = metrics

    def emit(
        self,
        event_name: str,
        principal_id: str = "anonymous",
        tenant_id: str = "default",
        action: str = "",
        result: str = "success",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit telemetry event and increment corresponding Prometheus metrics."""
        payload = {
            "principal_id": principal_id,
            "tenant_id": tenant_id,
            "action": action,
            "result": result,
            **(details or {}),
        }

        # 1. Structured Collector telemetry
        if self.collector and hasattr(self.collector, "record_event"):
            from aireliability.telemetry.events import TelemetryEvent

            self.collector.record_event(
                TelemetryEvent(name=event_name, payload=payload)
            )

        # 2. Prometheus metrics
        if self.metrics and getattr(self.metrics, "enabled", False):
            m = self.metrics
            if event_name == EVT_AUTH_SUCCESS and hasattr(m, "record_auth_attempt"):
                m.record_auth_attempt(success=True)
            elif event_name == EVT_AUTH_FAILURE and hasattr(m, "record_auth_attempt"):
                m.record_auth_attempt(success=False)
            elif event_name == EVT_AUTHZ_DENIED and hasattr(m, "record_authz_denial"):
                m.record_authz_denial()
            elif event_name == EVT_KEY_CREATED and hasattr(m, "record_api_key_created"):
                m.record_api_key_created()
            elif event_name == EVT_KEY_REVOKED and hasattr(m, "record_api_key_revoked"):
                m.record_api_key_revoked()
            elif event_name == EVT_REPLAY_DETECTED and hasattr(
                m, "record_replay_attempt"
            ):
                m.record_replay_attempt()
            elif event_name == EVT_RATE_LIMIT_TRIGGERED and hasattr(
                m, "record_security_rate_limit"
            ):
                m.record_security_rate_limit()
            elif event_name == EVT_BOUNDARY_VIOLATION and hasattr(
                m, "record_tenant_boundary_violation"
            ):
                m.record_tenant_boundary_violation()
