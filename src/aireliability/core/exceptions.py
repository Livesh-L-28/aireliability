"""Exceptions for the AI Reliability Engine."""


class AIReliabilityError(Exception):
    """Base exception for all aireliability errors."""


class ExecutionError(AIReliabilityError):
    """Raised when an execution trace or runner fails unexpectedly."""


class EvaluationError(AIReliabilityError):
    """Raised when evaluation of a trace or assertion encounters an error."""


class FailureAnalysisError(AIReliabilityError):
    """Raised during failure classification or root cause analysis."""


class RegressionTestError(AIReliabilityError):
    """Raised during regression test generation or synthesis."""


class StorageError(AIReliabilityError):
    """Raised when persistence or storage operations fail."""
