"""Deterministic pattern detection for AI reliability failures."""

from __future__ import annotations

from collections.abc import Sequence

from aireliability.evaluation.governance.baselines import EvaluationBaseline
from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.models import (
    EvidenceReference,
    FailureCluster,
    FailurePattern,
    PatternType,
)


class PatternDetector:
    """Detects longitudinal patterns, anomalies, and component-specific failure signatures."""

    def __init__(
        self,
        min_recurrence_count: int = 2,
        min_observations_for_trend: int = 2,
    ) -> None:
        self.min_recurrence_count = min_recurrence_count
        self.min_observations_for_trend = min_observations_for_trend

    def detect_patterns(
        self,
        clusters: Sequence[FailureCluster],
        historical_clusters: Sequence[Sequence[FailureCluster]] | None = None,
        baseline: EvaluationBaseline | None = None,
        evidence_pool: list[EvidenceReference] | None = None,
    ) -> list[FailurePattern]:
        """Detect patterns across current clusters and optional historical/baseline data."""
        patterns: list[FailurePattern] = []

        # 1. Intra-run Recurring & Component-Specific patterns
        for c in clusters:
            if c.frequency >= self.min_recurrence_count:
                patterns.append(
                    FailurePattern(
                        pattern_type=PatternType.RECURRING,
                        title=f"Recurring Failure: {c.name}",
                        description=(
                            f"Failure pattern repeated {c.frequency} times within the evaluation run. "
                            f"Dominant root cause: {c.dominant_root_cause}."
                        ),
                        fingerprint=c.fingerprint,
                        frequency=c.frequency,
                        affected_components=c.affected_components,
                        confidence=c.confidence,
                        evidence=c.evidence,
                    )
                )

            # Check Component-Specific patterns
            for comp in c.affected_components:
                p_type = (
                    PatternType.TOOL_SPECIFIC
                    if comp.startswith("tool:")
                    else (
                        PatternType.RETRIEVER_SPECIFIC
                        if comp.startswith("retriever:")
                        else (
                            PatternType.MODEL_SPECIFIC
                            if comp.startswith("model:")
                            else PatternType.ANOMALOUS
                        )
                    )
                )
                if p_type != PatternType.ANOMALOUS:
                    patterns.append(
                        FailurePattern(
                            pattern_type=p_type,
                            title=f"Component-Specific Failure: {comp}",
                            description=f"Failures in cluster '{c.name}' are strictly isolated to component '{comp}'.",
                            fingerprint=c.fingerprint,
                            frequency=c.frequency,
                            affected_components=[comp],
                            confidence=c.confidence,
                            evidence=c.evidence,
                        )
                    )

        # 2. Baseline comparison (NEW and DISAPPEARING patterns)
        if baseline is not None:
            # Baseline failures mapped by fingerprint
            base_meta = baseline.metadata or {}
            base_fps = set(base_meta.get("failure_fingerprints", []))
            curr_fps = {c.fingerprint for c in clusters}

            # NEW failures: in current but not in baseline
            for c in clusters:
                if base_fps and c.fingerprint not in base_fps:
                    conf = ConfidenceEngine.calculate(
                        evidence_count=len(c.evidence) + 1,
                        sample_size=max(2, c.frequency),
                        agreement_rate=1.0,
                    )
                    patterns.append(
                        FailurePattern(
                            pattern_type=PatternType.NEW,
                            title=f"Newly Introduced Failure: {c.name}",
                            description=(
                                f"Failure cluster was absent in reference baseline '{baseline.name}' "
                                f"and newly surfaced with {c.frequency} occurrences."
                            ),
                            fingerprint=c.fingerprint,
                            frequency=c.frequency,
                            affected_components=c.affected_components,
                            confidence=conf,
                            evidence=c.evidence,
                        )
                    )

            # DISAPPEARING failures: in baseline but not in current
            disappeared_fps = base_fps - curr_fps
            for dfp in disappeared_fps:
                patterns.append(
                    FailurePattern(
                        pattern_type=PatternType.DISAPPEARING,
                        title=f"Resolved / Disappearing Failure: {dfp[:10]}",
                        description=f"Failure fingerprint '{dfp}' present in baseline '{baseline.name}' is no longer observed.",
                        fingerprint=dfp,
                        frequency=0,
                        affected_components=[],
                        confidence=ConfidenceEngine.calculate(
                            evidence_count=1, sample_size=2
                        ),
                        evidence=[],
                    )
                )

        # 3. Longitudinal Trends across historical runs (INCREASING, DECREASING, PERSISTENT)
        if (
            historical_clusters
            and len(historical_clusters) >= self.min_observations_for_trend
        ):
            # Track frequency trajectory per fingerprint over time
            trajectory: dict[str, list[int]] = {}
            for run_clusters in historical_clusters:
                run_map = {c.fingerprint: c.frequency for c in run_clusters}
                all_fps = set(trajectory.keys()) | set(run_map.keys())
                for fp in all_fps:
                    trajectory.setdefault(fp, []).append(run_map.get(fp, 0))

            for fp, counts in trajectory.items():
                if len(counts) >= self.min_observations_for_trend and sum(counts) > 0:
                    matching_c = next(
                        (c for c in clusters if c.fingerprint == fp), None
                    )
                    c_name = matching_c.name if matching_c else f"Cluster {fp[:10]}"
                    comps = matching_c.affected_components if matching_c else []
                    ev = matching_c.evidence if matching_c else []

                    # Monotonically or strictly increasing
                    if counts[-1] > counts[0] and counts[-1] >= 2:
                        conf = ConfidenceEngine.calculate(
                            evidence_count=len(counts),
                            sample_size=len(counts),
                            agreement_rate=0.9,
                        )
                        patterns.append(
                            FailurePattern(
                                pattern_type=PatternType.INCREASING,
                                title=f"Increasing Failure Rate: {c_name}",
                                description=(
                                    f"Failure frequency increased from {counts[0]} to {counts[-1]} "
                                    f"over {len(counts)} consecutive runs."
                                ),
                                fingerprint=fp,
                                frequency=counts[-1],
                                affected_components=comps,
                                confidence=conf,
                                evidence=ev,
                            )
                        )
                    elif counts[-1] < counts[0] and counts[0] >= 2:
                        conf = ConfidenceEngine.calculate(
                            evidence_count=len(counts),
                            sample_size=len(counts),
                            agreement_rate=0.9,
                        )
                        patterns.append(
                            FailurePattern(
                                pattern_type=PatternType.DECREASING,
                                title=f"Decreasing Failure Rate: {c_name}",
                                description=(
                                    f"Failure frequency decreased from {counts[0]} to {counts[-1]} "
                                    f"over {len(counts)} consecutive runs."
                                ),
                                fingerprint=fp,
                                frequency=counts[-1],
                                affected_components=comps,
                                confidence=conf,
                                evidence=ev,
                            )
                        )
                    elif all(x == counts[0] for x in counts) and counts[0] > 0:
                        conf = ConfidenceEngine.calculate(
                            evidence_count=len(counts),
                            sample_size=len(counts),
                            agreement_rate=1.0,
                        )
                        patterns.append(
                            FailurePattern(
                                pattern_type=PatternType.PERSISTENT,
                                title=f"Persistent Failure: {c_name}",
                                description=(
                                    f"Failure remained static at {counts[0]} occurrences across "
                                    f"all {len(counts)} observed runs."
                                ),
                                fingerprint=fp,
                                frequency=counts[-1],
                                affected_components=comps,
                                confidence=conf,
                                evidence=ev,
                            )
                        )

        # De-duplicate patterns by pattern_type and fingerprint
        seen_keys: set[tuple[PatternType, str]] = set()
        unique_patterns: list[FailurePattern] = []
        for p in patterns:
            key = (p.pattern_type, p.fingerprint)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_patterns.append(p)

        return unique_patterns
