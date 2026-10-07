"""Configuration definitions, dataset size constants, and performance budgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BENCHMARK_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = BENCHMARK_ROOT.parent
RESULTS_DIR = BENCHMARK_ROOT / "results"
DATASETS_DIR = BENCHMARK_ROOT / "datasets"


@dataclass
class WorkloadSizes:
    """Standardized dataset and workload volume scales."""

    SMALL: int = 10
    MEDIUM: int = 100
    LARGE: int = 1000
    XLARGE: int = 10000


@dataclass
class PerformanceBudget:
    """Latency, throughput, and memory performance thresholds."""

    max_p95_ms: float
    min_throughput_ops: float
    max_memory_growth_mb: float = 50.0


# Performance budgets derived from empirical microsecond/millisecond performance
DEFAULT_BUDGETS: dict[str, PerformanceBudget] = {
    "deterministic_llm": PerformanceBudget(max_p95_ms=5.0, min_throughput_ops=500.0),
    "single_evaluation": PerformanceBudget(max_p95_ms=10.0, min_throughput_ops=200.0),
    "batch_evaluation": PerformanceBudget(max_p95_ms=50.0, min_throughput_ops=100.0),
    "rag_evaluation": PerformanceBudget(max_p95_ms=30.0, min_throughput_ops=30.0),
    "agent_evaluation": PerformanceBudget(max_p95_ms=40.0, min_throughput_ops=20.0),
    "safety_scoring": PerformanceBudget(max_p95_ms=15.0, min_throughput_ops=100.0),
    "intelligence_clustering": PerformanceBudget(
        max_p95_ms=80.0, min_throughput_ops=15.0
    ),
    "graph_insertion": PerformanceBudget(max_p95_ms=10.0, min_throughput_ops=100.0),
    "graph_traversal": PerformanceBudget(max_p95_ms=5.0, min_throughput_ops=200.0),
    "graph_serialization": PerformanceBudget(max_p95_ms=10.0, min_throughput_ops=100.0),
    "test_generation": PerformanceBudget(max_p95_ms=25.0, min_throughput_ops=50.0),
    "self_healing_simulation": PerformanceBudget(
        max_p95_ms=35.0, min_throughput_ops=40.0
    ),
    "optimization_search": PerformanceBudget(max_p95_ms=100.0, min_throughput_ops=10.0),
    "prediction_forecasting": PerformanceBudget(
        max_p95_ms=20.0, min_throughput_ops=50.0
    ),
    "policy_rule_evaluation": PerformanceBudget(
        max_p95_ms=5.0, min_throughput_ops=200.0
    ),
    "tenant_isolation_check": PerformanceBudget(
        max_p95_ms=2.0, min_throughput_ops=500.0
    ),
    "dashboard_aggregation": PerformanceBudget(
        max_p95_ms=45.0, min_throughput_ops=20.0
    ),
    "api_health_endpoint": PerformanceBudget(max_p95_ms=15.0, min_throughput_ops=100.0),
    "sdk_client_execution": PerformanceBudget(max_p95_ms=20.0, min_throughput_ops=50.0),
}


@dataclass
class BenchmarkConfig:
    """Runtime benchmark parameters and control flags."""

    mode: str = "standard"  # "smoke", "standard", "full"
    seed: int = 42
    warmup_iterations: int = 3
    iterations: int = 15
    sizes: WorkloadSizes = field(default_factory=WorkloadSizes)
    budgets: dict[str, PerformanceBudget] = field(
        default_factory=lambda: DEFAULT_BUDGETS
    )
    output_dir: Path = RESULTS_DIR
    save_baseline: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mode(cls, mode: str = "standard", **kwargs: Any) -> BenchmarkConfig:
        cfg = cls(mode=mode, **kwargs)
        if mode == "smoke":
            cfg.warmup_iterations = 1
            cfg.iterations = 3
            cfg.sizes = WorkloadSizes(SMALL=5, MEDIUM=20, LARGE=50, XLARGE=100)
        elif mode == "quick":
            cfg.warmup_iterations = 2
            cfg.iterations = 5
            cfg.sizes = WorkloadSizes(SMALL=10, MEDIUM=50, LARGE=200, XLARGE=500)
        elif mode == "full":
            cfg.warmup_iterations = 5
            cfg.iterations = 30
            cfg.sizes = WorkloadSizes(SMALL=10, MEDIUM=100, LARGE=1000, XLARGE=10000)
        return cfg
