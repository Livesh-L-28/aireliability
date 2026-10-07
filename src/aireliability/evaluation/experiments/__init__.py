"""A/B experiments and variant evaluation submodule."""

from aireliability.evaluation.experiments.manager import ExperimentManager
from aireliability.evaluation.experiments.models import (
    ABComparisonResult,
    VariantConfig,
    VariantResult,
)

__all__ = [
    "ABComparisonResult",
    "ExperimentManager",
    "VariantConfig",
    "VariantResult",
]
