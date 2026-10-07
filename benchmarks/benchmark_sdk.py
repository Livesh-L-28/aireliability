"""Benchmark suite for Sync and Async Python SDK Clients (Phase 46)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.api.app import api_app
from aireliability.sdk.async_client import AsyncClient
from aireliability.sdk.client import (
    Client,
    TenantIsolationError,
    _map_http_error,
)
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def run_sdk_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    sync_client = Client(app=api_app)
    async_client = AsyncClient(app=api_app)

    # 1. Exception Mapping
    def bench_exception_mapping() -> None:
        err1 = _map_http_error(401, "Token expired")
        err2 = _map_http_error(403, "Cross tenant access blocked")
        err3 = _map_http_error(422, "Missing parameter")
        assert err1.status_code == 401
        assert isinstance(err2, TenantIsolationError)
        assert err3.status_code == 422

    metrics.append(
        measure_benchmark(
            operation="sdk_exception_mapping",
            target_func=bench_exception_mapping,
            input_size="HTTP error mapping to typed SDK errors",
            iterations=config.iterations * 3,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("sdk_client_execution"),
            seed=config.seed,
        )
    )

    # 2. Synchronous Client - Health & Dashboard Query
    def bench_sync_dashboard() -> None:
        resp = sync_client.dashboard.get_health()
        assert (
            "overall_health" in resp
            or "health_status" in resp
            or isinstance(resp, dict)
        )

    metrics.append(
        measure_benchmark(
            operation="sdk_sync_dashboard_get_health",
            target_func=bench_sync_dashboard,
            input_size="Sync Client.dashboard.get_health()",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("sdk_client_execution"),
            seed=config.seed,
        )
    )

    # 3. Synchronous Client - Evaluation Create
    def bench_sync_evaluation() -> None:
        resp = sync_client.evaluations.create(
            input_text="SDK benchmark input prompt",
            output_text="SDK benchmark output response",
        )
        assert resp["passed"] is True

    metrics.append(
        measure_benchmark(
            operation="sdk_sync_evaluation_create",
            target_func=bench_sync_evaluation,
            input_size="Sync Client.evaluations.create()",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("sdk_client_execution"),
            seed=config.seed,
        )
    )

    # 4. Asynchronous Client - Evaluation Create
    async def _async_eval_task() -> None:
        resp = await async_client.evaluations.create(
            input_text="Async SDK benchmark prompt",
            output_text="Async SDK benchmark output",
        )
        assert resp["passed"] is True

    def bench_async_evaluation() -> None:
        asyncio.run(_async_eval_task())

    metrics.append(
        measure_benchmark(
            operation="sdk_async_evaluation_create",
            target_func=bench_async_evaluation,
            input_size="AsyncClient.evaluations.create()",
            iterations=config.iterations,
            warmup_iterations=1,
            budget=config.budgets.get("sdk_client_execution"),
            seed=config.seed,
        )
    )

    # 5. Synchronous Client - Policy Evaluation
    policy_ctx = {"metric_0": 0.95, "reliability_score": 0.98}

    def bench_sync_policy_eval() -> None:
        resp = sync_client.policies.evaluate(context=policy_ctx)
        assert "decision" in resp

    metrics.append(
        measure_benchmark(
            operation="sdk_sync_policy_evaluate",
            target_func=bench_sync_policy_eval,
            input_size="Sync Client.policies.evaluate()",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("sdk_client_execution"),
            seed=config.seed,
        )
    )

    # 6. Synchronous Client - Prediction Run
    def bench_sync_prediction() -> None:
        resp = sync_client.predictions.predict(target_id="agent_assistant")
        assert "target_id" in resp or "risk_forecast" in resp

    metrics.append(
        measure_benchmark(
            operation="sdk_sync_prediction_predict",
            target_func=bench_sync_prediction,
            input_size="Sync Client.predictions.predict()",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("sdk_client_execution"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_sdk_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
