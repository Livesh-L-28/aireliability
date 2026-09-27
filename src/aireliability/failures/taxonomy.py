"""Failure taxonomy enumerations and definitions for AI Reliability Engine."""

from enum import StrEnum


class FailureCategory(StrEnum):
    """Broad categories for AI failures and regressions."""

    TASK = "task"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    OUTPUT = "output"
    SAFETY = "safety"
    PERFORMANCE = "performance"
    CUSTOM = "custom"


class FailureType(StrEnum):
    """Specific failure types within each category."""

    # TASK
    TASK_INCOMPLETE = "task_incomplete"
    TASK_INCORRECT = "task_incorrect"

    # TOOL
    WRONG_TOOL = "wrong_tool"
    WRONG_ARGUMENT = "wrong_argument"
    WRONG_ORDER = "wrong_order"
    UNNECESSARY_TOOL = "unnecessary_tool"

    # RETRIEVAL
    MISSING_CONTEXT = "missing_context"
    IRRELEVANT_CONTEXT = "irrelevant_context"
    CONFLICTING_CONTEXT = "conflicting_context"

    # OUTPUT
    SCHEMA_ERROR = "schema_error"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    HALLUCINATION = "hallucination"
    SEMANTIC_VIOLATION = "semantic_violation"
    SEMANTIC_RELEVANCE = "semantic_relevance"
    SEMANTIC_SIMILARITY = "semantic_similarity"

    # SAFETY
    SAFETY_VIOLATION = "safety_violation"

    # PERFORMANCE
    LATENCY = "latency"
    TOKEN_OVERUSE = "token_overuse"
    COST = "cost"

    # CUSTOM
    CUSTOM = "custom"


class FailureTaxonomy:
    """Extensible registry and mapping for failure categories and types."""

    _CATEGORY_TYPE_MAP: dict[str, set[str]] = {
        FailureCategory.TASK.value: {
            FailureType.TASK_INCOMPLETE.value,
            FailureType.TASK_INCORRECT.value,
        },
        FailureCategory.TOOL.value: {
            FailureType.WRONG_TOOL.value,
            FailureType.WRONG_ARGUMENT.value,
            FailureType.WRONG_ORDER.value,
            FailureType.UNNECESSARY_TOOL.value,
        },
        FailureCategory.RETRIEVAL.value: {
            FailureType.MISSING_CONTEXT.value,
            FailureType.IRRELEVANT_CONTEXT.value,
            FailureType.CONFLICTING_CONTEXT.value,
        },
        FailureCategory.OUTPUT.value: {
            FailureType.SCHEMA_ERROR.value,
            FailureType.UNSUPPORTED_CLAIM.value,
            FailureType.HALLUCINATION.value,
            FailureType.SEMANTIC_VIOLATION.value,
            FailureType.SEMANTIC_RELEVANCE.value,
            FailureType.SEMANTIC_SIMILARITY.value,
        },
        FailureCategory.SAFETY.value: {
            FailureType.SAFETY_VIOLATION.value,
        },
        FailureCategory.PERFORMANCE.value: {
            FailureType.LATENCY.value,
            FailureType.TOKEN_OVERUSE.value,
            FailureType.COST.value,
        },
    }

    @classmethod
    def register_type(
        cls, category: str | FailureCategory, failure_type: str | FailureType
    ) -> None:
        """Register a new failure type under a category to extend the taxonomy."""
        cat_str = (
            category.value if isinstance(category, FailureCategory) else str(category)
        )
        type_str = (
            failure_type.value
            if isinstance(failure_type, FailureType)
            else str(failure_type)
        )
        if cat_str not in cls._CATEGORY_TYPE_MAP:
            cls._CATEGORY_TYPE_MAP[cat_str] = set()
        cls._CATEGORY_TYPE_MAP[cat_str].add(type_str)

    @classmethod
    def get_category_for_type(cls, failure_type: str | FailureType) -> str | None:
        """Look up the parent category for a given failure type."""
        type_str = (
            failure_type.value
            if isinstance(failure_type, FailureType)
            else str(failure_type)
        )
        for cat, types in cls._CATEGORY_TYPE_MAP.items():
            if type_str in types:
                return cat
        return None

    @classmethod
    def is_valid_type(cls, failure_type: str | FailureType) -> bool:
        """Check whether a failure type is registered in the taxonomy."""
        type_str = (
            failure_type.value
            if isinstance(failure_type, FailureType)
            else str(failure_type)
        )
        return any(type_str in types for types in cls._CATEGORY_TYPE_MAP.values())

    @classmethod
    def all_categories(cls) -> list[str]:
        """Return all registered category names."""
        return list(cls._CATEGORY_TYPE_MAP.keys())

    @classmethod
    def types_for_category(cls, category: str | FailureCategory) -> set[str]:
        """Return all failure types under a specified category."""
        cat_str = (
            category.value if isinstance(category, FailureCategory) else str(category)
        )
        return set(cls._CATEGORY_TYPE_MAP.get(cat_str, set()))


__all__ = ["FailureCategory", "FailureTaxonomy", "FailureType"]
