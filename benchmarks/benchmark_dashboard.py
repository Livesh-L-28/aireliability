"""Benchmark suite for Reliability Intelligence Dashboard (Phase 43)."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.dashboard.health import ReliabilityHealthCalculator
from aireliability.dashboard.models import AlertSeverity, DashboardAlert
from aireliability.dashboard.panels import DashboardPanelBuilder
from aireliability.dashboard.service import DashboardBuilder, DashboardService
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_metrics_payload(scale: int = 1) -> dict[str, float]:
    """Generate metrics payload simulating aggregated reliability indicators."""
    return {
        "reliability": 0.94,
        "safety": 1.0,
        "security": 1.0,
        "rag": 0.91,
        "agent": 0.89,
        "quality": 0.95,
        "incidents": 1 * scale,
        "failures_count": 12 * scale,
        "latency_p95": 14.2,
        "drift_score": 0.03,
    }


def run_dashboard_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    service = DashboardService()
    builder = DashboardBuilder()
    health_calc = ReliabilityHealthCalculator()
    panel_builder = DashboardPanelBuilder()

    metrics_small = make_metrics_payload(1)
    metrics_large = make_metrics_payload(10)
    alerts = [
        DashboardAlert(
            source="drift",
            title="Drift Warning",
            severity=AlertSeverity.LOW,
            message="Feature drift detected in retrieval signals",
        )
    ]

    # 1. Health Score Calculation
    def bench_health_calculation() -> None:
        _ = health_calc.calculate_health(
            reliability_score=0.92,
            safety_score=1.0,
            security_score=1.0,
            rag_score=0.88,
            agent_score=0.91,
            quality_score=0.93,
            active_incidents=0,
            active_alerts=1,
            hard_veto_flag=False,
        )

    metrics.append(
        measure_benchmark(
            operation="dashboard_health_calculation",
            target_func=bench_health_calculation,
            input_size="Multi-subsystem health vector",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    # 2. Panel Generation
    def bench_panel_generation() -> None:
        _ = panel_builder.build_all_panels(metrics_small)

    metrics.append(
        measure_benchmark(
            operation="dashboard_panel_generation",
            target_func=bench_panel_generation,
            input_size="All panels synthesis",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    # 3. Complete Dashboard Aggregation (Small)
    def bench_dashboard_aggregation_small() -> None:
        _ = builder.build_dashboard(metrics=metrics_small, alerts=alerts)

    metrics.append(
        measure_benchmark(
            operation="dashboard_aggregation_small",
            target_func=bench_dashboard_aggregation_small,
            input_size="Small metrics aggregation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    # 4. Complete Dashboard Aggregation (Large)
    def bench_dashboard_aggregation_large() -> None:
        _ = builder.build_dashboard(metrics=metrics_large, alerts=alerts)

    metrics.append(
        measure_benchmark(
            operation="dashboard_aggregation_large",
            target_func=bench_dashboard_aggregation_large,
            input_size="Large metrics aggregation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    dash = service.get_dashboard(metrics=metrics_small)

    # 5. JSON Serialization
    def bench_json_export() -> None:
        _ = service.export_json(dash)

    metrics.append(
        measure_benchmark(
            operation="dashboard_json_serialization",
            target_func=bench_json_export,
            input_size="Full dashboard model JSON export",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    # 6. Markdown Serialization
    def bench_markdown_export() -> None:
        _ = service.export_markdown(dash)

    metrics.append(
        measure_benchmark(
            operation="dashboard_markdown_serialization",
            target_func=bench_markdown_export,
            input_size="Full dashboard Markdown report generation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    # 7. HTML Serialization
    def bench_html_export() -> None:
        md = service.export_markdown(dash)
        # Fast deterministic HTML template wrapping
        _ = f"<!DOCTYPE html><html><head><title>{dash.name}</title></head><body><pre>{md}</pre></body></html>"

    metrics.append(
        measure_benchmark(
            operation="dashboard_html_serialization",
            target_func=bench_html_export,
            input_size="Dashboard HTML wrapper generation",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    # 8. Snapshot Fingerprinting
    snap = service.create_snapshot(dash)

    def bench_snapshot_fingerprint() -> None:
        _ = snap.fingerprint()

    metrics.append(
        measure_benchmark(
            operation="dashboard_snapshot_fingerprinting",
            target_func=bench_snapshot_fingerprint,
            input_size="Snapshot SHA256 fingerprint",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("dashboard_aggregation"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_dashboard_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
