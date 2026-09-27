"""Tenant-aware and weighted fair scheduling policies."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from aireliability.control_plane.models import ScheduledJob
from aireliability.tenancy.models import DEFAULT_TENANT_ID


class TenantFairSchedulingPolicy:
    """Fair scheduling across tenants preventing single-tenant queue dominance.

    Round-robins / balances selection across tenants based on recent dispatch counts.
    """

    def __init__(self) -> None:
        self._tenant_dispatch_counts: dict[str, int] = defaultdict(int)

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        current_time = now or datetime.now(UTC)
        eligible = [j for j in candidates if j.is_eligible_at(current_time)]
        if not eligible:
            return None

        # Group eligible jobs by tenant
        by_tenant: dict[str, list[ScheduledJob]] = defaultdict(list)
        for j in eligible:
            t_id = (
                j.metadata.get("tenant_id")
                or getattr(j, "tenant_id", None)
                or DEFAULT_TENANT_ID
            )
            by_tenant[t_id].append(j)

        # Select tenant with least dispatches among active candidate tenants
        sorted_tenants = sorted(
            by_tenant.keys(),
            key=lambda t: (self._tenant_dispatch_counts[t], t),
        )

        chosen_tenant = sorted_tenants[0]
        tenant_candidates = by_tenant[chosen_tenant]

        # Within the tenant, sort by priority, wait time, job_id
        selected = min(
            tenant_candidates,
            key=lambda j: (
                int(j.priority),
                j.queued_at or j.created_at,
                j.job_id,
            ),
        )

        self._tenant_dispatch_counts[chosen_tenant] += 1
        return selected


class WeightedTenantSchedulingPolicy:
    """Allocates execution opportunities proportionally to configured tenant weights."""

    def __init__(self, tenant_weights: dict[str, float] | None = None) -> None:
        self.tenant_weights = tenant_weights or {}
        self._tenant_opportunity_used: dict[str, float] = defaultdict(float)

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        current_time = now or datetime.now(UTC)
        eligible = [j for j in candidates if j.is_eligible_at(current_time)]
        if not eligible:
            return None

        by_tenant: dict[str, list[ScheduledJob]] = defaultdict(list)
        for j in eligible:
            t_id = (
                j.metadata.get("tenant_id")
                or getattr(j, "tenant_id", None)
                or DEFAULT_TENANT_ID
            )
            by_tenant[t_id].append(j)

        # Cost normalized by weight: used_score / weight
        def score(t_id: str) -> tuple[float, float, str]:
            w = max(0.1, self.tenant_weights.get(t_id, 1.0))
            return (self._tenant_opportunity_used[t_id] / w, -w, t_id)

        sorted_tenants = sorted(by_tenant.keys(), key=score)
        chosen_tenant = sorted_tenants[0]
        tenant_candidates = by_tenant[chosen_tenant]

        selected = min(
            tenant_candidates,
            key=lambda j: (
                int(j.priority),
                j.queued_at or j.created_at,
                j.job_id,
            ),
        )

        self._tenant_opportunity_used[chosen_tenant] += 1.0
        return selected


class TenantPriorityPolicy:
    """Strict tenant priority: high priority jobs across all tenants execute first,
    tie-breaking by tenant scheduling weight then age.
    """

    def __init__(self, tenant_weights: dict[str, float] | None = None) -> None:
        self.tenant_weights = tenant_weights or {}

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        current_time = now or datetime.now(UTC)
        eligible = [j for j in candidates if j.is_eligible_at(current_time)]
        if not eligible:
            return None

        def sort_key(j: ScheduledJob) -> tuple[int, float, datetime, str]:
            t_id = (
                j.metadata.get("tenant_id")
                or getattr(j, "tenant_id", None)
                or DEFAULT_TENANT_ID
            )
            w = max(0.1, self.tenant_weights.get(t_id, 1.0))
            # Lower priority integer = higher priority.
            # Higher weight = earlier opportunity (-w).
            return (
                int(j.priority),
                -w,
                j.queued_at or j.created_at,
                j.job_id,
            )

        return min(eligible, key=sort_key)
