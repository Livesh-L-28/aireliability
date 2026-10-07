"""Regression comparison tool comparing baseline.json against performance.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_metrics_map(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load JSON benchmark result file into (metadata, {operation_name: metric_dict})."""
    if not path.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    metrics_map = {m["operation"]: m for m in data.get("metrics", [])}
    return data, metrics_map


def compare_benchmarks(
    baseline_path: Path,
    performance_path: Path,
    tolerance_pct: float = 20.0,
) -> int:
    """Compare baseline metrics against candidate performance metrics."""
    base_data, base_map = load_metrics_map(baseline_path)
    perf_data, perf_map = load_metrics_map(performance_path)

    improvements: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    all_ops = sorted(set(base_map.keys()) | set(perf_map.keys()))

    print("=" * 90)
    print("AIRELIABILITY v1.4.0 — PERFORMANCE REGRESSION COMPARISON")
    print(f"Baseline:    {baseline_path.name} ({len(base_map)} operations)")
    print(f"Performance: {performance_path.name} ({len(perf_map)} operations)")
    print(f"Tolerance:   ±{tolerance_pct}%")
    print("=" * 90)
    print(
        f"{'Operation':<40} {'Base p50':<11} {'Perf p50':<11} {'Delta p50':<12} {'Throughput Δ':<14} {'Status':<10}"
    )
    print("-" * 90)

    for op in all_ops:
        b = base_map.get(op)
        p = perf_map.get(op)

        if not b:
            print(
                f"{op:<40} {'N/A':<11} {p['median_latency_ms']:<11.3f} {'NEW':<12} {'N/A':<14} {'[NEW]':<10}"
            )
            continue
        if not p:
            print(
                f"{op:<40} {b['median_latency_ms']:<11.3f} {'N/A':<11} {'REMOVED':<12} {'N/A':<14} {'[REMOVED]':<10}"
            )
            continue

        b_p50 = b["median_latency_ms"]
        p_p50 = p["median_latency_ms"]
        b_thr = b["throughput_ops"]
        p_thr = p["throughput_ops"]

        # Latency delta
        delta_p50_ms = p_p50 - b_p50
        delta_p50_pct = (delta_p50_ms / b_p50 * 100.0) if b_p50 > 0 else 0.0

        # Throughput delta
        delta_thr_pct = ((p_thr - b_thr) / b_thr * 100.0) if b_thr > 0 else 0.0

        item = {
            "operation": op,
            "base_p50": b_p50,
            "perf_p50": p_p50,
            "delta_ms": delta_p50_ms,
            "delta_pct": delta_p50_pct,
            "thr_delta_pct": delta_thr_pct,
        }

        # Classification: require both percentage increase and material absolute latency change
        min_delta_ms = (
            0.20  # 200 microseconds threshold to filter out timer resolution jitter
        )
        if delta_p50_pct < -tolerance_pct and abs(delta_p50_ms) >= min_delta_ms:
            status = "IMPROVED"
            improvements.append(item)
        elif delta_p50_pct > tolerance_pct and delta_p50_ms >= min_delta_ms:
            # Latency materially increased
            status = "REGRESSION"
            regressions.append(item)
        else:
            status = "UNCHANGED"
            unchanged.append(item)

        sign = "+" if delta_p50_ms > 0 else ""
        delta_str = f"{sign}{delta_p50_ms:.3f}ms ({sign}{delta_p50_pct:.1f}%)"
        thr_str = f"{'+' if delta_thr_pct > 0 else ''}{delta_thr_pct:.1f}%"

        print(
            f"{op:<40} {b_p50:<11.3f} {p_p50:<11.3f} {delta_str:<12} {thr_str:<14} [{status}]"
        )

    print("=" * 90)
    print("COMPARISON SUMMARY")
    print("=" * 90)
    print(f"Total Compared: {len(all_ops)}")
    print(f"Improvements:   {len(improvements)}")
    print(f"Unchanged:      {len(unchanged)}")
    print(f"Regressions:    {len(regressions)}")
    print("=" * 90)

    if regressions:
        print("\n[!] WARNING: Detected potential performance regressions:")
        for r in regressions:
            print(
                f"    - {r['operation']}: +{r['delta_ms']:.3f}ms (+{r['delta_pct']:.1f}%)"
            )
        return 1

    print("\n[+] SUCCESS: No regressions observed within tolerance.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare benchmark JSON files.")
    parser.add_argument("baseline", type=Path, help="Path to baseline.json")
    parser.add_argument("performance", type=Path, help="Path to performance.json")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=25.0,
        help="Percentage tolerance threshold for regression (default: 25.0)",
    )
    args = parser.parse_args()

    return compare_benchmarks(
        args.baseline, args.performance, tolerance_pct=args.tolerance
    )


if __name__ == "__main__":
    sys.exit(main())
