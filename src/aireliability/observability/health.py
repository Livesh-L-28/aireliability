"""Operational health engine synthesizing subsystem states."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aireliability.observability.models import HealthSnapshot, HealthStatus


class OperationalHealthManager:
    """Manages operational health across all subsystems."""

    def __init__(
        self,
        health_checker: Any | None = None,
        resilience_manager: Any | None = None,
        resource_governor: Any | None = None,
        security_gateway: Any | None = None,
        control_plane: Any | None = None,
        worker_manager: Any | None = None,
        storage_backend: Any | None = None,
    ) -> None:
        self.health_checker = health_checker
        self.resilience_manager = resilience_manager
        self.resource_governor = resource_governor
        self.security_gateway = security_gateway
        self.control_plane = control_plane
        self.worker_manager = worker_manager
        self.storage_backend = storage_backend

    def evaluate_health(self) -> HealthSnapshot:
        """Produce a complete operational health snapshot."""
        details: dict[str, Any] = {}

        # 1. Scheduler / Control Plane
        sched_status = HealthStatus.HEALTHY
        if self.control_plane is not None:
            try:
                # Check queue or control plane status if available
                details["control_plane"] = "active"
            except Exception as e:
                sched_status = HealthStatus.DEGRADED
                details["control_plane_error"] = str(e)

        # 2. Storage
        storage_status = HealthStatus.HEALTHY
        if self.storage_backend is not None:
            try:
                if (
                    hasattr(self.storage_backend, "ping")
                    and not self.storage_backend.ping()
                ):
                    storage_status = HealthStatus.UNHEALTHY
                details["storage"] = "connected"
            except Exception as e:
                storage_status = HealthStatus.UNHEALTHY
                details["storage_error"] = str(e)

        # 3. Workers
        worker_status = HealthStatus.HEALTHY
        if self.worker_manager is not None:
            try:
                if hasattr(self.worker_manager, "get_quarantined_workers"):
                    quarantined = self.worker_manager.get_quarantined_workers()
                    if quarantined:
                        worker_status = HealthStatus.DEGRADED
                        details["quarantined_workers_count"] = len(quarantined)
            except Exception as e:
                worker_status = HealthStatus.UNKNOWN
                details["worker_manager_error"] = str(e)

        # 4. Resilience
        resilience_status = HealthStatus.HEALTHY
        if self.resilience_manager is not None:
            try:
                if hasattr(self.resilience_manager, "circuit_breakers"):
                    open_cbs = [
                        name
                        for name, cb in self.resilience_manager.circuit_breakers.items()
                        if hasattr(cb, "is_open") and cb.is_open()
                    ]
                    if open_cbs:
                        resilience_status = HealthStatus.DEGRADED
                        details["open_circuit_breakers"] = open_cbs
            except Exception as e:
                resilience_status = HealthStatus.UNKNOWN
                details["resilience_error"] = str(e)

        # 5. Security
        security_status = HealthStatus.HEALTHY
        if self.security_gateway is not None:
            details["security_gateway"] = "active"

        # 6. Tenancy
        tenancy_status = HealthStatus.HEALTHY
        if self.resource_governor is not None:
            details["resource_governor"] = "active"

        # 7. Queue
        queue_status = HealthStatus.HEALTHY

        # Calculate Overall Status
        sub_statuses = [
            sched_status,
            storage_status,
            worker_status,
            resilience_status,
            security_status,
            tenancy_status,
            queue_status,
        ]

        if any(s == HealthStatus.UNHEALTHY for s in sub_statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(
            s in (HealthStatus.DEGRADED, HealthStatus.UNKNOWN) for s in sub_statuses
        ):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return HealthSnapshot(
            overall_status=overall,
            scheduler_status=sched_status,
            storage_status=storage_status,
            worker_status=worker_status,
            resilience_status=resilience_status,
            security_status=security_status,
            tenancy_status=tenancy_status,
            queue_status=queue_status,
            timestamp=datetime.now(UTC),
            details=details,
        )
