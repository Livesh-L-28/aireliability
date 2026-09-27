"""Correlation context propagation using contextvars."""

from __future__ import annotations

import contextvars
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ObservabilityContext(BaseModel):
    """Context container for tracing and correlation."""

    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    span_id: str | None = None
    parent_span_id: str | None = None
    execution_id: str | None = None
    job_id: str | None = None
    tenant_id: str = "default"
    project_id: str = "default"
    namespace: str = "default"
    worker_id: str | None = None
    request_id: str | None = None
    baggage: dict[str, Any] = Field(default_factory=dict)


_CURRENT_OBSERVABILITY_CONTEXT: contextvars.ContextVar[ObservabilityContext | None] = (
    contextvars.ContextVar("current_observability_context", default=None)
)


def get_current_context() -> ObservabilityContext:
    """Retrieve current context or create a default one if unset."""
    ctx = _CURRENT_OBSERVABILITY_CONTEXT.get()
    if ctx is None:
        ctx = ObservabilityContext()
        _CURRENT_OBSERVABILITY_CONTEXT.set(ctx)
    return ctx


def set_current_context(
    ctx: ObservabilityContext,
) -> contextvars.Token[ObservabilityContext | None]:
    """Set the current context and return the token."""
    return _CURRENT_OBSERVABILITY_CONTEXT.set(ctx)


def reset_current_context(
    token: contextvars.Token[ObservabilityContext | None],
) -> None:
    """Reset context using a token."""
    _CURRENT_OBSERVABILITY_CONTEXT.reset(token)


def clear_current_context() -> None:
    """Clear the active observability context."""
    _CURRENT_OBSERVABILITY_CONTEXT.set(None)


def create_trace_context(
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    execution_id: str | None = None,
    job_id: str | None = None,
    tenant_id: str = "default",
    project_id: str = "default",
    namespace: str = "default",
    worker_id: str | None = None,
    request_id: str | None = None,
    **baggage: Any,
) -> ObservabilityContext:
    """Helper to instantiate an ObservabilityContext."""
    return ObservabilityContext(
        trace_id=trace_id or str(uuid4()),
        span_id=span_id,
        parent_span_id=parent_span_id,
        execution_id=execution_id,
        job_id=job_id,
        tenant_id=tenant_id,
        project_id=project_id,
        namespace=namespace,
        worker_id=worker_id,
        request_id=request_id or str(uuid4()),
        baggage=baggage,
    )


@contextmanager
def observability_context(
    ctx: ObservabilityContext | None = None,
    **kwargs: Any,
) -> Generator[ObservabilityContext, None, None]:
    """Context manager for scoping an observability context."""
    if ctx is None:
        parent = _CURRENT_OBSERVABILITY_CONTEXT.get()
        merged = parent.model_dump() if parent else {}
        merged.update({k: v for k, v in kwargs.items() if v is not None})
        if "trace_id" not in merged or not merged["trace_id"]:
            merged["trace_id"] = str(uuid4())
        ctx = ObservabilityContext(**merged)

    token = set_current_context(ctx)
    try:
        yield ctx
    finally:
        reset_current_context(token)
