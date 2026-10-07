"""Evaluation regression submodule."""

from aireliability.evaluation.regression.diff import EvaluationRegressionDetector
from aireliability.evaluation.regression.models import (
    ComprehensiveRegressionSummary,
    DimensionalRegression,
    RegressionDimension,
)

__all__ = [
    "ComprehensiveRegressionSummary",
    "DimensionalRegression",
    "EvaluationRegressionDetector",
    "RegressionDimension",
]
