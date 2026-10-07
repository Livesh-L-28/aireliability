"""Benchmark suite for Local FastAPI REST Service (Phase 46)."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from aireliability.api.app import create_app
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import (
    BenchmarkMetric,
    measure_benchmark,
    measure_concurrency,
)


def run_api_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    app = create_app()
    client = TestClient(app)
    auth_header = {"Authorization": "Bearer bearer_token_tenant1_user1_owner"}

    # 1. Health Endpoint (Public, GET /health)
    def bench_health() -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    metrics.append(
        measure_benchmark(
            operation="api_health_endpoint",
            target_func=bench_health,
            input_size="GET /health",
            iterations=config.iterations * 3,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("api_health_endpoint"),
            seed=config.seed,
        )
    )

    # 2. Evaluation Endpoint (POST /api/v1/evaluations)
    eval_payload = {
        "input_text": "Translate English to French",
        "output_text": "Bonjour le monde",
        "expected_output": "Bonjour le monde",
    }

    def bench_evaluation_endpoint() -> None:
        resp = client.post(
            "/api/v1/evaluations", headers=auth_header, json=eval_payload
        )
        assert resp.status_code == 200

    metrics.append(
        measure_benchmark(
            operation="api_evaluation_endpoint",
            target_func=bench_evaluation_endpoint,
            input_size="POST /api/v1/evaluations",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("api_health_endpoint"),
            seed=config.seed,
        )
    )

    # 3. Prediction Endpoint (POST /api/v1/predictions)
    pred_payload = {"target_id": "service_pipeline_alpha"}

    def bench_prediction_endpoint() -> None:
        resp = client.post(
            "/api/v1/predictions", headers=auth_header, json=pred_payload
        )
        assert resp.status_code == 200

    metrics.append(
        measure_benchmark(
            operation="api_prediction_endpoint",
            target_func=bench_prediction_endpoint,
            input_size="POST /api/v1/predictions",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("api_health_endpoint"),
            seed=config.seed,
        )
    )

    # 4. Dashboard Endpoint (GET /api/v1/dashboard)
    def bench_dashboard_endpoint() -> None:
        resp = client.get("/api/v1/dashboard", headers=auth_header)
        assert resp.status_code == 200

    metrics.append(
        measure_benchmark(
            operation="api_dashboard_endpoint",
            target_func=bench_dashboard_endpoint,
            input_size="GET /api/v1/dashboard",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("api_health_endpoint"),
            seed=config.seed,
        )
    )

    # 5. Policies Endpoint (GET /api/v1/policies)
    def bench_policy_endpoint() -> None:
        resp = client.get("/api/v1/policies", headers=auth_header)
        assert resp.status_code == 200

    metrics.append(
        measure_benchmark(
            operation="api_policy_endpoint",
            target_func=bench_policy_endpoint,
            input_size="GET /api/v1/policies",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("api_health_endpoint"),
            seed=config.seed,
        )
    )

    # 6. Tenants Endpoint (GET /api/v1/tenants)
    def bench_tenants_endpoint() -> None:
        resp = client.get("/api/v1/tenants", headers=auth_header)
        assert resp.status_code == 200

    metrics.append(
        measure_benchmark(
            operation="api_tenants_endpoint",
            target_func=bench_tenants_endpoint,
            input_size="GET /api/v1/tenants",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("api_health_endpoint"),
            seed=config.seed,
        )
    )

    # 7. Controlled Concurrency (4 workers on GET /health)
    def check_health_ok() -> bool:
        resp = client.get("/health")
        return resp.status_code == 200

    conc_results = measure_concurrency(
        worker_fn=check_health_ok,
        worker_counts=[1, 2, 4, 8],
        requests_per_worker=10,
    )
    # Record representative 4-worker metric into standard metrics list
    m4 = next((item for item in conc_results if item["workers"] == 4), conc_results[-1])
    metrics.append(
        BenchmarkMetric(
            operation="api_concurrency_4_workers",
            input_size=f"{m4['total_requests']} requests across 4 workers",
            iterations=m4["total_requests"],
            warmup_iterations=0,
            total_duration_ms=m4["wall_time_ms"],
            average_latency_ms=m4["p50_ms"],
            median_latency_ms=m4["p50_ms"],
            p95_latency_ms=m4["p95_ms"],
            p99_latency_ms=m4["p99_ms"],
            min_latency_ms=m4["p50_ms"] * 0.5,
            max_latency_ms=m4["p99_ms"],
            throughput_ops=m4["throughput_ops"],
            memory_initial_mb=0.0,
            memory_peak_mb=0.0,
            memory_final_mb=0.0,
            memory_growth_mb=0.0,
            status="PASS" if m4["error_rate"] == 0.0 else "REGRESSION",
            details={"error_rate": m4["error_rate"], "workers": 4},
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_api_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
