"""Benchmark suite for Reliability Intelligence Engine (Phase 34) across clustering, patterns, impact, and scale."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.core.models import FailureReport
from aireliability.failures.taxonomy import FailureCategory
from aireliability.intelligence.clustering import FailureClusterer
from aireliability.intelligence.engine import ReliabilityIntelligenceEngine
from aireliability.intelligence.impact import ImpactAnalyzer
from aireliability.intelligence.patterns import PatternDetector
from aireliability.intelligence.recommendations import RecommendationEngine
from aireliability.intelligence.similarity import FailureNormalizer
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_failure_reports(count: int) -> list[FailureReport]:
    """Generate synthetic FailureReport objects."""
    categories = [
        FailureCategory.TOOL,
        FailureCategory.TASK,
        FailureCategory.PERFORMANCE,
        FailureCategory.RETRIEVAL,
        FailureCategory.OUTPUT,
    ]
    reports: list[FailureReport] = []
    for i in range(count):
        cat = categories[i % len(categories)]
        reports.append(
            FailureReport(
                failure_id=f"f_{i:06d}",
                trace_id=f"tr_{i:06d}",
                category=cat,
                message=f"Synthetic failure detected in {cat.value}: invariant mismatch at index {i}",
                evidence={"step": i, "observed": f"val_{i}"},
                confidence=0.88 + ((i % 10) / 100.0),
            )
        )
    return reports


def run_intelligence_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    engine = ReliabilityIntelligenceEngine()

    fails_10 = make_failure_reports(config.sizes.SMALL)
    fails_100 = make_failure_reports(config.sizes.MEDIUM)
    fails_1000 = make_failure_reports(min(1000, config.sizes.LARGE))

    # 1. Normalization
    fn = FailureNormalizer()

    def bench_normalization_100() -> None:
        _ = [fn.normalize(f) for f in fails_100]

    metrics.append(
        measure_benchmark(
            operation="intelligence_normalization_100",
            target_func=bench_normalization_100,
            input_size=f"{len(fails_100)} failures",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    norm_100 = [fn.normalize(f) for f in fails_100]

    # 2. Structural Clustering - 100 failures
    fc = FailureClusterer()

    def bench_clustering_100() -> None:
        _ = fc.cluster(norm_100)

    metrics.append(
        measure_benchmark(
            operation="intelligence_clustering_100",
            target_func=bench_clustering_100,
            input_size=f"{len(norm_100)} normalized failures",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    clusters_100 = fc.cluster(norm_100)

    # 3. Pattern Detection
    pd = PatternDetector()

    def bench_pattern_detection() -> None:
        _ = pd.detect_patterns(clusters_100)

    metrics.append(
        measure_benchmark(
            operation="intelligence_pattern_detection",
            target_func=bench_pattern_detection,
            input_size=f"{len(clusters_100)} clusters",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    # 4. Impact Assessment
    ia = ImpactAnalyzer()

    def bench_impact_assessment() -> None:
        _ = ia.assess_all(clusters=clusters_100)

    metrics.append(
        measure_benchmark(
            operation="intelligence_impact_assessment",
            target_func=bench_impact_assessment,
            input_size=f"{len(clusters_100)} clusters",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    # 5. Recommendation Generation
    re = RecommendationEngine()

    def bench_recommendation_gen() -> None:
        _ = re.generate_recommendations(clusters=clusters_100)

    metrics.append(
        measure_benchmark(
            operation="intelligence_recommendations",
            target_func=bench_recommendation_gen,
            input_size=f"{len(clusters_100)} clusters",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    # 6. Complete End-to-End Analysis - Small (10 failures)
    def bench_analysis_small() -> None:
        _ = engine.analyze(failures=fails_10, target_name="bench_small")

    metrics.append(
        measure_benchmark(
            operation="intelligence_complete_analysis_small",
            target_func=bench_analysis_small,
            input_size=f"{len(fails_10)} failures",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    # 7. Complete End-to-End Analysis - Medium (100 failures)
    def bench_analysis_medium() -> None:
        _ = engine.analyze(failures=fails_100, target_name="bench_medium")

    metrics.append(
        measure_benchmark(
            operation="intelligence_complete_analysis_medium",
            target_func=bench_analysis_medium,
            input_size=f"{len(fails_100)} failures",
            iterations=max(3, config.iterations // 2),
            warmup_iterations=1,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    # 8. Complete End-to-End Analysis - Large (1,000 failures)
    def bench_analysis_large() -> None:
        _ = engine.analyze(failures=fails_1000, target_name="bench_large")

    metrics.append(
        measure_benchmark(
            operation="intelligence_complete_analysis_large",
            target_func=bench_analysis_large,
            input_size=f"{len(fails_1000)} failures",
            iterations=max(2, config.iterations // 4),
            warmup_iterations=1,
            budget=config.budgets.get("intelligence_clustering"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_intelligence_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
