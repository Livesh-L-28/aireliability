"""Authentication providers and secure API key management (Phase 46)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from aireliability.api.models import APIKeyInfo
from aireliability.tenancy.models import TenantContext, TenantRole


def _hash_secret(secret: str) -> str:
    """Secure SHA-256 hash of API secret key."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class KeyStatus(StrEnum):
    """Lifecycle status of an inspected API credential."""

    VALID = "VALID"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class APIKeyRecord:
    """Internal storage record for an API key with hashed secret."""

    def __init__(
        self,
        key_id: str,
        name: str,
        secret_hash: str,
        tenant_id: str,
        scopes: list[str],
        created_at: datetime,
        expires_at: datetime | None = None,
        revoked: bool = False,
    ) -> None:
        self.key_id = key_id
        self.name = name
        self.secret_hash = secret_hash
        self.tenant_id = tenant_id
        self.scopes = scopes
        self.created_at = created_at
        self.expires_at = expires_at
        self.revoked = revoked

    def to_info(self) -> APIKeyInfo:
        return APIKeyInfo(
            key_id=self.key_id,
            name=self.name,
            tenant_id=self.tenant_id,
            scopes=self.scopes,
            created_at=self.created_at,
            expires_at=self.expires_at,
            revoked=self.revoked,
        )


class APIKeyManager:
    """Manages generation, secure hashing, rotation, and revocation of API keys."""

    def __init__(self) -> None:
        self._keys: dict[str, APIKeyRecord] = {}

    def create_key(
        self,
        tenant_id: str,
        name: str,
        scopes: list[str] | None = None,
        expires_in_days: int | None = 90,
    ) -> tuple[APIKeyInfo, str]:
        """Generate a new API key. The plaintext secret is returned ONLY once."""
        key_id = f"key_{uuid4().hex[:12]}"
        raw_secret = f"airel_{secrets.token_urlsafe(32)}"
        secret_hash = _hash_secret(raw_secret)

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=expires_in_days) if expires_in_days else None

        record = APIKeyRecord(
            key_id=key_id,
            name=name,
            secret_hash=secret_hash,
            tenant_id=tenant_id,
            scopes=list(scopes or ["*"]),
            created_at=now,
            expires_at=expires_at,
        )
        self._keys[key_id] = record
        return record.to_info(), raw_secret

    def check_key_status(self, raw_secret: str) -> tuple[KeyStatus, APIKeyInfo | None]:
        """Inspect the status of an API key using timing-safe comparison."""
        if not raw_secret or not raw_secret.startswith("airel_"):
            return KeyStatus.INVALID, None

        hashed = _hash_secret(raw_secret)
        now = datetime.now(UTC)

        for record in self._keys.values():
            if hmac.compare_digest(record.secret_hash, hashed):
                if record.revoked:
                    return KeyStatus.REVOKED, record.to_info()
                if record.expires_at and record.expires_at < now:
                    return KeyStatus.EXPIRED, record.to_info()
                return KeyStatus.VALID, record.to_info()

        return KeyStatus.INVALID, None

    def verify_key(self, raw_secret: str) -> APIKeyInfo | None:
        """Verify a plaintext key against hashed storage."""
        status, info = self.check_key_status(raw_secret)
        return info if status == KeyStatus.VALID else None

    def rotate_key(self, key_id: str) -> tuple[APIKeyInfo, str]:
        """Revoke old key and issue new secret under same tenant and scopes."""
        record = self._keys.get(key_id)
        if not record:
            raise KeyError(f"Key '{key_id}' not found")
        record.revoked = True
        return self.create_key(
            tenant_id=record.tenant_id,
            name=f"{record.name} (Rotated)",
            scopes=record.scopes,
        )

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an existing API key immediately."""
        record = self._keys.get(key_id)
        if record:
            record.revoked = True
            return True
        return False

    def list_keys_for_tenant(self, tenant_id: str) -> list[APIKeyInfo]:
        """List active and revoked key metadata for a specific tenant."""
        return [
            rec.to_info() for rec in self._keys.values() if rec.tenant_id == tenant_id
        ]


class AuthProvider(ABC):
    """Abstract authentication provider."""

    @abstractmethod
    def authenticate(self, credentials: Any) -> TenantContext | None: ...


class APIKeyProvider(AuthProvider):
    """Authenticates API requests via API key manager."""

    def __init__(self, key_manager: APIKeyManager) -> None:
        self.key_manager = key_manager

    def authenticate(self, credentials: Any) -> TenantContext | None:
        info = self.key_manager.verify_key(str(credentials))
        if info:
            roles = [TenantRole.ENGINEER]
            if "owner" in info.scopes or "*" in info.scopes:
                roles = [TenantRole.OWNER]
            elif "admin" in info.scopes:
                roles = [TenantRole.ADMIN]
            elif "analyst" in info.scopes:
                roles = [TenantRole.ANALYST]
            elif "viewer" in info.scopes:
                roles = [TenantRole.VIEWER]
            elif "auditor" in info.scopes:
                roles = [TenantRole.AUDITOR]
            elif "service_account" in info.scopes:
                roles = [TenantRole.SERVICE_ACCOUNT]
            return TenantContext(
                organization_id="org_enterprise",
                tenant_id=info.tenant_id,
                actor_id=info.key_id,
                roles=roles,
                metadata={"scopes": info.scopes},
            )
        return None


class BearerTokenProvider(AuthProvider):
    """Authenticates Bearer tokens."""

    def authenticate(self, credentials: Any) -> TenantContext | None:
        token = str(credentials).strip()
        if not token.startswith("bearer_token_") and not token.startswith(
            "bearer_token:"
        ):
            return None

        prefix = (
            "bearer_token:" if token.startswith("bearer_token:") else "bearer_token_"
        )
        remainder = token[len(prefix) :]
        if not remainder:
            return None

        role_map = {
            "owner": TenantRole.OWNER,
            "admin": TenantRole.ADMIN,
            "engineer": TenantRole.ENGINEER,
            "analyst": TenantRole.ANALYST,
            "viewer": TenantRole.VIEWER,
            "auditor": TenantRole.AUDITOR,
            "service_account": TenantRole.SERVICE_ACCOUNT,
        }

        if ":" in remainder:
            parts = remainder.split(":")
            tenant = parts[0]
            actor = parts[1] if len(parts) > 1 else "bearer_user"
            role = (
                role_map.get(parts[2].lower(), TenantRole.ENGINEER)
                if len(parts) > 2
                else TenantRole.ENGINEER
            )
        else:
            parts = remainder.split("_")
            if len(parts) >= 3 and parts[-1].lower() in role_map:
                role = role_map[parts[-1].lower()]
                actor = parts[-2]
                tenant = "_".join(parts[:-2])
            elif len(parts) >= 2:
                tenant = parts[0]
                actor = "_".join(parts[1:])
                role = TenantRole.ENGINEER
            else:
                tenant = parts[0]
                actor = "bearer_user"
                role = TenantRole.ENGINEER

        if not tenant:
            return None

        return TenantContext(
            organization_id="org_enterprise",
            tenant_id=tenant,
            actor_id=actor,
            roles=[role],
        )


class ServiceAccountProvider(AuthProvider):
    """Authenticates internal service accounts."""

    def authenticate(self, credentials: Any) -> TenantContext | None:
        cred_str = str(credentials).strip()
        if not cred_str.startswith("sa_") and not cred_str.startswith("sa:"):
            return None

        prefix = "sa:" if cred_str.startswith("sa:") else "sa_"
        remainder = cred_str[len(prefix) :]
        if not remainder:
            return None

        role_map = {
            "owner": TenantRole.OWNER,
            "admin": TenantRole.ADMIN,
            "engineer": TenantRole.ENGINEER,
            "analyst": TenantRole.ANALYST,
            "viewer": TenantRole.VIEWER,
            "auditor": TenantRole.AUDITOR,
            "service_account": TenantRole.SERVICE_ACCOUNT,
        }

        if ":" in remainder:
            parts = remainder.split(":")
            _ = parts[0]
            tenant_id = parts[1] if len(parts) > 1 else "default"
            role = (
                role_map.get(parts[2].lower(), TenantRole.SERVICE_ACCOUNT)
                if len(parts) > 2
                else TenantRole.SERVICE_ACCOUNT
            )
        else:
            parts = remainder.split("_")
            if len(parts) >= 3 and parts[-1].lower() in role_map:
                role = role_map[parts[-1].lower()]
                tenant_id = "_".join(parts[1:-1])
            elif len(parts) >= 2:
                tenant_id = parts[1]
                role = TenantRole.SERVICE_ACCOUNT
            else:
                tenant_id = "default"
                role = TenantRole.SERVICE_ACCOUNT

        return TenantContext(
            organization_id="org_enterprise",
            tenant_id=tenant_id,
            actor_id=cred_str,
            roles=[role],
        )


class AuthenticationCoordinator:
    """Coordinates multi-method authentication across API keys, Bearer tokens, and service accounts."""

    def __init__(self, key_manager: APIKeyManager) -> None:
        self.key_manager = key_manager
        self.key_provider = APIKeyProvider(key_manager)
        self.bearer_provider = BearerTokenProvider()
        self.sa_provider = ServiceAccountProvider()

    def authenticate_credential(
        self,
        api_key: str | None = None,
        bearer_token: str | None = None,
        service_account: str | None = None,
    ) -> tuple[TenantContext | None, str | None]:
        """Authenticate request credentials, returning (context, rejection_reason)."""
        if api_key:
            status, info = self.key_manager.check_key_status(api_key)
            if status == KeyStatus.VALID:
                ctx = self.key_provider.authenticate(api_key)
                return ctx, None
            elif status == KeyStatus.EXPIRED:
                return None, "API key has expired."
            elif status == KeyStatus.REVOKED:
                return None, "API key has been revoked."
            else:
                return None, "Invalid API key credentials."

        if bearer_token:
            ctx = self.bearer_provider.authenticate(bearer_token)
            if ctx:
                return ctx, None
            return None, "Invalid or malformed Bearer authentication token."

        if service_account:
            ctx = self.sa_provider.authenticate(service_account)
            if ctx:
                return ctx, None
            return None, "Invalid service account credentials."

        return None, "Authentication credentials were not provided."
