"""Unified Secure API Gateway coordinating validation, authentication,
authorization, replay protection, rate limiting, and audit logging.
"""

import asyncio
from typing import Any

from aireliability.security.api_keys import APIKeyManager
from aireliability.security.audit import AuditLogger
from aireliability.security.authentication import (
    APIKeyAuthenticationProvider,
    AuthenticationCoordinator,
    AuthenticationProvider,
    BearerTokenAuthenticationProvider,
    ServiceAuthenticationProvider,
)
from aireliability.security.authorization import AuthorizationEngine
from aireliability.security.models import (
    AuthenticationMethod,
    AuthenticationResult,
    AuthorizationDecision,
    GatewayRequest,
    GatewayResponse,
    Principal,
)
from aireliability.security.permissions import PermissionManager
from aireliability.security.replay_protection import ReplayProtection
from aireliability.security.request_validator import RequestValidator
from aireliability.security.roles import RoleManager
from aireliability.security.security_events import (
    EVT_AUTH_FAILURE,
    EVT_AUTH_SUCCESS,
    EVT_AUTHZ_ALLOWED,
    EVT_AUTHZ_DENIED,
    EVT_BOUNDARY_VIOLATION,
    EVT_RATE_LIMIT_TRIGGERED,
    EVT_REPLAY_DETECTED,
    EVT_VALIDATION_FAILURE,
    SecurityTelemetry,
)
from aireliability.security.tokens import SimpleSignedTokenValidator, TokenValidator
from aireliability.telemetry.sanitizer import SanitizationPolicy
from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)
from aireliability.tenancy.rate_limiter import RateLimiter


class SecurityGateway:
    """Production-grade secure API Gateway and Security Boundary (Phase 28)."""

    def __init__(
        self,
        *,
        auth_coordinator: AuthenticationCoordinator | None = None,
        authz_engine: AuthorizationEngine | None = None,
        request_validator: RequestValidator | None = None,
        replay_protection: ReplayProtection | None = None,
        rate_limiter: RateLimiter | None = None,
        audit_logger: AuditLogger | None = None,
        telemetry: SecurityTelemetry | None = None,
        api_key_manager: APIKeyManager | None = None,
        token_validator: TokenValidator | None = None,
        permission_manager: PermissionManager | None = None,
        role_manager: RoleManager | None = None,
        storage: Any | None = None,
        sanitizer: SanitizationPolicy | None = None,
    ) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()
        self.storage = storage

        # Shared RBAC Managers
        self.permissions = permission_manager or PermissionManager()
        self.roles = role_manager or RoleManager()
        self.api_keys = api_key_manager or APIKeyManager(storage=self.storage)
        self.tokens = token_validator or SimpleSignedTokenValidator()

        # Core Pipeline Components
        self.validator = request_validator or RequestValidator()
        self.replay = replay_protection or ReplayProtection(storage=self.storage)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.audit = audit_logger or AuditLogger(
            storage=self.storage, sanitizer=self.sanitizer
        )
        self.telemetry = telemetry or SecurityTelemetry()

        # Auth & Authz
        if auth_coordinator is not None:
            self.auth = auth_coordinator
        else:
            providers: list[AuthenticationProvider] = [
                APIKeyAuthenticationProvider(self.api_keys, self.roles),
                BearerTokenAuthenticationProvider(self.tokens, self.roles),
                ServiceAuthenticationProvider(role_manager=self.roles),
            ]
            self.auth = AuthenticationCoordinator(
                providers=providers, allow_anonymous=True
            )

        self.authz = authz_engine or AuthorizationEngine(
            permission_manager=self.permissions
        )

    def handle_request(
        self,
        request: GatewayRequest,
        handler: Any | None = None,
        *,
        principal: Principal | None = None,
    ) -> GatewayResponse:
        """Process an inbound request synchronously through the security pipeline."""
        req_id = request.request_id

        # 1. Structural Request Validation
        val_result = self.validator.validate(request)
        if not val_result.valid:
            reason = val_result.reason or "Request validation failed."
            self.audit.record(
                action=request.action,
                result="rejected",
                reason=reason,
                request_id=req_id,
                tenant_id=request.tenant_id,
            )
            self.telemetry.emit(
                EVT_VALIDATION_FAILURE,
                tenant_id=request.tenant_id,
                action=request.action,
                result="rejected",
            )
            return GatewayResponse(
                status="rejected",
                request_id=req_id,
                allowed=False,
                reason=reason,
            )

        # 2. Authentication
        if principal is not None:
            auth_result = AuthenticationResult(
                authenticated=True,
                principal=principal,
                method=principal.authentication_method,
            )
        else:
            has_explicit_creds = bool(
                request.api_key
                or request.bearer_token
                or request.headers.get("x-api-key")
                or request.headers.get("authorization")
                or request.headers.get("x-service-token")
            )
            if not has_explicit_creds and request.metadata.get("internal_call", True):
                # Internal or backward-compatible system execution
                # defaults to system principal
                from aireliability.security.identity import create_system_principal

                derived_principal = create_system_principal().model_copy(
                    update={
                        "tenant_id": request.tenant_id or DEFAULT_TENANT_ID,
                        "project_id": request.project_id or DEFAULT_PROJECT_ID,
                        "namespace": request.namespace or DEFAULT_NAMESPACE,
                    }
                )
                auth_result = AuthenticationResult(
                    authenticated=True,
                    principal=derived_principal,
                    method=AuthenticationMethod.INTERNAL,
                )
            else:
                auth_result = self.auth.authenticate(request)
        if not auth_result.authenticated:
            reason = auth_result.failure_reason or "Authentication failed."
            self.audit.record(
                action=request.action,
                result="rejected",
                reason=reason,
                request_id=req_id,
                tenant_id=request.tenant_id,
            )
            self.telemetry.emit(
                EVT_AUTH_FAILURE,
                tenant_id=request.tenant_id,
                action=request.action,
                result="failure",
            )
            return GatewayResponse(
                status="rejected",
                request_id=req_id,
                allowed=False,
                reason=reason,
            )

        principal = auth_result.principal
        self.telemetry.emit(
            EVT_AUTH_SUCCESS,
            principal_id=principal.principal_id,
            tenant_id=principal.tenant_id,
            action=request.action,
        )

        # 3. Authorization (RBAC + Tenant Isolation)
        decision, authz_reason = self.authz.authorize(
            principal=principal,
            action=request.action,
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            namespace=request.namespace,
            resource=request.resource,
        )
        if decision != AuthorizationDecision.ALLOW:
            reason = authz_reason or "Authorization denied."
            is_boundary = "boundary violation" in reason.lower()
            self.audit.record(
                action=request.action,
                result="denied",
                principal_id=principal.principal_id,
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                namespace=request.namespace,
                resource=request.resource,
                reason=reason,
                request_id=req_id,
            )
            self.telemetry.emit(
                EVT_BOUNDARY_VIOLATION if is_boundary else EVT_AUTHZ_DENIED,
                principal_id=principal.principal_id,
                tenant_id=request.tenant_id,
                action=request.action,
                result="denied",
            )
            return GatewayResponse(
                status="rejected",
                request_id=req_id,
                allowed=False,
                principal=principal,
                reason=reason,
            )

        self.audit.record(
            action=request.action,
            result="allowed",
            principal_id=principal.principal_id,
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            namespace=request.namespace,
            resource=request.resource,
            request_id=req_id,
        )
        self.telemetry.emit(
            EVT_AUTHZ_ALLOWED,
            principal_id=principal.principal_id,
            tenant_id=request.tenant_id,
            action=request.action,
            result="allowed",
        )

        # 4. Security Rate Limiting (by principal or tenant)
        if self.rate_limiter is not None:
            rate_key = f"sec:{principal.tenant_id}:{principal.principal_id}"
            if hasattr(self.rate_limiter, "check_sync"):
                rate_decision = self.rate_limiter.check_sync(rate_key)
            else:
                rate_decision = asyncio.run(self.rate_limiter.check(rate_key))
            if not rate_decision.allowed:
                detail = rate_decision.reason or "capacity exhausted."
                reason = f"Security rate limit exceeded: {detail}"
                self.audit.record(
                    action=request.action,
                    result="rate_limited",
                    principal_id=principal.principal_id,
                    tenant_id=request.tenant_id,
                    reason=reason,
                    request_id=req_id,
                )
                self.telemetry.emit(
                    EVT_RATE_LIMIT_TRIGGERED,
                    principal_id=principal.principal_id,
                    tenant_id=request.tenant_id,
                    action=request.action,
                )
                return GatewayResponse(
                    status="rejected",
                    request_id=req_id,
                    allowed=False,
                    principal=principal,
                    reason=reason,
                )

        # 5. Replay Protection
        req_ts = request.timestamp.timestamp() if request.timestamp else None
        replay_ok, replay_reason = self.replay.check_and_record(
            request_id=req_id,
            nonce=request.nonce,
            request_timestamp=req_ts,
            principal_id=principal.principal_id,
        )
        if not replay_ok:
            reason = replay_reason or "Replay detected."
            self.audit.record(
                action=request.action,
                result="rejected",
                principal_id=principal.principal_id,
                tenant_id=request.tenant_id,
                reason=reason,
                request_id=req_id,
            )
            self.telemetry.emit(
                EVT_REPLAY_DETECTED,
                principal_id=principal.principal_id,
                tenant_id=request.tenant_id,
                action=request.action,
            )
            return GatewayResponse(
                status="rejected",
                request_id=req_id,
                allowed=False,
                principal=principal,
                reason=reason,
            )

        # 6. Execute downstream handler if provided
        data: dict[str, Any] = {}
        if handler is not None:
            try:
                res = handler(request, principal)
                if isinstance(res, dict):
                    data = res
            except Exception as e:
                return GatewayResponse(
                    status="error",
                    request_id=req_id,
                    allowed=True,
                    principal=principal,
                    reason=f"Downstream handler failed: {e}",
                )

        return GatewayResponse(
            status="success",
            request_id=req_id,
            allowed=True,
            principal=principal,
            data=data,
        )

    async def ahandle_request(
        self,
        request: GatewayRequest,
        handler: Any | None = None,
    ) -> GatewayResponse:
        """Asynchronously process an inbound request through the security pipeline."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.handle_request, request, handler)
