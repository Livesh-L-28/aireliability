"""Deduplication engine for generated AI tests supporting exact and near-duplicate pruning."""

from __future__ import annotations

from aireliability.generation.fingerprint import (
    compute_fingerprint,
    compute_token_similarity,
)
from aireliability.generation.models import GeneratedTest


class TestDeduplicator:
    """Deterministic deduplicator using exact fingerprinting and structural token similarity."""

    def __init__(
        self,
        mode: str = "exact_and_near",
        near_duplicate_threshold: float = 0.85,
    ) -> None:
        self.mode = mode.lower()
        self.near_duplicate_threshold = near_duplicate_threshold

    def _is_better_candidate(
        self, cand_a: GeneratedTest, cand_b: GeneratedTest
    ) -> bool:
        """Deterministically determine if candidate A is higher quality than candidate B."""
        score_a = cand_a.quality_score.total_score if cand_a.quality_score else 0.0
        score_b = cand_b.quality_score.total_score if cand_b.quality_score else 0.0
        if score_a != score_b:
            return score_a > score_b

        if cand_a.confidence != cand_b.confidence:
            return cand_a.confidence > cand_b.confidence

        criteria_a = len(cand_a.expected_criteria)
        criteria_b = len(cand_b.expected_criteria)
        if criteria_a != criteria_b:
            return criteria_a > criteria_b

        return cand_a.test_id < cand_b.test_id

    def deduplicate(
        self,
        tests: list[GeneratedTest],
    ) -> tuple[list[GeneratedTest], int]:
        """Deduplicate tests and return (deduplicated_tests, dropped_duplicate_count)."""
        if self.mode == "off" or not tests:
            return list(tests), 0

        # Step 1: Ensure fingerprints are computed
        prepared: list[GeneratedTest] = []
        for t in tests:
            if not t.fingerprint:
                fp = compute_fingerprint(t)
                prepared.append(t.model_copy(update={"fingerprint": fp}))
            else:
                prepared.append(t)

        # Step 2: Exact fingerprint deduplication
        fingerprint_map: dict[str, GeneratedTest] = {}
        exact_dropped = 0
        for t in prepared:
            if t.fingerprint in fingerprint_map:
                existing = fingerprint_map[t.fingerprint]
                if self._is_better_candidate(t, existing):
                    fingerprint_map[t.fingerprint] = t
                exact_dropped += 1
            else:
                fingerprint_map[t.fingerprint] = t

        unique_tests = list(fingerprint_map.values())

        if self.mode != "exact_and_near" or len(unique_tests) <= 1:
            return unique_tests, exact_dropped

        # Step 3: Near-duplicate detection
        # Sort deterministically before pairwise pass
        unique_tests.sort(
            key=lambda x: (
                -(x.quality_score.total_score if x.quality_score else 0.0),
                -x.confidence,
                x.test_id,
            )
        )

        selected: list[GeneratedTest] = []
        near_dropped = 0

        for candidate in unique_tests:
            is_near_dup = False
            for kept in selected:
                sim = compute_token_similarity(candidate, kept)
                if sim >= self.near_duplicate_threshold:
                    is_near_dup = True
                    near_dropped += 1
                    break
            if not is_near_dup:
                selected.append(candidate)

        total_dropped = exact_dropped + near_dropped
        return selected, total_dropped
