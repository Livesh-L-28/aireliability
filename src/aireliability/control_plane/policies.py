"""Scheduling policies for job selection and dispatch order.

Implements:
- FIFO: First queued job executes first.
- Priority: Higher priority first (CRITICAL > HIGH > NORMAL > LOW), older first.
- FairScheduling: Prevents low-priority starvation by aging queued jobs.
- RetryAwareScheduling: Balances retried jobs against new job submissions.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from aireliability.control_plane.models import ScheduledJob


class SchedulingPolicy(Protocol):
    """Protocol for selecting the next job to schedule from candidates."""

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        """Select the next job that should be scheduled, or None if none eligible."""
        ...


class FIFOPolicy:
    """First-In, First-Out: older queued jobs execute first."""

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        current_time = now or datetime.now(UTC)
        eligible = [j for j in candidates if j.is_eligible_at(current_time)]
        if not eligible:
            return None
        # Sort by queued_at / created_at, then deterministic job_id tie breaker
        return min(
            eligible,
            key=lambda j: (j.queued_at or j.created_at, j.job_id),
        )


class PriorityPolicy:
    """Strict priority ordering (CRITICAL=0 > HIGH=1 > NORMAL=2 > LOW=3).

    Tie-breaking: earlier queued_at/created_at first, then job_id string sorting.
    """

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        current_time = now or datetime.now(UTC)
        eligible = [j for j in candidates if j.is_eligible_at(current_time)]
        if not eligible:
            return None
        return min(
            eligible,
            key=lambda j: (
                int(j.priority),
                j.queued_at or j.created_at,
                j.job_id,
            ),
        )


class FairSchedulingPolicy:
    """Fair scheduling policy that boosts the priority of aged low-priority jobs.

    If a job has waited in the queue for longer than aging_threshold_seconds,
    its effective priority is upgraded by 1 tier for every aging interval,
    preventing low-priority starvation under high critical load.
    """

    def __init__(self, aging_threshold_seconds: float = 10.0) -> None:
        self.aging_threshold_seconds = max(0.1, aging_threshold_seconds)

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        current_time = now or datetime.now(UTC)
        eligible = [j for j in candidates if j.is_eligible_at(current_time)]
        if not eligible:
            return None

        def effective_priority(job: ScheduledJob) -> tuple[int, datetime, str]:
            q_time = job.queued_at or job.created_at
            waited_sec = max(0.0, (current_time - q_time).total_seconds())
            age_boost = int(waited_sec // self.aging_threshold_seconds)
            # Boost priority towards CRITICAL (0), minimum priority is 0
            boosted = max(0, int(job.priority) - age_boost)
            return (boosted, q_time, job.job_id)

        return min(eligible, key=effective_priority)


class RetryAwareSchedulingPolicy:
    """Balances retry attempts with freshly submitted jobs.

    Gives retrying jobs fair opportunity without letting a repeatedly failing job
    monopolize workers and starve newly submitted fresh jobs.
    """

    def __init__(
        self,
        base_priority_policy: SchedulingPolicy | None = None,
        retry_penalty_weight: float = 0.5,
    ) -> None:
        self.base_policy = base_priority_policy or PriorityPolicy()
        self.retry_penalty_weight = retry_penalty_weight

    def select_next(
        self, candidates: Sequence[ScheduledJob], now: datetime | None = None
    ) -> ScheduledJob | None:
        current_time = now or datetime.now(UTC)
        eligible = [j for j in candidates if j.is_eligible_at(current_time)]
        if not eligible:
            return None

        def rank(job: ScheduledJob) -> tuple[float, datetime, str]:
            q_time = job.queued_at or job.created_at
            # Attempt 1 -> penalty 0; Attempt 2 -> penalty 0.5; etc.
            attempt_penalty = max(0, job.attempt - 1) * self.retry_penalty_weight
            effective_score = float(int(job.priority)) + attempt_penalty
            return (effective_score, q_time, job.job_id)

        return min(eligible, key=rank)


def get_scheduling_policy(name: str) -> SchedulingPolicy:
    """Factory helper to obtain a SchedulingPolicy by name."""
    cleaned = name.strip().lower()
    if cleaned == "fifo":
        return FIFOPolicy()
    if cleaned == "priority":
        return PriorityPolicy()
    if cleaned in ("fair", "fairness", "fair_scheduling"):
        return FairSchedulingPolicy()
    if cleaned in ("retry_aware", "retry"):
        return RetryAwareSchedulingPolicy()
    raise ValueError(
        f"Unknown scheduling policy '{name}'. "
        "Valid options: fifo, priority, fair, retry_aware"
    )
