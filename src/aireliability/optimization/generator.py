"""Candidate configuration generator with registry validation and deduplication."""

from __future__ import annotations

import logging

from aireliability.optimization.models import (
    CandidateStatus,
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationProblem,
)
from aireliability.optimization.strategies import BaseSearchStrategy, get_strategy
from aireliability.optimization.variables import (
    VariableRegistry,
    get_default_variable_registry,
)

logger = logging.getLogger(__name__)


class CandidateGenerator:
    """Generates and validates candidate parameter configurations."""

    def __init__(self, registry: VariableRegistry | None = None) -> None:
        self.registry = registry or get_default_variable_registry()

    def generate(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        strategy: BaseSearchStrategy | str = "random",
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate, validate, and deduplicate candidates using the selected strategy."""
        strat = get_strategy(strategy) if isinstance(strategy, str) else strategy

        raw_candidates = strat.generate_candidates(
            problem=problem,
            budget=budget,
            seed=seed,
            history=history,
        )

        validated_candidates: list[OptimizationCandidate] = []
        seen_fingerprints: set[str] = set()

        if problem.baseline_config.fingerprint:
            seen_fingerprints.add(problem.baseline_config.fingerprint)

        if history:
            for past in history:
                seen_fingerprints.add(past.fingerprint)

        limit = budget.max_candidates

        for cand in raw_candidates:
            if len(validated_candidates) >= limit:
                break

            # Deduplication
            if cand.fingerprint in seen_fingerprints:
                continue

            seen_fingerprints.add(cand.fingerprint)

            # Security and registry validation
            is_valid, violations = self.registry.validate_configuration(
                cand.configuration.values,
                allowed_variables=problem.variables,
            )

            if not is_valid:
                cand.is_feasible = False
                cand.status = CandidateStatus.INVALID
                cand.constraint_violations.extend(violations)
                cand.explanation = (
                    f"Registry/Security violation: {'; '.join(violations)}"
                )

            validated_candidates.append(cand)

        return validated_candidates
