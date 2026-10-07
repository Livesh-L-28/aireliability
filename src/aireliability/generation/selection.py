"""Deterministic candidate ranking, diversification, and budget selection."""

from __future__ import annotations

from collections import defaultdict

from aireliability.generation.models import (
    GeneratedTest,
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestRiskLevel,
)


class TestSelector:
    """Ranks and selects the highest-value test candidates subject to generation budgets."""

    def select(
        self,
        tests: list[GeneratedTest],
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        """Filter, rank, and budget candidates into a final selection pool."""
        if not tests:
            return []

        # 1. Quality & Confidence thresholding
        filtered: list[GeneratedTest] = []
        for t in tests:
            quality = t.quality_score.total_score if t.quality_score else 1.0
            if quality < config.min_quality_threshold:
                continue
            if t.confidence < config.min_confidence_threshold:
                continue
            filtered.append(t)

        # 2. Priority & Risk sorting key
        # Safety/Security/Critical first, then highest quality, then confidence, then test_id
        priority_rank = {
            TestPriority.CRITICAL: 4,
            TestPriority.HIGH: 3,
            TestPriority.MEDIUM: 2,
            TestPriority.LOW: 1,
        }
        risk_rank = {
            TestRiskLevel.CRITICAL: 4,
            TestRiskLevel.HIGH: 3,
            TestRiskLevel.MEDIUM: 2,
            TestRiskLevel.LOW: 1,
        }

        def _sort_key(t: GeneratedTest) -> tuple[int, int, float, float, str]:
            p_val = priority_rank.get(t.priority, 1)
            r_val = risk_rank.get(t.risk_level, 1)
            q_val = t.quality_score.total_score if t.quality_score else 0.0
            c_val = t.confidence
            return (-p_val, -r_val, -q_val, -c_val, t.test_id)

        filtered.sort(key=_sort_key)

        # 3. Budget enforcement
        selected: list[GeneratedTest] = []
        source_counts: dict[str, int] = defaultdict(int)
        component_counts: dict[str, int] = defaultdict(int)
        mutation_count = 0

        for t in filtered:
            if len(selected) >= config.max_candidates:
                break

            # Mutation budget
            if t.strategy == GenerationStrategy.MUTATION_BASED:
                if mutation_count >= config.max_mutation_count:
                    continue
                mutation_count += 1

            # Source budget
            src_id = t.provenance.source_id
            if source_counts[src_id] >= config.max_tests_per_source:
                continue

            # Component budget (if component tag exists)
            comp = next(
                (tag.split(":")[1] for tag in t.tags if tag.startswith("component:")),
                None,
            )
            if comp and component_counts[comp] >= config.max_tests_per_component:
                continue

            # Accept candidate
            selected.append(t)
            source_counts[src_id] += 1
            if comp:
                component_counts[comp] += 1

        return selected
