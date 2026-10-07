"""Data models for Reliability Intelligence Dashboard (Phase 43)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "dash") -> str:
    """Generate a unique ID with a given prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


class AlertSeverity(StrEnum):
    """Severity levels for dashboard alerts."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DashboardTimeRange(BaseModel):
    """Temporal range for querying dashboard panels."""

    model_config = ConfigDict(frozen=True)

    start_time: datetime | None = None
    end_time: datetime | None = None
    preset: str = "last_24h"  # last_1h, last_24h, last_7d, last_30d


class DashboardFilter(BaseModel):
    """Filters applied to dashboard telemetry queries."""

    model_config = ConfigDict(frozen=True)

    environment: str | None = None
    target_id: str | None = None
    tenant_id: str | None = None
    severity: AlertSeverity | None = None
    tags: list[str] = Field(default_factory=list)


class DashboardMetric(BaseModel):
    """Individual aggregated metric cell on a dashboard widget."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    value: float
    unit: str = "ratio"
    delta: float | None = None
    status: str = "normal"  # normal, warning, critical


class DashboardWidget(BaseModel):
    """A visual or data widget inside a dashboard panel."""

    model_config = ConfigDict(frozen=True)

    widget_id: str = Field(default_factory=lambda: _generate_id("widg"))
    title: str
    widget_type: str = (
        "stat_card"  # stat_card, timeseries, bar_chart, table, alert_list
    )
    metrics: list[DashboardMetric] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class DashboardPanel(BaseModel):
    """A thematic section grouping related reliability widgets."""

    model_config = ConfigDict(frozen=True)

    panel_id: str = Field(default_factory=lambda: _generate_id("pnl"))
    title: str
    category: str
    widgets: list[DashboardWidget] = Field(default_factory=list)
    description: str = ""


class DashboardLayout(BaseModel):
    """Arrangement metadata for dashboard panels."""

    model_config = ConfigDict(frozen=True)

    columns: int = 12
    panel_order: list[str] = Field(default_factory=list)


class DashboardAlert(BaseModel):
    """Active or historical alert emitted on the dashboard."""

    model_config = ConfigDict(frozen=True)

    alert_id: str = Field(default_factory=lambda: _generate_id("alert"))
    source: str  # safety, prediction, slo, incident, regression, drift
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime = Field(default_factory=_utc_now)
    target_id: str | None = None
    acknowledged: bool = False


class DashboardHealthSummary(BaseModel):
    """Composite enterprise system health summary with hard constraint enforcement."""

    model_config = ConfigDict(frozen=True)

    overall_health: float = Field(ge=0.0, le=1.0)
    health_status: str = "HEALTHY"  # HEALTHY, DEGRADED, CRITICAL, COMPROMISED
    quality_score: float = Field(ge=0.0, le=1.0)
    reliability_score: float = Field(ge=0.0, le=1.0)
    safety_score: float = Field(ge=0.0, le=1.0)
    security_score: float = Field(ge=0.0, le=1.0)
    rag_score: float = Field(ge=0.0, le=1.0)
    agent_score: float = Field(ge=0.0, le=1.0)
    active_incidents_count: int = 0
    active_alerts_count: int = 0
    hard_veto_applied: bool = False


class Dashboard(BaseModel):
    """Full unified reliability intelligence dashboard."""

    model_config = ConfigDict(frozen=True)

    dashboard_id: str = Field(default_factory=lambda: _generate_id("dash"))
    name: str = "Enterprise Reliability Intelligence"
    health_summary: DashboardHealthSummary
    panels: list[DashboardPanel] = Field(default_factory=list)
    alerts: list[DashboardAlert] = Field(default_factory=list)
    layout: DashboardLayout = Field(default_factory=DashboardLayout)
    time_range: DashboardTimeRange = Field(default_factory=DashboardTimeRange)
    filters: DashboardFilter = Field(default_factory=DashboardFilter)
    generated_at: datetime = Field(default_factory=_utc_now)


class DashboardSnapshot(BaseModel):
    """Deterministic frozen snapshot of dashboard state for audits or archival."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str = Field(default_factory=lambda: _generate_id("snap"))
    timestamp: datetime = Field(default_factory=_utc_now)
    health: DashboardHealthSummary
    active_incidents: list[str] = Field(default_factory=list)
    safety_status: str = "SAFE"
    prediction_status: str = "STABLE"
    top_failures: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    def fingerprint(self) -> str:
        """Deterministic fingerprint of this snapshot."""
        data = f"{self.health.overall_health:.4f}:{self.safety_status}:{len(self.active_incidents)}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


class DashboardReport(BaseModel):
    """Human- and machine-readable report generated from dashboard state."""

    report_id: str = Field(default_factory=lambda: _generate_id("drep"))
    dashboard_id: str
    markdown_content: str
    generated_at: datetime = Field(default_factory=_utc_now)
