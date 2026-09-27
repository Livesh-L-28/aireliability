"""Regression test generation, execution, and baseline tracking module."""

from aireliability.regression.baseline import (
    BaselineComparisonSummary,
    BaselineEntry,
    BaselineManager,
    ComparisonResult,
    ComparisonStatus,
)
from aireliability.regression.generator import RegressionGenerator
from aireliability.regression.minimizer import RegressionMinimizer
from aireliability.regression.models import (
    GenerationMethod,
    GenerationStatus,
    RegressionCandidate,
    RegressionValidation,
)
from aireliability.regression.runner import RegressionRunner, RegressionSuiteResult
from aireliability.regression.synthesizer import RegressionSynthesizer
from aireliability.regression.validator import RegressionValidator

__all__ = [
    "BaselineComparisonSummary",
    "BaselineEntry",
    "BaselineManager",
    "ComparisonResult",
    "ComparisonStatus",
    "GenerationMethod",
    "GenerationStatus",
    "RegressionCandidate",
    "RegressionGenerator",
    "RegressionMinimizer",
    "RegressionRunner",
    "RegressionSuiteResult",
    "RegressionSynthesizer",
    "RegressionValidation",
    "RegressionValidator",
]
