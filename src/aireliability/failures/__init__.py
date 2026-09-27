"""Failure analysis and classification module."""

from aireliability.failures.analyzer import FailureAnalyzer
from aireliability.failures.taxonomy import (
    FailureCategory,
    FailureTaxonomy,
    FailureType,
)

__all__ = [
    "FailureAnalyzer",
    "FailureCategory",
    "FailureTaxonomy",
    "FailureType",
]
