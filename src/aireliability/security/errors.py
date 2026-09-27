"""Structured security exceptions for the AI Reliability Engine (Phase 28).

All security exceptions avoid leaking credentials, raw tokens, or secrets.
"""


class SecurityError(Exception):
    """Base exception for all security, authentication, and authorization errors."""

    def __init__(self, message: str = "A security error occurred.") -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(SecurityError):
    """Raised when authentication fails (missing, invalid, or expired credentials)."""

    def __init__(self, message: str = "Authentication failed.") -> None:
        super().__init__(message)


class InvalidAPIKeyError(AuthenticationError):
    """Raised when an API key is invalid or unrecognized."""

    def __init__(self, message: str = "Invalid API key.") -> None:
        super().__init__(message)


class ExpiredCredentialError(AuthenticationError):
    """Raised when an API key or token has expired."""

    def __init__(self, message: str = "Credential has expired.") -> None:
        super().__init__(message)


class InvalidTokenError(AuthenticationError):
    """Raised when a bearer token is invalid, malformed, or has invalid claims."""

    def __init__(self, message: str = "Invalid bearer token.") -> None:
        super().__init__(message)


class AuthorizationError(SecurityError):
    """Raised when a principal is not authorized to perform an action."""

    def __init__(self, message: str = "Authorization denied.") -> None:
        super().__init__(message)


class PermissionDeniedError(AuthorizationError):
    """Raised when a principal lacks a required permission."""

    def __init__(
        self,
        permission: str = "",
        message: str | None = None,
    ) -> None:
        msg = message or f"Permission denied: '{permission}'."
        super().__init__(msg)
        self.permission = permission


class TenantBoundaryViolationError(AuthorizationError):
    """Raised when an action violates tenant, project, or namespace isolation."""

    def __init__(
        self,
        tenant_id: str = "",
        message: str | None = None,
    ) -> None:
        msg = (
            message
            or f"Tenant boundary violation: access to tenant '{tenant_id}' denied."
        )
        super().__init__(msg)
        self.tenant_id = tenant_id


class ReplayDetectedError(SecurityError):
    """Raised when a replayed or duplicate request/nonce is detected."""

    def __init__(
        self, message: str = "Replay detected: duplicate request or nonce."
    ) -> None:
        super().__init__(message)


class SecurityRateLimitError(SecurityError):
    """Raised when a security rate limit is exceeded."""

    def __init__(self, message: str = "Security rate limit exceeded.") -> None:
        super().__init__(message)


class RequestValidationError(SecurityError):
    """Raised when a gateway request fails structural or policy validation."""

    def __init__(self, message: str = "Request validation failed.") -> None:
        super().__init__(message)
