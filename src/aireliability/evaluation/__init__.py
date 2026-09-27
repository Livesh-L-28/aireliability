"""Evaluation module for AI Reliability Engine.

Separates deterministic trace evaluation from semantic output evaluation.
"""

from aireliability.core.protocols import Evaluator, Expectation
from aireliability.evaluation import deterministic, semantic
from aireliability.evaluation.assertions import AssertionResult
from aireliability.evaluation.expectations import (
    BaseExpectation,
    MaxCost,
    MaxLatency,
    OutputContains,
    OutputEquals,
    SchemaMatch,
    ToolArguments,
    ToolCalled,
    ToolNotCalled,
    ToolOrder,
)
from aireliability.evaluation.semantic import (
    JudgeResult,
    MockSemanticJudge,
    SemanticEvaluator,
    SemanticExpectation,
    SemanticJudge,
    SemanticRelevance,
    SemanticSimilarity,
)

__all__ = [
    "AssertionResult",
    "BaseExpectation",
    "Evaluator",
    "Expectation",
    "JudgeResult",
    "MaxCost",
    "MaxLatency",
    "MockSemanticJudge",
    "OutputContains",
    "OutputEquals",
    "SchemaMatch",
    "SemanticEvaluator",
    "SemanticExpectation",
    "SemanticJudge",
    "SemanticRelevance",
    "SemanticSimilarity",
    "ToolArguments",
    "ToolCalled",
    "ToolNotCalled",
    "ToolOrder",
    "deterministic",
    "semantic",
]
