"""Identity utilities and helper factories for Phase 28."""

from aireliability.security.models import (
    AuthenticationMethod,
    IdentityContext,
    Principal,
    PrincipalType,
)
from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)


def create_system_principal() -> Principal:
    """Create a fully privileged SYSTEM identity principal."""
    return Principal(
        principal_id="system",
        principal_type=PrincipalType.SYSTEM,
        tenant_id=DEFAULT_TENANT_ID,
        project_id=DEFAULT_PROJECT_ID,
        namespace=DEFAULT_NAMESPACE,
        roles=["ADMIN"],
        permissions=["*"],
        authenticated=True,
        authentication_method=AuthenticationMethod.INTERNAL,
    )


def create_anonymous_principal() -> Principal:
    """Create an unauthenticated ANONYMOUS principal."""
    return Principal(
        principal_id="anonymous",
        principal_type=PrincipalType.ANONYMOUS,
        tenant_id=DEFAULT_TENANT_ID,
        project_id=DEFAULT_PROJECT_ID,
        namespace=DEFAULT_NAMESPACE,
        roles=["VIEWER"],
        permissions=["jobs.read", "executions.read"],
        authenticated=False,
        authentication_method=AuthenticationMethod.ANONYMOUS,
    )


def create_identity_context(
    principal: Principal | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> IdentityContext:
    """Wrap a principal into an IdentityContext with request metadata."""
    p = principal or create_anonymous_principal()
    return IdentityContext(
        principal=p,
        client_ip_hash=client_ip,
        user_agent=user_agent,
    )
