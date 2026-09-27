"""Assertion models and utilities for trace evaluation."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssertionResult(BaseModel):
    """Result of an assertion check against an execution trace."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
