"""API Key management with secure salted SHA-256 hashing and lifecycle controls."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aireliability.security.errors import (
    ExpiredCredentialError,
    InvalidAPIKeyError,
)
from aireliability.security.models import _utc_now
from aireliability.tenancy.models import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT_ID,
    DEFAULT_TENANT_ID,
)


class APIKey(BaseModel):
    """Metadata record of an API key. Raw key is never stored."""

    model_config = ConfigDict(frozen=True)

    key_id: str
    key_prefix: str  # First 8 chars for recognition, e.g. "airel_ab12"
    hashed_secret: str
    salt: str
    tenant_id: str = DEFAULT_TENANT_ID
    project_id: str = DEFAULT_PROJECT_ID
    namespace: str = DEFAULT_NAMESPACE
    name: str = "API Key"
    roles: list[str] = Field(default_factory=lambda: ["DEVELOPER"])
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime | None = None
    revoked: bool = False
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        if self.revoked:
            return False
        return not bool(self.expires_at and self.expires_at < datetime.now(UTC))


class APIKeyCreationResult(BaseModel):
    """Result returned on key creation containing the raw secret once."""

    model_config = ConfigDict(frozen=True)

    key: APIKey
    raw_key: str  # Only returned at creation time


class APIKeyManager:
    """Manages API key generation, secure storage, rotation, and verification."""

    def __init__(self, storage: Any | None = None) -> None:
        self.storage = storage
        self._memory_keys: dict[str, APIKey] = {}

    @staticmethod
    def _hash_key(raw_secret: str, salt: str) -> str:
        """Hash key using HMAC-SHA256 with a unique cryptographic salt."""
        return hmac.new(
            salt.encode("utf-8"),
            raw_secret.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def create_key(
        self,
        tenant_id: str = DEFAULT_TENANT_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        namespace: str = DEFAULT_NAMESPACE,
        name: str = "API Key",
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> APIKeyCreationResult:
        """Create a new API key. Raw key is returned once."""
        key_id = f"key_{uuid4().hex[:16]}"
        salt = secrets.token_hex(16)
        secret_part = secrets.token_urlsafe(32)
        raw_key = f"airel_{secret_part}"
        key_prefix = raw_key[:12]
        hashed_secret = self._hash_key(raw_key, salt)

        key = APIKey(
            key_id=key_id,
            key_prefix=key_prefix,
            hashed_secret=hashed_secret,
            salt=salt,
            tenant_id=tenant_id,
            project_id=project_id,
            namespace=namespace,
            name=name,
            roles=roles or ["DEVELOPER"],
            permissions=permissions or [],
            created_at=_utc_now(),
            expires_at=expires_at,
            metadata=metadata or {},
        )

        self._save_key(key)
        return APIKeyCreationResult(key=key, raw_key=raw_key)

    def _save_key(self, key: APIKey) -> None:
        self._memory_keys[key.key_id] = key
        if self.storage and hasattr(self.storage, "save_api_key"):
            self.storage.save_api_key(key)

    def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve key metadata by key_id."""
        if self.storage and hasattr(self.storage, "get_api_key"):
            stored = self.storage.get_api_key(key_id)
            if stored:
                return stored
        return self._memory_keys.get(key_id)

    def list_keys(self, tenant_id: str | None = None) -> list[APIKey]:
        """List keys, optionally filtered by tenant."""
        if self.storage and hasattr(self.storage, "list_api_keys"):
            return self.storage.list_api_keys(tenant_id=tenant_id)
        keys = list(self._memory_keys.values())
        if tenant_id:
            keys = [k for k in keys if k.tenant_id == tenant_id]
        return keys

    def verify_key(self, raw_key: str) -> APIKey:
        """Verify raw key against stored records. Returns APIKey on success.

        Raises:
            InvalidAPIKeyError: If key not found or hash mismatch.
            ExpiredCredentialError: If key expired or revoked.
        """
        if not raw_key.startswith("airel_"):
            raise InvalidAPIKeyError("Invalid API key format.")

        candidate: APIKey | None = None
        for k in self.list_keys():
            expected_hash = self._hash_key(raw_key, k.salt)
            if hmac.compare_digest(k.hashed_secret, expected_hash):
                candidate = k
                break

        if candidate is None:
            raise InvalidAPIKeyError("API key not recognized or invalid.")

        if candidate.revoked:
            raise ExpiredCredentialError("API key has been revoked.")

        if candidate.expires_at and candidate.expires_at < datetime.now(UTC):
            raise ExpiredCredentialError("API key has expired.")

        # Update last_used_at
        updated = candidate.model_copy(update={"last_used_at": _utc_now()})
        self._save_key(updated)
        return updated

    def revoke_key(self, key_id: str) -> APIKey:
        """Revoke an active API key."""
        key = self.get_key(key_id)
        if not key:
            raise InvalidAPIKeyError(f"API key '{key_id}' not found.")
        revoked = key.model_copy(update={"revoked": True, "revoked_at": _utc_now()})
        self._save_key(revoked)
        return revoked

    def rotate_key(
        self, key_id: str, expires_in_seconds: float | None = None
    ) -> APIKeyCreationResult:
        """Revoke existing key and issue a new one with identical privileges."""
        old_key = self.revoke_key(key_id)
        expires_at = (
            datetime.now(UTC) + datetime.timedelta(seconds=expires_in_seconds)
            if expires_in_seconds
            else old_key.expires_at
        )
        return self.create_key(
            tenant_id=old_key.tenant_id,
            project_id=old_key.project_id,
            namespace=old_key.namespace,
            name=f"{old_key.name} (Rotated)",
            roles=old_key.roles,
            permissions=old_key.permissions,
            expires_at=expires_at,
            metadata=old_key.metadata,
        )
