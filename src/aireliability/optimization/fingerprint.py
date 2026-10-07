"""Deterministic configuration fingerprinting ignoring volatile metadata."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aireliability.optimization.models import OptimizationConfiguration

VOLATILE_KEYS = {
    "timestamp",
    "created_at",
    "updated_at",
    "id",
    "candidate_id",
    "optimization_id",
    "execution_id",
    "trace_id",
    "run_id",
    "metadata",
    "duration_seconds",
    "cost",
}


def _canonicalize(val: Any) -> Any:
    """Recursively normalize values into a canonical JSON-serializable representation."""
    if isinstance(val, dict):
        return {
            k: _canonicalize(v)
            for k, v in sorted(val.items())
            if k.lower() not in VOLATILE_KEYS
        }
    if isinstance(val, (list, tuple)):
        return [_canonicalize(v) for v in val]
    if isinstance(val, float):
        # Round to 6 decimals to eliminate machine floating point representation variances
        return round(val, 6)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, str)):
        return val
    if val is None:
        return None
    return str(val)


def compute_configuration_fingerprint(values: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 fingerprint representing actual configuration state.

    Ignores volatile timestamps, run IDs, and execution metadata.
    """
    clean_values = {
        k: _canonicalize(v)
        for k, v in sorted(values.items())
        if k.lower() not in VOLATILE_KEYS
    }
    encoded = json.dumps(clean_values, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"cfg_{h[:16]}"


def create_configuration(
    values: dict[str, Any],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> OptimizationConfiguration:
    """Factory creating an OptimizationConfiguration with an auto-computed fingerprint."""
    fp = compute_configuration_fingerprint(values)
    return OptimizationConfiguration(
        values=dict(values),
        fingerprint=fp,
        description=description,
        metadata=dict(metadata or {}),
    )
