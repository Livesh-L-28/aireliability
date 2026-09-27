"""Incident lifecycle management and correlation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from aireliability.observability.models import IncidentStatus


class IncidentRecord(BaseModel):
    """Operational incident record."""

    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    title: str
    description: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    tenant_id: str = "default"
    trace_ids: list[str] = Field(default_factory=list)
    execution_ids: list[str] = Field(default_factory=list)
    affected_workers: list[str] = Field(default_factory=list)
    affected_providers: list[str] = Field(default_factory=list)
    related_events: list[str] = Field(default_factory=list)
    status: IncidentStatus = IncidentStatus.DETECTED
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentManager:
    """Manages detection, correlation, acknowledgement, and resolution of incidents."""

    def __init__(self, max_incidents: int = 1000) -> None:
        self.max_incidents = max_incidents
        self._incidents: dict[str, IncidentRecord] = {}

    def create_incident(
        self,
        title: str,
        description: str,
        severity: str = "HIGH",
        tenant_id: str = "default",
        trace_ids: list[str] | None = None,
        execution_ids: list[str] | None = None,
        affected_workers: list[str] | None = None,
        affected_providers: list[str] | None = None,
        related_events: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        """Create and register a new operational incident."""
        incident = IncidentRecord(
            incident_id=str(uuid4()),
            severity=severity,
            title=title,
            description=description,
            tenant_id=tenant_id,
            trace_ids=trace_ids or [],
            execution_ids=execution_ids or [],
            affected_workers=affected_workers or [],
            affected_providers=affected_providers or [],
            related_events=related_events or [],
            status=IncidentStatus.DETECTED,
            metadata=metadata or {},
        )
        self._incidents[incident.incident_id] = incident
        if len(self._incidents) > self.max_incidents:
            oldest_id = next(iter(self._incidents))
            self._incidents.pop(oldest_id, None)
        return incident

    def get_incident(self, incident_id: str) -> IncidentRecord | None:
        """Fetch incident by id."""
        return self._incidents.get(incident_id)

    def list_incidents(
        self,
        tenant_id: str | None = None,
        status: IncidentStatus | None = None,
        limit: int = 100,
    ) -> list[IncidentRecord]:
        """Query incidents with filtering."""
        results = []
        for inc in reversed(list(self._incidents.values())):
            if tenant_id and inc.tenant_id != tenant_id:
                continue
            if status and inc.status != status:
                continue
            results.append(inc)
            if len(results) >= limit:
                break
        return list(reversed(results))

    def acknowledge_incident(self, incident_id: str) -> IncidentRecord | None:
        """Mark incident as acknowledged."""
        inc = self._incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.ACKNOWLEDGED
            inc.acknowledged_at = datetime.now(UTC)
        return inc

    def mitigate_incident(self, incident_id: str) -> IncidentRecord | None:
        """Mark incident as mitigating."""
        inc = self._incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.MITIGATING
        return inc

    def resolve_incident(self, incident_id: str) -> IncidentRecord | None:
        """Mark incident as resolved."""
        inc = self._incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.RESOLVED
            inc.resolved_at = datetime.now(UTC)
        return inc

    def clear(self) -> None:
        """Clear all registered incidents."""
        self._incidents.clear()
