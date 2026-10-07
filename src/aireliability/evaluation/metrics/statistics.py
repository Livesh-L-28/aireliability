"""Statistical primitives, confidence intervals, bootstrap, and effect sizes."""

from __future__ import annotations

import math
import random

from pydantic import BaseModel, ConfigDict


class StatisticalSummary(BaseModel):
    """Statistical summary of a sample population."""

    model_config = ConfigDict(frozen=True)

    count: int
    mean: float
    median: float
    std_dev: float
    variance: float
    min: float
    max: float
    p50: float
    p90: float
    p95: float
    p99: float
    confidence_interval: tuple[float, float] = (0.0, 0.0)


def mean(values: list[float]) -> float:
    """Compute arithmetic mean of a sequence."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    """Compute median value."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def variance(values: list[float], sample: bool = True) -> float:
    """Compute population or sample variance."""
    n = len(values)
    if n < 2 and sample:
        return 0.0
    if n == 0:
        return 0.0
    m = mean(values)
    sum_sq = sum((x - m) ** 2 for x in values)
    divisor = (n - 1) if sample else n
    return sum_sq / divisor


def standard_deviation(values: list[float], sample: bool = True) -> float:
    """Compute standard deviation."""
    return math.sqrt(variance(values, sample=sample))


def percentile(values: list[float], p: float) -> float:
    """Compute percentile p in [0.0, 1.0] using linear interpolation."""
    if not values:
        return 0.0
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Percentile must be between 0.0 and 1.0, got {p}")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    k = (n - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return float(d0 + d1)


def min_value(values: list[float]) -> float:
    """Return minimum value or 0.0 if empty."""
    return min(values) if values else 0.0


def max_value(values: list[float]) -> float:
    """Return maximum value or 0.0 if empty."""
    return max(values) if values else 0.0


def _approx_t_critical(df: int, confidence: float = 0.95) -> float:
    """Approximate two-tailed critical t-value for given degrees of freedom."""
    if df <= 0:
        return 1.96
    # Lookups for standard degrees of freedom at 95%
    t_95_lookup = {
        1: 12.71,
        2: 4.30,
        3: 3.18,
        4: 2.78,
        5: 2.57,
        10: 2.23,
        20: 2.09,
        30: 2.04,
        50: 2.01,
        100: 1.98,
    }
    if confidence == 0.95:
        for k in sorted(t_95_lookup.keys()):
            if df <= k:
                return t_95_lookup[k]
        return 1.96
    # Normal approximation for other confidence levels
    alpha = 1.0 - confidence
    z = math.sqrt(2.0) * _erf_inverse(1.0 - alpha)
    return z


def _erf_inverse(x: float) -> float:
    """Winitzki approximation of inverse error function."""
    a = 0.147
    sgn = 1.0 if x >= 0 else -1.0
    val = max(-0.999999, min(0.999999, x))
    ln_term = math.log(1.0 - val**2)
    first = (2.0 / (math.pi * a)) + (ln_term / 2.0)
    inside_sqrt = first**2 - (ln_term / a)
    inside_sqrt = max(0.0, inside_sqrt)
    return sgn * math.sqrt(inside_sqrt - first)


def confidence_interval(
    values: list[float],
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate parametric confidence interval for the sample mean."""
    n = len(values)
    if n < 2:
        m = mean(values)
        return (m, m)
    m = mean(values)
    s = standard_deviation(values, sample=True)
    se = s / math.sqrt(n)
    t_crit = _approx_t_critical(n - 1, confidence=confidence)
    margin = t_crit * se
    return (m - margin, m + margin)


def bootstrap_confidence_interval(
    values: list[float],
    num_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int | None = 42,
) -> tuple[float, float]:
    """Calculate non-parametric bootstrap confidence interval for the mean."""
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])

    rng = random.Random(seed)
    n = len(values)
    resample_means: list[float] = []

    for _ in range(num_resamples):
        sample = [rng.choice(values) for _ in range(n)]
        resample_means.append(sum(sample) / n)

    resample_means.sort()
    alpha = (1.0 - confidence) / 2.0
    lower = percentile(resample_means, alpha)
    upper = percentile(resample_means, 1.0 - alpha)
    return (lower, upper)


def cohens_d(group_a: list[float], group_b: list[float]) -> float:
    """Calculate Cohen's d effect size between two groups."""
    if not group_a or not group_b:
        return 0.0
    n1, n2 = len(group_a), len(group_b)
    m1, m2 = mean(group_a), mean(group_b)
    v1, v2 = variance(group_a, sample=True), variance(group_b, sample=True)

    # Pooled standard deviation
    denom = n1 + n2 - 2
    if denom <= 0:
        return 0.0
    pooled_var = (((n1 - 1) * v1) + ((n2 - 1) * v2)) / denom
    if pooled_var <= 0.0:
        return 0.0
    return (m1 - m2) / math.sqrt(pooled_var)


def welchs_t_test(
    group_a: list[float],
    group_b: list[float],
) -> tuple[float, float]:
    """Calculate Welch's t-test returning (t_statistic, approximate_two_tailed_p_value)."""
    if len(group_a) < 2 or len(group_b) < 2:
        return (0.0, 1.0)
    n1, n2 = len(group_a), len(group_b)
    m1, m2 = mean(group_a), mean(group_b)
    v1, v2 = variance(group_a, sample=True), variance(group_b, sample=True)

    se1 = v1 / n1
    se2 = v2 / n2
    se_diff = math.sqrt(se1 + se2)
    if se_diff == 0.0:
        return (0.0, 1.0 if m1 == m2 else 0.0)

    t_stat = (m1 - m2) / se_diff

    # Approximate p-value using standard normal CDF / complementary error function
    z = abs(t_stat)
    p_val = math.erfc(z / math.sqrt(2.0))
    return (t_stat, max(0.0, min(1.0, p_val)))


def mann_whitney_u(
    group_a: list[float],
    group_b: list[float],
) -> tuple[float, float]:
    """Calculate Mann-Whitney U test returning (u_statistic, approximate_two_tailed_p_value)."""
    n1 = len(group_a)
    n2 = len(group_b)
    if n1 == 0 or n2 == 0:
        return (0.0, 1.0)

    combined = [(x, 0) for x in group_a] + [(y, 1) for y in group_b]
    combined.sort(key=lambda item: item[0])

    # Assign ranks with tie handling
    ranks = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    r1 = sum(ranks[idx] for idx in range(len(combined)) if combined[idx][1] == 0)
    u1 = r1 - (n1 * (n1 + 1)) / 2.0
    u2 = (n1 * n2) - u1
    u = min(u1, u2)

    # Normal approximation for large sample size
    mean_u = (n1 * n2) / 2.0
    var_u = (n1 * n2 * (n1 + n2 + 1)) / 12.0
    if var_u == 0.0:
        return (u, 1.0)
    z = (u - mean_u) / math.sqrt(var_u)
    p_val = math.erfc(abs(z) / math.sqrt(2.0))
    return (u, max(0.0, min(1.0, p_val)))


def compute_statistical_summary(values: list[float]) -> StatisticalSummary:
    """Compute complete statistical summary for sample values."""
    if not values:
        return StatisticalSummary(
            count=0,
            mean=0.0,
            median=0.0,
            std_dev=0.0,
            variance=0.0,
            min=0.0,
            max=0.0,
            p50=0.0,
            p90=0.0,
            p95=0.0,
            p99=0.0,
            confidence_interval=(0.0, 0.0),
        )

    return StatisticalSummary(
        count=len(values),
        mean=round(mean(values), 4),
        median=round(median(values), 4),
        std_dev=round(standard_deviation(values), 4),
        variance=round(variance(values), 4),
        min=round(min_value(values), 4),
        max=round(max_value(values), 4),
        p50=round(percentile(values, 0.50), 4),
        p90=round(percentile(values, 0.90), 4),
        p95=round(percentile(values, 0.95), 4),
        p99=round(percentile(values, 0.99), 4),
        confidence_interval=confidence_interval(values, confidence=0.95),
    )
