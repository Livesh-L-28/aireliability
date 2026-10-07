"""Base protocol and abstract class for deterministic candidate search strategies."""

from __future__ import annotations

import abc
from typing import Any

from aireliability.optimization.fingerprint import create_configuration
from aireliability.optimization.models import (
    CandidateStatus,
    OptimizationBudget,
    OptimizationCandidate,
    OptimizationProblem,
)


class BaseSearchStrategy(abc.ABC):
    """Abstract base class for all deterministic search strategies."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abc.abstractmethod
    def generate_candidates(
        self,
        problem: OptimizationProblem,
        budget: OptimizationBudget,
        seed: int = 42,
        history: list[OptimizationCandidate] | None = None,
    ) -> list[OptimizationCandidate]:
        """Generate candidate configurations bounded by problem variables and budget."""
        raise NotImplementedError

    def _build_candidate(
        self,
        values: dict[str, Any],
        generation_params: dict[str, Any] | None = None,
        parent_candidate_id: str | None = None,
    ) -> OptimizationCandidate:
        """Create a well-formed OptimizationCandidate with deterministic fingerprint."""
        config = create_configuration(values)
        return OptimizationCandidate(
            configuration=config,
            fingerprint=config.fingerprint,
            parent_candidate_id=parent_candidate_id,
            generation_strategy=self.name,
            generation_params=generation_params or {},
            status=CandidateStatus.PENDING,
        )
