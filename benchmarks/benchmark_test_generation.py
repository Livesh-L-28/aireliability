"""Benchmark suite for Automated AI Test Generation (Phase 36)."""

from __future__ import annotations

import sys
from pathlib import Path

# Path setup for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aireliability.core.models import FailureReport
from aireliability.failures.taxonomy import FailureCategory
from aireliability.generation.deduplication import TestDeduplicator
from aireliability.generation.engine import TestGenerationEngine
from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    TestGenerationStatus,
    TestProvenance,
    TestQualityScore,
)
from aireliability.generation.promotion import TestPromotionManager
from aireliability.generation.scoring import TestQualityScorer
from benchmarks.benchmark_config import BenchmarkConfig
from benchmarks.benchmark_utils import BenchmarkMetric, measure_benchmark


def make_failures(count: int) -> list[FailureReport]:
    """Generate synthetic failure reports for test generation."""
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
                failure_id=f"fail_tg_{i:05d}",
                trace_id=f"tr_tg_{i:05d}",
                category=cat,
                message=f"Invariant failed for {cat.value}: item index {i}",
                evidence={"step": i, "observed": f"out_{i}", "threshold": 0.8},
                confidence=0.92,
            )
        )
    return reports


def make_synthetic_generated_tests(count: int) -> list[GeneratedTest]:
    """Create synthetic GeneratedTest objects."""
    tests: list[GeneratedTest] = []
    for i in range(count):
        t = GeneratedTest(
            test_id=f"gen_test_{i:05d}",
            name=f"Generated Invariant Test {i}",
            input=f"Explain reliability behavior case {i % 10}",  # Induce some duplicates
            expected_criteria=[f"Output must adhere to invariant {i % 5}"],
            provenance=TestProvenance(
                source_type=GenerationSourceType.FAILURE_REPORT,
                source_id=f"fail_tg_{i:05d}",
                source_failure_id=f"fail_tg_{i:05d}",
            ),
            status=TestGenerationStatus.VALIDATED,
            confidence=0.90,
            quality_score=TestQualityScore(
                provenance_strength=1.0,
                failure_relevance=1.0,
                coverage_score=0.85,
                novelty_score=0.9,
                total_score=0.92,
            ),
        )
        tests.append(t)
    return tests


def run_test_generation_benchmarks(config: BenchmarkConfig) -> list[BenchmarkMetric]:
    metrics: list[BenchmarkMetric] = []
    engine = TestGenerationEngine()
    deduplicator = TestDeduplicator()
    scorer = TestQualityScorer()
    promoter = TestPromotionManager()

    fails_10 = make_failures(config.sizes.SMALL)
    fails_100 = make_failures(config.sizes.MEDIUM)
    candidate_tests_100 = make_synthetic_generated_tests(config.sizes.MEDIUM)
    candidate_tests_1000 = make_synthetic_generated_tests(min(1000, config.sizes.LARGE))

    # 1. Failure -> Generated Test (Pipeline with 10 failures)
    def bench_generation_10() -> None:
        _ = engine.generate(fails_10)

    metrics.append(
        measure_benchmark(
            operation="testgen_from_failures_10",
            target_func=bench_generation_10,
            input_size=f"{len(fails_10)} failures",
            iterations=config.iterations,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("test_generation"),
            seed=config.seed,
        )
    )

    # 2. Failure -> Generated Test (Pipeline with 100 failures)
    def bench_generation_100() -> None:
        _ = engine.generate(fails_100)

    metrics.append(
        measure_benchmark(
            operation="testgen_from_failures_100",
            target_func=bench_generation_100,
            input_size=f"{len(fails_100)} failures",
            iterations=max(3, config.iterations // 2),
            warmup_iterations=1,
            budget=config.budgets.get("test_generation"),
            seed=config.seed,
        )
    )

    # 3. Deduplication (100 candidate tests)
    def bench_deduplication_100() -> None:
        _ = deduplicator.deduplicate(candidate_tests_100)

    metrics.append(
        measure_benchmark(
            operation="testgen_deduplication_100",
            target_func=bench_deduplication_100,
            input_size="100 candidate tests",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("test_generation"),
            seed=config.seed,
        )
    )

    # 4. Deduplication (1,000 candidate tests)
    def bench_deduplication_1000() -> None:
        _ = deduplicator.deduplicate(candidate_tests_1000)

    metrics.append(
        measure_benchmark(
            operation="testgen_deduplication_1000",
            target_func=bench_deduplication_1000,
            input_size="1,000 candidate tests",
            iterations=max(3, config.iterations // 2),
            warmup_iterations=1,
            budget=config.budgets.get("test_generation"),
            seed=config.seed,
        )
    )

    # 5. Quality Scoring (100 candidate tests)
    def bench_quality_scoring_100() -> None:
        for t in candidate_tests_100:
            _ = scorer.score(t)

    metrics.append(
        measure_benchmark(
            operation="testgen_quality_scoring_100",
            target_func=bench_quality_scoring_100,
            input_size="100 candidate tests scored",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("test_generation"),
            seed=config.seed,
        )
    )

    # 6. Promotion to Regression Test (100 candidate tests)
    sample_test = candidate_tests_100[0]

    def bench_promotion() -> None:
        _ = promoter.promote_to_regression(sample_test)

    metrics.append(
        measure_benchmark(
            operation="testgen_promotion_to_regression",
            target_func=bench_promotion,
            input_size="Single test promotion to RegressionTest",
            iterations=config.iterations * 2,
            warmup_iterations=config.warmup_iterations,
            budget=config.budgets.get("test_generation"),
            seed=config.seed,
        )
    )

    return metrics


if __name__ == "__main__":
    cfg = BenchmarkConfig.from_mode("quick")
    res = run_test_generation_benchmarks(cfg)
    for m in res:
        print(
            f"[{m.status}] {m.operation}: p50={m.median_latency_ms}ms, p95={m.p95_latency_ms}ms, throughput={m.throughput_ops} ops/s"
        )
