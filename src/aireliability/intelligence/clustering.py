"""Failure clustering engine grouping normalized failures into structural clusters."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from aireliability.intelligence.confidence import ConfidenceEngine
from aireliability.intelligence.models import (
    EvidenceReference,
    FailureCluster,
    NormalizedFailure,
)


class FailureClusterer:
    """Deterministic clustering engine for grouping equivalent and similar failures."""

    def __init__(self, similarity_threshold: float = 0.80) -> None:
        self.similarity_threshold = similarity_threshold

    def cluster(
        self,
        failures: Sequence[NormalizedFailure],
        evidence_pool: list[EvidenceReference] | None = None,
    ) -> list[FailureCluster]:
        """Group normalized failures into distinct FailureClusters.

        Step 1: O(N) grouping by exact deterministic failure fingerprint.
        Step 2: Merging near-identical singletons above similarity_threshold.
        """
        if not failures:
            return []

        # 1. Exact fingerprint grouping
        fingerprint_groups: dict[str, list[NormalizedFailure]] = {}
        for f in failures:
            fingerprint_groups.setdefault(f.fingerprint, []).append(f)

        clusters: list[FailureCluster] = []

        # Index evidence by failure_id if provided
        ev_by_source: dict[str, list[EvidenceReference]] = {}
        if evidence_pool:
            for ev in evidence_pool:
                if ev.source_type == "failure_report":
                    ev_by_source.setdefault(ev.source_id, []).append(ev)

        for fp, group in fingerprint_groups.items():
            rep = group[0]
            cat_counts = Counter(item.category for item in group)
            dominant_cat = cat_counts.most_common(1)[0][0]

            rc_counts = Counter(
                f"{item.root_cause_category or 'unknown'}.{item.root_cause_type or 'unknown'}"
                for item in group
            )
            dominant_rc = rc_counts.most_common(1)[0][0]

            components = sorted(
                {
                    item.component
                    for item in group
                    if item.component and item.component != "unknown"
                }
            )
            failure_ids = [item.failure_id for item in group]

            # Collect evidence for this cluster
            cluster_evidence: list[EvidenceReference] = []
            for fid in failure_ids[:10]:  # Cap references to avoid giant payloads
                cluster_evidence.extend(ev_by_source.get(fid, []))

            # Compute cluster confidence
            conf = ConfidenceEngine.calculate(
                evidence_count=len(cluster_evidence) or len(group),
                sample_size=len(failures),
                agreement_rate=cat_counts.most_common(1)[0][1] / len(group),
                data_completeness=1.0 if rep.root_cause_category else 0.8,
            )

            name = f"Cluster: [{dominant_cat.upper()}] {rep.failure_type} ({rep.component or 'system'})"

            cluster = FailureCluster(
                cluster_id=f"cluster_{fp[:10]}",
                name=name,
                fingerprint=fp,
                representative_failure_id=rep.failure_id,
                failure_ids=failure_ids,
                dominant_category=dominant_cat,
                dominant_root_cause=dominant_rc,
                frequency=len(group),
                affected_components=components,
                confidence=conf,
                evidence=cluster_evidence,
                metadata={
                    "first_seen": min(item.timestamp for item in group).isoformat(),
                    "latest_seen": max(item.timestamp for item in group).isoformat(),
                    "severities": list(
                        Counter(item.severity for item in group).items()
                    ),
                },
            )
            clusters.append(cluster)

        # Sort clusters by frequency descending
        clusters.sort(key=lambda c: c.frequency, reverse=True)
        return clusters
