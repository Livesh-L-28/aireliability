"""Optional Redis queue and coordination integration for distributed AI reliability.

Requires: pip install 'aireliability[redis]'.
"""

import importlib.util

from aireliability.distributed.models import ReliabilityJob

__all__ = [
    "RedisDistributedCoordinator",
    "ReliabilityJob",
]

REDIS_AVAILABLE = bool(importlib.util.find_spec("redis"))


class RedisDistributedCoordinator:
    """Optional Redis-backed coordinator for distributed job claiming and locking."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis coordinator requires 'redis'. "
                "Install with: pip install 'aireliability[redis]'"
            )
        self.redis_url = redis_url

    def claim_job(self, job_id: str, worker_id: str, ttl_seconds: int = 30) -> bool:
        raise NotImplementedError("Redis integration is an optional backend.")
