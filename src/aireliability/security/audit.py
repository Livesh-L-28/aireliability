"""Structured security audit events and AuditLogger for Phase 28."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.security.models import _utc_now
from aireliability.telemetry.sanitizer import SanitizationPolicy
from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)


class AuditEvent(BaseModel):
    """Immutable audit trail record for security-sensitive operations.

    Never contains raw secrets, unhashed keys, or plaintext bearer tokens.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: f"audit_{uuid4().hex[:16]}")
    timestamp: datetime = Field(default_factory=_utc_now)
    principal_id: str = "anonymous"
    tenant_id: str = DEFAULT_TENANT_ID
    project_id: str = DEFAULT_PROJECT_ID
    namespace: str = DEFAULT_NAMESPACE
    action: str = ""
    resource: str = ""
    result: str = "allowed"  # allowed, denied, failure, success
    reason: str | None = None
    request_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogger:
    """Records sanitized security audit events to memory and optional storage."""

    def __init__(
        self,
        storage: Any | None = None,
        sanitizer: SanitizationPolicy | None = None,
    ) -> None:
        self.storage = storage
        self.sanitizer = sanitizer or SanitizationPolicy()
        self._memory_events: list[AuditEvent] = []

    def record(
        self,
        action: str,
        result: str,
        principal_id: str = "anonymous",
        tenant_id: str = DEFAULT_TENANT_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        namespace: str = DEFAULT_NAMESPACE,
        resource: str = "",
        reason: str | None = None,
        request_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Create, sanitize, and record an audit event."""
        sanitized_meta = self.sanitizer.sanitize(metadata or {})
        # Extra redaction safeguard: strip any accidentally passed key fields
        for sensitive_key in ("api_key", "secret", "bearer_token", "token", "password"):
            sanitized_meta.pop(sensitive_key, None)

        event = AuditEvent(
            action=action,
            result=result,
            principal_id=principal_id,
            tenant_id=tenant_id,
            project_id=project_id,
            namespace=namespace,
            resource=resource,
            reason=reason,
            request_id=request_id,
            metadata=sanitized_meta,
        )

        self._memory_events.append(event)
        if self.storage and hasattr(self.storage, "save_audit_event"):
            self.storage.save_audit_event(event)

        return event

    def list_events(
        self,
        tenant_id: str | None = None,
        principal_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query recorded audit events matching filters."""
        if self.storage and hasattr(self.storage, "list_audit_events"):
            return self.storage.list_audit_events(
                tenant_id=tenant_id,
                principal_id=principal_id,
                action=action,
                limit=limit,
            )

        events = list(self._memory_events)
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if principal_id:
            events = [e for e in events if e.principal_id == principal_id]
        if action:
            events = [e for e in events if e.action == action]
        return events[-limit:]
