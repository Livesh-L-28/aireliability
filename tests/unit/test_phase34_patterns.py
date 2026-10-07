"""Unit tests for Phase 34 deterministic PatternDetector."""

from __future__ import annotations

from aireliability.evaluation.governance.baselines import EvaluationBaseline
from aireliability.intelligence.models import (
    FailureCluster,
    PatternType,
)
from aireliability.intelligence.patterns import PatternDetector


def _make_cluster(
    cluster_id: str,
    name: str,
    fingerprint: str,
    frequency: int,
    category: str = "retrieval",
    components: list[str] | None = None,
) -> FailureCluster:
    return FailureCluster(
        cluster_id=cluster_id,
        name=name,
        fingerprint=fingerprint,
        representative_failure_id=f"rep_{cluster_id}",
        failure_ids=[f"f_{i}" for i in range(frequency)],
        dominant_category=category,
        dominant_root_cause=f"{category}.missing",
        frequency=frequency,
        affected_components=components or [],
    )


def test_recurring_pattern_detection() -> None:
    detector = PatternDetector(min_recurrence_count=3)
    c1 = _make_cluster("c1", "Cluster 1", "fp_1", frequency=4)
    c2 = _make_cluster("c2", "Cluster 2", "fp_2", frequency=1)

    patterns = detector.detect_patterns([c1, c2])
    recurring = [p for p in patterns if p.pattern_type == PatternType.RECURRING]
    assert len(recurring) == 1
    assert recurring[0].fingerprint == "fp_1"
    assert recurring[0].frequency == 4


def test_component_specific_patterns() -> None:
    detector = PatternDetector()
    c_tool = _make_cluster(
        "c_tool", "Tool failure", "fp_tool", 2, components=["tool:calculator"]
    )
    c_ret = _make_cluster(
        "c_ret", "Retriever failure", "fp_ret", 2, components=["retriever:weaviate"]
    )
    c_mod = _make_cluster(
        "c_mod", "Model failure", "fp_mod", 2, components=["model:claude-3-5"]
    )

    patterns = detector.detect_patterns([c_tool, c_ret, c_mod])
    types = {p.pattern_type for p in patterns}
    assert PatternType.TOOL_SPECIFIC in types
    assert PatternType.RETRIEVER_SPECIFIC in types
    assert PatternType.MODEL_SPECIFIC in types


def test_baseline_new_and_disappearing_patterns() -> None:
    detector = PatternDetector()
    c_existing = _make_cluster("c_old", "Existing", "fp_old", 2)
    c_new = _make_cluster("c_new", "New cluster", "fp_new", 3)

    baseline = EvaluationBaseline(
        name="v1.0-baseline",
        target_name="agent",
        dataset_id="golden",
        metrics={},
        total_test_cases=10,
        passed_test_cases=8,
        failed_test_cases=2,
        metadata={"failure_fingerprints": ["fp_old", "fp_resolved"]},
    )

    patterns = detector.detect_patterns([c_existing, c_new], baseline=baseline)
    new_patterns = [p for p in patterns if p.pattern_type == PatternType.NEW]
    disappeared_patterns = [
        p for p in patterns if p.pattern_type == PatternType.DISAPPEARING
    ]

    assert len(new_patterns) == 1
    assert new_patterns[0].fingerprint == "fp_new"

    assert len(disappeared_patterns) == 1
    assert disappeared_patterns[0].fingerprint == "fp_resolved"


def test_longitudinal_increasing_and_persistent_patterns() -> None:
    detector = PatternDetector(min_observations_for_trend=3)

    # 3 historical runs: fp_bad escalates: 1 -> 3 -> 8
    run1 = [_make_cluster("c1_1", "Bad", "fp_bad", 1)]
    run2 = [_make_cluster("c2_1", "Bad", "fp_bad", 3)]
    run3 = [_make_cluster("c3_1", "Bad", "fp_bad", 8)]

    patterns = detector.detect_patterns(
        clusters=run3,
        historical_clusters=[run1, run2, run3],
    )

    increasing = [p for p in patterns if p.pattern_type == PatternType.INCREASING]
    assert len(increasing) == 1
    assert increasing[0].fingerprint == "fp_bad"
