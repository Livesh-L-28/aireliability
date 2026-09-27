"""Provider-neutral token claims and validator abstractions for Phase 28."""

import base64
import json
import time
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)


class TokenClaims(BaseModel):
    """Standard token claims model (JWT/OIDC compatible)."""

    model_config = ConfigDict(frozen=True)

    sub: str  # Subject / Principal ID
    iss: str = "aireliability-gateway"  # Issuer
    aud: str = "aireliability-api"  # Audience
    exp: float  # Expiration epoch seconds
    nbf: float = 0.0  # Not-before epoch seconds
    iat: float = Field(default_factory=time.time)  # Issued-at epoch seconds
    tenant_id: str = DEFAULT_TENANT_ID
    project_id: str = DEFAULT_PROJECT_ID
    namespace: str = DEFAULT_NAMESPACE
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    claims: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.exp


class TokenValidationResult(BaseModel):
    """Result of token validation."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    claims: TokenClaims | None = None
    reason: str | None = None


@runtime_checkable
class TokenValidator(Protocol):
    """Protocol for validating bearer tokens."""

    def validate_token(self, token: str) -> TokenValidationResult:
        """Validate bearer token string and return decoded claims."""
        ...


class SimpleSignedTokenValidator:
    """Provider-neutral reference token encoder and validator.

    Format: base64(header).base64(claims).signature
    Allows local testing, CI, and decoupled auth without external IdPs or pyjwt.
    """

    def __init__(self, secret: str = "insecure-dev-secret") -> None:
        self.secret = secret

    def create_token(
        self,
        sub: str,
        expires_in_seconds: float = 3600.0,
        tenant_id: str = DEFAULT_TENANT_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        namespace: str = DEFAULT_NAMESPACE,
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
        issuer: str = "aireliability-gateway",
        audience: str = "aireliability-api",
    ) -> str:
        """Generate a signed bearer token string."""
        now = time.time()
        claims = TokenClaims(
            sub=sub,
            iss=issuer,
            aud=audience,
            exp=now + expires_in_seconds,
            nbf=now - 5.0,
            iat=now,
            tenant_id=tenant_id,
            project_id=project_id,
            namespace=namespace,
            roles=roles or [],
            permissions=permissions or [],
        )
        claims_json = claims.model_dump_json()
        b64_claims = base64.urlsafe_b64encode(claims_json.encode("utf-8")).decode(
            "utf-8"
        )
        import hashlib
        import hmac

        sig = hmac.new(
            self.secret.encode("utf-8"),
            b64_claims.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"bear_{b64_claims}.{sig}"

    def validate_token(self, token: str) -> TokenValidationResult:
        """Validate signed bearer token and verify claims."""
        if not token.startswith("bear_") or "." not in token:
            return TokenValidationResult(valid=False, reason="Malformed token format.")

        token_body = token[5:]
        parts = token_body.split(".", 1)
        if len(parts) != 2:
            return TokenValidationResult(valid=False, reason="Invalid token structure.")

        b64_claims, signature = parts
        import hashlib
        import hmac

        expected_sig = hmac.new(
            self.secret.encode("utf-8"),
            b64_claims.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return TokenValidationResult(
                valid=False, reason="Token signature verification failed."
            )

        try:
            raw_claims = base64.urlsafe_b64decode(b64_claims.encode("utf-8")).decode(
                "utf-8"
            )
            data = json.loads(raw_claims)
            claims = TokenClaims(**data)
        except Exception as e:
            return TokenValidationResult(
                valid=False, reason=f"Failed to parse token claims: {e}"
            )

        now = time.time()
        if now < claims.nbf:
            return TokenValidationResult(
                valid=False, reason="Token not valid yet (nbf claim)."
            )
        if now >= claims.exp:
            return TokenValidationResult(valid=False, reason="Token has expired.")

        return TokenValidationResult(valid=True, claims=claims)
