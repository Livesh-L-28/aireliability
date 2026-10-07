"""API request and response schemas for Reliability API Platform (Phase 46)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _generate_id(prefix: str = "api") -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}_{uuid4().hex[:12]}"


def _utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


class APIHealthResponse(BaseModel):
    """Health check response for the reliability API."""

    status: str = "healthy"
    version: str = "1.4.0"
    timestamp: datetime = Field(default_factory=_utc_now)
    uptime_seconds: float = 0.0


class APIPagination(BaseModel):
    """Cursor-based pagination metadata."""

    limit: int = 50
    cursor: str | None = None
    next_cursor: str | None = None
    total_count: int | None = None


class EvaluationCreateRequest(BaseModel):
    """Request to create and evaluate an execution trace."""

    trace_id: str | None = None
    input_text: str
    output_text: str
    expected_output: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResponse(BaseModel):
    """Result of an evaluation."""

    evaluation_id: str = Field(default_factory=lambda: _generate_id("eval"))
    trace_id: str
    passed: bool
    score: float
    failures: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class DatasetCreateRequest(BaseModel):
    """Request to register a dataset."""

    name: str
    description: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


class DatasetResponse(BaseModel):
    """Dataset registration response."""

    dataset_id: str = Field(default_factory=lambda: _generate_id("ds"))
    name: str
    item_count: int
    created_at: datetime = Field(default_factory=_utc_now)


class APIJobStatus(StrEnum):
    """Lifecycle states of an asynchronous API job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


JobStatus = APIJobStatus


class Job(BaseModel):
    """An asynchronous task execution entity."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(default_factory=lambda: _generate_id("job"))
    operation: str
    status: JobStatus = JobStatus.QUEUED
    tenant_id: str = "default"
    input_payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None


class JobResult(BaseModel):
    """Result emitted by an asynchronous job."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    completed_at: datetime = Field(default_factory=_utc_now)


class WebhookEvent(BaseModel):
    """Event payload for webhook dispatch."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: _generate_id("whevt"))
    event_type: str
    tenant_id: str = "default"
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utc_now)


class WebhookDelivery(BaseModel):
    """Record of a webhook dispatch attempt."""

    model_config = ConfigDict(frozen=True)

    delivery_id: str = Field(default_factory=lambda: _generate_id("whdel"))
    webhook_id: str
    event_id: str
    status_code: int = 200
    success: bool = True
    attempt: int = 1
    timestamp: datetime = Field(default_factory=_utc_now)


class WebhookCreateRequest(BaseModel):
    """Request to register a webhook subscription."""

    url: str
    events: list[str] = Field(default_factory=list)
    secret: str | None = None


class Webhook(BaseModel):
    """Webhook subscription record."""

    model_config = ConfigDict(frozen=True)

    webhook_id: str = Field(default_factory=lambda: _generate_id("wh"))
    tenant_id: str
    url: str
    events: list[str] = Field(default_factory=list)
    secret_hash: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utc_now)


class APIKey(BaseModel):
    """Public metadata for an API key (never contains secret)."""

    key_id: str
    name: str
    tenant_id: str
    scopes: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime | None = None
    revoked: bool = False


APIKeyInfo = APIKey
