"""Authentication providers and coordinator for Phase 28."""

from typing import Protocol, runtime_checkable

from aireliability.security.api_keys import APIKeyManager
from aireliability.security.errors import (
    ExpiredCredentialError,
    InvalidAPIKeyError,
)
from aireliability.security.models import (
    AuthenticationMethod,
    AuthenticationResult,
    GatewayRequest,
    Principal,
    PrincipalType,
)
from aireliability.security.roles import RoleManager
from aireliability.security.tokens import TokenValidator
from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)


@runtime_checkable
class AuthenticationProvider(Protocol):
    """Protocol for provider-neutral authentication mechanisms."""

    def authenticate(self, request: GatewayRequest) -> AuthenticationResult:
        """Evaluate credentials on request and return AuthenticationResult."""
        ...


class APIKeyAuthenticationProvider:
    """Authenticates inbound requests using hashed API keys."""

    def __init__(
        self,
        api_key_manager: APIKeyManager,
        role_manager: RoleManager | None = None,
    ) -> None:
        self.api_key_manager = api_key_manager
        self.role_manager = role_manager or RoleManager()

    def authenticate(self, request: GatewayRequest) -> AuthenticationResult:
        api_key = request.api_key or request.headers.get("x-api-key")
        if not api_key:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.API_KEY,
                failure_reason="No API key provided.",
            )

        try:
            key_record = self.api_key_manager.verify_key(api_key)
        except InvalidAPIKeyError as e:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.API_KEY,
                failure_reason=str(e),
            )
        except ExpiredCredentialError as e:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.API_KEY,
                failure_reason=str(e),
            )

        # Expand permissions from roles + direct permissions
        expanded_perms = set(key_record.permissions)
        expanded_perms.update(
            self.role_manager.get_permissions_for_roles(key_record.roles)
        )

        principal = Principal(
            principal_id=key_record.key_id,
            principal_type=PrincipalType.USER,
            tenant_id=key_record.tenant_id,
            project_id=key_record.project_id,
            namespace=key_record.namespace,
            roles=key_record.roles,
            permissions=sorted(expanded_perms),
            authenticated=True,
            authentication_method=AuthenticationMethod.API_KEY,
            metadata={"key_prefix": key_record.key_prefix, "name": key_record.name},
        )
        return AuthenticationResult(
            authenticated=True,
            principal=principal,
            method=AuthenticationMethod.API_KEY,
        )


class BearerTokenAuthenticationProvider:
    """Authenticates inbound requests using bearer tokens."""

    def __init__(
        self,
        token_validator: TokenValidator,
        role_manager: RoleManager | None = None,
    ) -> None:
        self.token_validator = token_validator
        self.role_manager = role_manager or RoleManager()

    def authenticate(self, request: GatewayRequest) -> AuthenticationResult:
        token = request.bearer_token or request.headers.get("authorization")
        if not token:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.BEARER_TOKEN,
                failure_reason="No bearer token provided.",
            )

        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        result = self.token_validator.validate_token(token)
        if not result.valid or not result.claims:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.BEARER_TOKEN,
                failure_reason=result.reason or "Invalid bearer token.",
            )

        claims = result.claims
        expanded_perms = set(claims.permissions)
        expanded_perms.update(self.role_manager.get_permissions_for_roles(claims.roles))

        principal = Principal(
            principal_id=claims.sub,
            principal_type=PrincipalType.USER,
            tenant_id=claims.tenant_id,
            project_id=claims.project_id,
            namespace=claims.namespace,
            roles=claims.roles,
            permissions=sorted(expanded_perms),
            authenticated=True,
            authentication_method=AuthenticationMethod.BEARER_TOKEN,
            metadata={"iss": claims.iss, "aud": claims.aud},
        )
        return AuthenticationResult(
            authenticated=True,
            principal=principal,
            method=AuthenticationMethod.BEARER_TOKEN,
        )


class ServiceAuthenticationProvider:
    """Authenticates internal services and worker nodes."""

    def __init__(
        self,
        valid_service_tokens: dict[str, str] | None = None,
        role_manager: RoleManager | None = None,
    ) -> None:
        self.valid_service_tokens = valid_service_tokens or {}
        self.role_manager = role_manager or RoleManager()

    def authenticate(self, request: GatewayRequest) -> AuthenticationResult:
        svc_header = request.headers.get("x-service-identity")
        svc_token = request.headers.get("x-service-token")
        if not svc_header or not svc_token:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.SERVICE_IDENTITY,
                failure_reason="No service credentials provided.",
            )

        expected = self.valid_service_tokens.get(svc_header)
        if not expected or expected != svc_token:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.SERVICE_IDENTITY,
                failure_reason="Invalid service credentials.",
            )

        role = "SERVICE"
        perms = sorted(self.role_manager.get_permissions_for_roles([role]))
        principal = Principal(
            principal_id=svc_header,
            principal_type=PrincipalType.SERVICE,
            tenant_id=request.tenant_id or DEFAULT_TENANT_ID,
            project_id=request.project_id or DEFAULT_PROJECT_ID,
            namespace=request.namespace or DEFAULT_NAMESPACE,
            roles=[role],
            permissions=perms,
            authenticated=True,
            authentication_method=AuthenticationMethod.SERVICE_IDENTITY,
        )
        return AuthenticationResult(
            authenticated=True,
            principal=principal,
            method=AuthenticationMethod.SERVICE_IDENTITY,
        )


class AuthenticationCoordinator:
    """Orchestrates authentication across registered providers."""

    def __init__(
        self,
        providers: list[AuthenticationProvider] | None = None,
        allow_anonymous: bool = True,
    ) -> None:
        self.providers = list(providers or [])
        self.allow_anonymous = allow_anonymous

    def authenticate(self, request: GatewayRequest) -> AuthenticationResult:
        """Attempt authentication using configured providers."""
        last_failure_reason: str | None = None

        for provider in self.providers:
            result = provider.authenticate(request)
            if result.authenticated:
                return result
            if result.failure_reason and "No " not in result.failure_reason:
                # Explicit credential was provided but failed verification
                last_failure_reason = result.failure_reason

        if last_failure_reason:
            return AuthenticationResult(
                authenticated=False,
                principal=Principal(),
                method=AuthenticationMethod.ANONYMOUS,
                failure_reason=last_failure_reason,
            )

        if self.allow_anonymous:
            # Fallback to anonymous unauthenticated principal with default scope
            anon_principal = Principal(
                principal_id="anonymous",
                principal_type=PrincipalType.ANONYMOUS,
                tenant_id=request.tenant_id or DEFAULT_TENANT_ID,
                project_id=request.project_id or DEFAULT_PROJECT_ID,
                namespace=request.namespace or DEFAULT_NAMESPACE,
                roles=["VIEWER"],
                permissions=["jobs.read", "executions.read"],
                authenticated=False,
                authentication_method=AuthenticationMethod.ANONYMOUS,
            )
            return AuthenticationResult(
                authenticated=True,
                principal=anon_principal,
                method=AuthenticationMethod.ANONYMOUS,
            )

        return AuthenticationResult(
            authenticated=False,
            principal=Principal(),
            method=AuthenticationMethod.ANONYMOUS,
            failure_reason="Authentication required.",
        )
