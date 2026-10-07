"""Reliability Intelligence Dashboard module (Phase 43)."""

from aireliability.dashboard.health import ReliabilityHealthCalculator
from aireliability.dashboard.models import (
    AlertSeverity,
    Dashboard,
    DashboardAlert,
    DashboardFilter,
    DashboardHealthSummary,
    DashboardLayout,
    DashboardMetric,
    DashboardPanel,
    DashboardReport,
    DashboardSnapshot,
    DashboardTimeRange,
    DashboardWidget,
)
from aireliability.dashboard.panels import DashboardPanelBuilder
from aireliability.dashboard.service import (
    DashboardBuilder,
    DashboardQuery,
    DashboardRegistry,
    DashboardService,
)

__all__ = [
    "AlertSeverity",
    "Dashboard",
    "DashboardAlert",
    "DashboardBuilder",
    "DashboardFilter",
    "DashboardHealthSummary",
    "DashboardLayout",
    "DashboardMetric",
    "DashboardPanel",
    "DashboardPanelBuilder",
    "DashboardQuery",
    "DashboardRegistry",
    "DashboardReport",
    "DashboardService",
    "DashboardSnapshot",
    "DashboardTimeRange",
    "DashboardWidget",
    "ReliabilityHealthCalculator",
]
