"""Security package for AI Reliability Engine (Phase 28).

Provides secure API gateway, provider-neutral authentication, explicit RBAC,
tenant isolation boundaries, replay protection, security rate limiting,
audit logging, and security telemetry.
"""

from aireliability.security.api_keys import (
    APIKey,
    APIKeyCreationResult,
    APIKeyManager,
)
from aireliability.security.audit import AuditEvent, AuditLogger
from aireliability.security.authentication import (
    APIKeyAuthenticationProvider,
    AuthenticationCoordinator,
    AuthenticationProvider,
    BearerTokenAuthenticationProvider,
    ServiceAuthenticationProvider,
)
from aireliability.security.authorization import AuthorizationEngine
from aireliability.security.errors import (
    AuthenticationError,
    AuthorizationError,
    ExpiredCredentialError,
    InvalidAPIKeyError,
    InvalidTokenError,
    PermissionDeniedError,
    ReplayDetectedError,
    RequestValidationError,
    SecurityError,
    SecurityRateLimitError,
    TenantBoundaryViolationError,
)
from aireliability.security.gateway import SecurityGateway
from aireliability.security.identity import (
    create_anonymous_principal,
    create_identity_context,
    create_system_principal,
)
from aireliability.security.models import (
    AuthenticationMethod,
    AuthenticationResult,
    AuthorizationDecision,
    GatewayRequest,
    GatewayResponse,
    IdentityContext,
    Principal,
    PrincipalType,
    ValidationResult,
)
from aireliability.security.permissions import (
    ALL_STANDARD_PERMISSIONS,
    Permission,
    PermissionManager,
)
from aireliability.security.replay_protection import (
    ReplayProtection,
    ReplayRecord,
)
from aireliability.security.request_validator import RequestValidator
from aireliability.security.roles import (
    STANDARD_ROLES,
    BuiltinRole,
    Role,
    RoleManager,
)
from aireliability.security.security_events import (
    EVT_AUTH_FAILURE,
    EVT_AUTH_SUCCESS,
    EVT_AUTHZ_ALLOWED,
    EVT_AUTHZ_DENIED,
    EVT_BOUNDARY_VIOLATION,
    EVT_KEY_CREATED,
    EVT_KEY_REVOKED,
    EVT_KEY_ROTATED,
    EVT_RATE_LIMIT_TRIGGERED,
    EVT_REPLAY_DETECTED,
    EVT_VALIDATION_FAILURE,
    SecurityTelemetry,
)
from aireliability.security.tokens import (
    SimpleSignedTokenValidator,
    TokenClaims,
    TokenValidationResult,
    TokenValidator,
)

__all__ = [
    "ALL_STANDARD_PERMISSIONS",
    "APIKey",
    "APIKeyAuthenticationProvider",
    "APIKeyCreationResult",
    "APIKeyManager",
    "AuditEvent",
    "AuditLogger",
    "AuthenticationCoordinator",
    "AuthenticationError",
    "AuthenticationMethod",
    "AuthenticationProvider",
    "AuthenticationResult",
    "AuthorizationDecision",
    "AuthorizationEngine",
    "AuthorizationError",
    "BearerTokenAuthenticationProvider",
    "BuiltinRole",
    "EVT_AUTH_FAILURE",
    "EVT_AUTH_SUCCESS",
    "EVT_AUTHZ_ALLOWED",
    "EVT_AUTHZ_DENIED",
    "EVT_BOUNDARY_VIOLATION",
    "EVT_KEY_CREATED",
    "EVT_KEY_REVOKED",
    "EVT_KEY_ROTATED",
    "EVT_RATE_LIMIT_TRIGGERED",
    "EVT_REPLAY_DETECTED",
    "EVT_VALIDATION_FAILURE",
    "ExpiredCredentialError",
    "GatewayRequest",
    "GatewayResponse",
    "IdentityContext",
    "InvalidAPIKeyError",
    "InvalidTokenError",
    "Permission",
    "PermissionDeniedError",
    "PermissionManager",
    "Principal",
    "PrincipalType",
    "ReplayDetectedError",
    "ReplayProtection",
    "ReplayRecord",
    "RequestValidationError",
    "RequestValidator",
    "Role",
    "RoleManager",
    "STANDARD_ROLES",
    "SecurityError",
    "SecurityGateway",
    "SecurityRateLimitError",
    "SecurityTelemetry",
    "ServiceAuthenticationProvider",
    "SimpleSignedTokenValidator",
    "TenantBoundaryViolationError",
    "TokenClaims",
    "TokenValidationResult",
    "TokenValidator",
    "ValidationResult",
    "create_anonymous_principal",
    "create_identity_context",
    "create_system_principal",
]
