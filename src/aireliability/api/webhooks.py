"""Webhook dispatching, HMAC signing, replay defense, and management (Phase 46)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from aireliability.api.models import Webhook, WebhookDelivery


class WebhookManager:
    """Manages outgoing webhooks, HMAC-SHA256 signatures, replay protection, and deliveries."""

    def __init__(self) -> None:
        self._webhooks: dict[str, Webhook] = {}
        self._secrets: dict[str, str] = {}  # In-memory store of raw secrets for signing
        self._seen_signatures: dict[
            str, float
        ] = {}  # Replay prevention cache (signature -> timestamp)
        self._deliveries: list[WebhookDelivery] = []

    def register_webhook(
        self,
        tenant_id: str,
        url: str,
        events: list[str],
        secret: str,
    ) -> Webhook:
        """Register a new webhook subscription. Raw secret is never serialized in the returned model."""
        secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        webhook = Webhook(
            tenant_id=tenant_id,
            url=url,
            events=events,
            secret_hash=secret_hash,
        )
        self._webhooks[webhook.webhook_id] = webhook
        self._secrets[webhook.webhook_id] = secret
        return webhook

    def get_webhook(
        self, webhook_id: str, tenant_id: str | None = None
    ) -> Webhook | None:
        """Retrieve webhook subscription, verifying tenant ownership."""
        wh = self._webhooks.get(webhook_id)
        if not wh:
            return None
        if tenant_id and wh.tenant_id != tenant_id:
            return None
        return wh

    def list_webhooks(self, tenant_id: str | None = None) -> list[Webhook]:
        """List webhook subscriptions, optionally filtered by tenant."""
        webhooks = list(self._webhooks.values())
        if tenant_id:
            webhooks = [wh for wh in webhooks if wh.tenant_id == tenant_id]
        return webhooks

    def sign_payload(self, secret: str, payload_bytes: bytes) -> str:
        """Compute HMAC-SHA256 signature for webhook payload."""
        return hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()

    def verify_signature(
        self, secret: str, payload_bytes: bytes, signature: str
    ) -> bool:
        """Verify HMAC-SHA256 signature against payload using constant-time comparison."""
        expected = self.sign_payload(secret, payload_bytes)
        return hmac.compare_digest(expected, signature)

    def sign_payload_with_timestamp(
        self, secret: str, payload_bytes: bytes, timestamp: float | None = None
    ) -> tuple[str, float]:
        """Compute HMAC-SHA256 signature binding timestamp and payload."""
        ts = timestamp if timestamp is not None else time.time()
        ts_bytes = f"{ts:.0f}.".encode()
        signed_bytes = ts_bytes + payload_bytes
        sig = hmac.new(secret.encode("utf-8"), signed_bytes, hashlib.sha256).hexdigest()
        return sig, ts

    def verify_signature_with_timestamp(
        self,
        secret: str,
        payload_bytes: bytes,
        signature: str,
        timestamp: float,
        max_age_seconds: float = 300.0,
    ) -> bool:
        """Verify signature with timestamp freshness and replay prevention."""
        now = time.time()
        # 1. Freshness check: reject if too old or too far in the future
        if abs(now - timestamp) > max_age_seconds:
            return False

        # 2. Replay check: reject if signature was already seen
        self._purge_stale_replay_cache(now, max_age_seconds)
        if signature in self._seen_signatures:
            return False

        # 3. Signature verification
        expected, _ = self.sign_payload_with_timestamp(secret, payload_bytes, timestamp)
        if not hmac.compare_digest(expected, signature):
            return False

        # 4. Record signature in replay cache
        self._seen_signatures[signature] = now
        return True

    def _purge_stale_replay_cache(self, now: float, max_age_seconds: float) -> None:
        """Purge entries older than max_age_seconds from replay cache."""
        cutoff = now - max_age_seconds
        stale = [sig for sig, ts in self._seen_signatures.items() if ts < cutoff]
        for sig in stale:
            self._seen_signatures.pop(sig, None)

    def dispatch_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Simulate event dispatch to subscribed endpoints."""
        deliveries: list[dict[str, Any]] = []
        payload_bytes = json.dumps(payload, default=str).encode("utf-8")

        for wh in self._webhooks.values():
            if not wh.enabled:
                continue
            if tenant_id and wh.tenant_id != tenant_id:
                continue
            if "*" in wh.events or event_type in wh.events:
                secret = self._secrets.get(wh.webhook_id, "default_secret")
                now_ts = time.time()
                sig = self.sign_payload_with_timestamp(secret, payload_bytes, now_ts)
                deliveries.append(
                    {
                        "webhook_id": wh.webhook_id,
                        "url": wh.url,
                        "event": event_type,
                        "signature": sig,
                        "timestamp": now_ts,
                        "delivered": True,
                    }
                )
        return deliveries
