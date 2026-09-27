"""In-process metrics engine, percentiles, and Prometheus renderer."""

from __future__ import annotations

import math
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from aireliability.observability.context import get_current_context
from aireliability.observability.models import MetricSample


def _labels_to_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Convert label dict to hashable sorted tuple."""
    return tuple(sorted(labels.items()))


def calculate_percentiles(values: list[float]) -> dict[str, float]:
    """Calculate p50, p90, p95, p99, min, max, mean, count from numeric samples."""
    if not values:
        return {
            "count": 0.0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _percentile(p: float) -> float:
        if n == 1:
            return sorted_vals[0]
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return d0 + d1

    return {
        "count": float(n),
        "min": float(sorted_vals[0]),
        "max": float(sorted_vals[-1]),
        "mean": float(sum(sorted_vals) / n),
        "p50": float(_percentile(0.50)),
        "p90": float(_percentile(0.90)),
        "p95": float(_percentile(0.95)),
        "p99": float(_percentile(0.99)),
    }


class Counter:
    """Monotonically increasing counter with label support."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = {}

    def increment(self, amount: float = 1.0, **labels: str) -> None:
        """Increment counter by specified amount."""
        if amount < 0:
            raise ValueError("Counter increments must be non-negative.")
        key = _labels_to_key(labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def get(self, **labels: str) -> float:
        """Get value for specific labels."""
        key = _labels_to_key(labels)
        return self._values.get(key, 0.0)

    def get_all(self) -> dict[dict[str, str], float]:
        """Return mapping of labels to values."""
        return {dict(k): v for k, v in self._values.items()}


class Gauge:
    """Instantaneous numerical gauge with label support."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = {}

    def set(self, value: float, **labels: str) -> None:
        """Set gauge value."""
        key = _labels_to_key(labels)
        self._values[key] = float(value)

    def increment(self, amount: float = 1.0, **labels: str) -> None:
        """Increment gauge by amount."""
        key = _labels_to_key(labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def decrement(self, amount: float = 1.0, **labels: str) -> None:
        """Decrement gauge by amount."""
        self.increment(-amount, **labels)

    def get(self, **labels: str) -> float:
        """Get current gauge value."""
        key = _labels_to_key(labels)
        return self._values.get(key, 0.0)

    def get_all(self) -> dict[dict[str, str], float]:
        """Return mapping of labels to values."""
        return {dict(k): v for k, v in self._values.items()}


class Histogram:
    """Histogram tracking observations in a rolling window."""

    def __init__(
        self,
        name: str,
        description: str = "",
        max_samples: int = 5000,
        window_seconds: float = 300.0,
    ) -> None:
        self.name = name
        self.description = description
        self.max_samples = max_samples
        self.window_seconds = window_seconds
        self._samples: dict[
            tuple[tuple[str, str], ...], deque[tuple[float, float]]
        ] = {}

    def observe(self, value: float, **labels: str) -> None:
        """Observe a numeric value."""
        key = _labels_to_key(labels)
        if key not in self._samples:
            self._samples[key] = deque(maxlen=self.max_samples)

        now = time.time()
        self._samples[key].append((now, float(value)))

    def get_percentiles(self, **labels: str) -> dict[str, float]:
        """Calculate percentiles for current window."""
        key = _labels_to_key(labels)
        samples = self._samples.get(key, deque())
        now = time.time()
        cutoff = now - self.window_seconds
        values = [v for ts, v in samples if ts >= cutoff]
        return calculate_percentiles(values)


class Timer:
    """Timer wrapping duration measurement around execution blocks."""

    def __init__(self, histogram: Histogram, **labels: str) -> None:
        self.histogram = histogram
        self.labels = labels
        self._start_time: float | None = None

    def __enter__(self) -> Timer:
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._start_time is not None:
            duration = time.perf_counter() - self._start_time
            self.observe(duration)

    def observe(self, duration_seconds: float) -> None:
        """Record duration into underlying histogram."""
        self.histogram.observe(duration_seconds, **self.labels)


class Rate:
    """Rate metric measuring events per second over rolling window."""

    def __init__(self, name: str, window_seconds: float = 60.0) -> None:
        self.name = name
        self.window_seconds = window_seconds
        self._timestamps: dict[tuple[tuple[str, str], ...], deque[float]] = {}

    def mark(self, count: int = 1, **labels: str) -> None:
        """Record occurrences at current timestamp."""
        key = _labels_to_key(labels)
        if key not in self._timestamps:
            self._timestamps[key] = deque(maxlen=10000)
        now = time.time()
        for _ in range(count):
            self._timestamps[key].append(now)

    def get_rate(self, **labels: str) -> float:
        """Calculate events per second over window."""
        key = _labels_to_key(labels)
        dq = self._timestamps.get(key, deque())
        now = time.time()
        cutoff = now - self.window_seconds
        valid_count = sum(1 for ts in dq if ts >= cutoff)
        return valid_count / self.window_seconds if self.window_seconds > 0 else 0.0


class MetricsEngine:
    """In-process metrics registry and aggregator."""

    def __init__(self) -> None:
        self.counters: dict[str, Counter] = {}
        self.gauges: dict[str, Gauge] = {}
        self.histograms: dict[str, Histogram] = {}
        self.rates: dict[str, Rate] = {}
        self._raw_samples: list[MetricSample] = []
        self._init_standard_metrics()

    def _init_standard_metrics(self) -> None:
        """Register Phase 29 standard metrics."""
        self.register_counter(
            "aireliability_jobs_submitted_total", "Total jobs submitted"
        )
        self.register_counter(
            "aireliability_jobs_completed_total", "Total jobs completed"
        )
        self.register_counter("aireliability_jobs_failed_total", "Total jobs failed")
        self.register_counter("aireliability_retries_total", "Total job retries")
        self.register_counter(
            "aireliability_jobs_reassigned_total", "Total jobs reassigned"
        )
        self.register_counter("aireliability_jobs_shed_total", "Total jobs shed")
        self.register_counter(
            "aireliability_auth_failures_total", "Total authentication failures"
        )
        self.register_counter(
            "aireliability_authorization_denials_total",
            "Total authorization denials",
        )
        self.register_counter(
            "aireliability_tenant_rate_limits_total",
            "Total tenant rate limits hit",
        )
        self.register_counter(
            "aireliability_tenant_quota_exceeded_total",
            "Total tenant quota exceeded events",
        )
        self.register_counter(
            "aireliability_provider_errors_total", "Total provider errors"
        )

        self.register_gauge("aireliability_queue_depth", "Current queue depth")
        self.register_gauge(
            "aireliability_worker_utilization", "Worker utilization ratio (0-1)"
        )
        self.register_gauge(
            "aireliability_circuit_breakers_open", "Count of open circuit breakers"
        )

        self.register_histogram(
            "aireliability_job_latency_seconds", "Job overall latency"
        )
        self.register_histogram(
            "aireliability_worker_execution_latency_seconds",
            "Worker execution latency",
        )
        self.register_histogram(
            "aireliability_provider_latency_seconds", "Provider request latency"
        )

    def register_counter(self, name: str, description: str = "") -> Counter:
        if name not in self.counters:
            self.counters[name] = Counter(name, description)
        return self.counters[name]

    def register_gauge(self, name: str, description: str = "") -> Gauge:
        if name not in self.gauges:
            self.gauges[name] = Gauge(name, description)
        return self.gauges[name]

    def register_histogram(
        self,
        name: str,
        description: str = "",
        max_samples: int = 5000,
        window_seconds: float = 300.0,
    ) -> Histogram:
        if name not in self.histograms:
            self.histograms[name] = Histogram(
                name, description, max_samples, window_seconds
            )
        return self.histograms[name]

    def counter(self, name: str) -> Counter:
        return self.register_counter(name)

    def gauge(self, name: str) -> Gauge:
        return self.register_gauge(name)

    def histogram(self, name: str) -> Histogram:
        return self.register_histogram(name)

    def timer(self, name: str, **labels: str) -> Timer:
        hist = self.register_histogram(name)
        return Timer(hist, **labels)

    def record_sample(
        self,
        metric_name: str,
        value: float,
        tenant_id: str | None = None,
        project_id: str | None = None,
        namespace: str | None = None,
        worker_id: str | None = None,
        provider_id: str | None = None,
        **labels: str,
    ) -> MetricSample:
        """Record an explicit sample with tenant context."""
        ctx = get_current_context()
        t_id = tenant_id or ctx.tenant_id
        p_id = project_id or ctx.project_id
        ns = namespace or ctx.namespace
        w_id = worker_id or ctx.worker_id

        lbls = dict(labels)
        lbls["tenant_id"] = t_id
        if p_id:
            lbls["project_id"] = p_id
        if ns:
            lbls["namespace"] = ns

        sample = MetricSample(
            metric_name=metric_name,
            timestamp=datetime.now(UTC),
            value=float(value),
            tenant_id=t_id,
            project_id=p_id,
            namespace=ns,
            worker_id=w_id,
            provider_id=provider_id,
            labels=lbls,
        )
        self._raw_samples.append(sample)
        if len(self._raw_samples) > 20000:
            self._raw_samples.pop(0)
        return sample

    def render_prometheus(self) -> str:
        """Render registered metrics in Prometheus exposition format."""
        lines: list[str] = []

        # Render Counters
        for name, c in sorted(self.counters.items()):
            if c.description:
                lines.append(f"# HELP {name} {c.description}")
            lines.append(f"# TYPE {name} counter")
            if not c._values:
                lines.append(f"{name} 0.0")
            for k, val in c._values.items():
                if k:
                    lbls = ",".join(f'{lk}="{lv}"' for lk, lv in k)
                    lines.append(f"{name}{{{lbls}}} {val}")
                else:
                    lines.append(f"{name} {val}")

        # Render Gauges
        for name, g in sorted(self.gauges.items()):
            if g.description:
                lines.append(f"# HELP {name} {g.description}")
            lines.append(f"# TYPE {name} gauge")
            if not g._values:
                lines.append(f"{name} 0.0")
            for k, val in g._values.items():
                if k:
                    lbls = ",".join(f'{lk}="{lv}"' for lk, lv in k)
                    lines.append(f"{name}{{{lbls}}} {val}")
                else:
                    lines.append(f"{name} {val}")

        # Render Histograms
        for name, h in sorted(self.histograms.items()):
            if h.description:
                lines.append(f"# HELP {name} {h.description}")
            lines.append(f"# TYPE {name} summary")
            for k in h._samples:
                labels_dict = dict(k)
                stats = h.get_percentiles(**labels_dict)
                for q, qname in [
                    (0.5, "0.5"),
                    (0.9, "0.9"),
                    (0.95, "0.95"),
                    (0.99, "0.99"),
                ]:
                    metric_labels = dict(labels_dict)
                    metric_labels["quantile"] = qname
                    lbl_str = ",".join(
                        f'{lk}="{lv}"' for lk, lv in sorted(metric_labels.items())
                    )
                    lines.append(
                        f"{name}{{{lbl_str}}} {stats.get(f'p{int(q * 100)}', 0.0)}"
                    )
                lbl_str = ",".join(
                    f'{lk}="{lv}"' for lk, lv in sorted(labels_dict.items())
                )
                if lbl_str:
                    lines.append(f"{name}_count{{{lbl_str}}} {stats['count']}")
                    lines.append(
                        f"{name}_sum{{{lbl_str}}} {stats['mean'] * stats['count']}"
                    )
                else:
                    lines.append(f"{name}_count {stats['count']}")
                    lines.append(f"{name}_sum {stats['mean'] * stats['count']}")

        return "\n".join(lines) + "\n"

    def clear(self) -> None:
        """Clear all metrics."""
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.rates.clear()
        self._raw_samples.clear()
        self._init_standard_metrics()
