"""Core security, identity, and authorization models for Phase 28."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)


def _generate_security_id(prefix: str = "") -> str:
    """Generate a unique hex identifier, optionally with a prefix."""
    generated = uuid4().hex
    return f"{prefix}_{generated}" if prefix else generated


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class PrincipalType(StrEnum):
    """Supported identity principal types."""

    USER = "user"
    SERVICE = "service"
    WORKER = "worker"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"


class AuthenticationMethod(StrEnum):
    """Method used to authenticate the principal."""

    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    SERVICE_IDENTITY = "service_identity"
    ANONYMOUS = "anonymous"
    INTERNAL = "internal"


class AuthorizationDecision(StrEnum):
    """Result decision of an authorization evaluation."""

    ALLOW = "allow"
    DENY = "deny"


class Principal(BaseModel):
    """Authenticated identity principal propagating through the gateway."""

    model_config = ConfigDict(frozen=True)

    principal_id: str = "anonymous"
    principal_type: PrincipalType = PrincipalType.ANONYMOUS
    tenant_id: str = DEFAULT_TENANT_ID
    project_id: str = DEFAULT_PROJECT_ID
    namespace: str = DEFAULT_NAMESPACE
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    authenticated: bool = False
    authentication_method: AuthenticationMethod = AuthenticationMethod.ANONYMOUS
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return self.authenticated

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self.roles or "security.manage" in self.permissions


class IdentityContext(BaseModel):
    """Identity context attached to an inbound request."""

    model_config = ConfigDict(frozen=True)

    principal: Principal
    request_id: str = Field(default_factory=lambda: _generate_security_id("req"))
    client_ip_hash: str | None = None
    user_agent: str | None = None
    timestamp: datetime = Field(default_factory=_utc_now)


class AuthenticationResult(BaseModel):
    """Result of an authentication attempt."""

    model_config = ConfigDict(frozen=True)

    authenticated: bool
    principal: Principal
    method: AuthenticationMethod = AuthenticationMethod.ANONYMOUS
    failure_reason: str | None = None


class ValidationResult(BaseModel):
    """Result of request validation."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class GatewayRequest(BaseModel):
    """Provider-neutral request submitted to the API Gateway."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(default_factory=lambda: _generate_security_id("req"))
    action: str = "jobs.submit"
    resource: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    api_key: str | None = None
    bearer_token: str | None = None
    tenant_id: str = DEFAULT_TENANT_ID
    project_id: str = DEFAULT_PROJECT_ID
    namespace: str = DEFAULT_NAMESPACE
    nonce: str | None = None
    timestamp: datetime = Field(default_factory=_utc_now)
    client_ip: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GatewayResponse(BaseModel):
    """Structured response from the API Gateway."""

    model_config = ConfigDict(frozen=True)

    status: str  # "success", "rejected", "error"
    request_id: str
    allowed: bool
    principal: Principal | None = None
    reason: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utc_now)
