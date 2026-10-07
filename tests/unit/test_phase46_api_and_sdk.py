"""Unit and SDK integration tests for Phase 46 Reliability API and SDK Platform."""

from __future__ import annotations

import pytest

from aireliability.api.app import api_app
from aireliability.api.auth import APIKeyManager
from aireliability.api.webhooks import WebhookManager
from aireliability.sdk.client import Client, NotFoundError


def test_api_health_endpoint():
    with Client(app=api_app) as client:
        health = client.health()
        assert health["status"] == "healthy"
        assert health["version"] == "1.4.0"


def test_openapi_schema_generation():
    schema = api_app.openapi()
    assert schema["info"]["title"] == "AI Reliability Platform API"
    assert schema["info"]["version"] == "1.4.0"
    assert "/health" in schema["paths"]
    assert "/api/v1/evaluations" in schema["paths"]
    assert "/api/v1/safety/evaluate" in schema["paths"]
    assert "/api/v1/predictions" in schema["paths"]
    assert "/api/v1/dashboard" in schema["paths"]


def test_api_key_manager_lifecycle():
    mgr = APIKeyManager()
    info, secret = mgr.create_key(tenant_id="tenant_x", name="Test Key")
    assert secret.startswith("airel_")
    assert info.tenant_id == "tenant_x"

    # Verify secret
    verified = mgr.verify_key(secret)
    assert verified is not None
    assert verified.key_id == info.key_id

    # Revoke key
    assert mgr.revoke_key(info.key_id) is True
    assert mgr.verify_key(secret) is None


def test_webhook_hmac_signing_and_verification():
    wh_mgr = WebhookManager()
    secret = "my_webhook_secret_key"
    payload = b'{"event": "evaluation.completed", "status": "passed"}'

    sig = wh_mgr.sign_payload(secret, payload)
    assert isinstance(sig, str) and len(sig) == 64  # SHA-256 hex
    assert wh_mgr.verify_signature(secret, payload, sig) is True
    assert wh_mgr.verify_signature("wrong_secret", payload, sig) is False


def test_sdk_synchronous_evaluations_and_datasets():
    with Client(app=api_app) as client:
        # Create evaluation
        res = client.evaluations.create(input_text="hello", output_text="world")
        assert res["passed"] is True
        assert res["score"] == 0.95

        # Get evaluation
        fetched = client.evaluations.get(res["evaluation_id"])
        assert fetched["evaluation_id"] == res["evaluation_id"]

        # Datasets
        ds = client.datasets.create(
            name="Golden Set", items=[{"input": "a", "output": "b"}]
        )
        assert ds["name"] == "Golden Set"
        assert ds["item_count"] == 1


def test_sdk_error_handling_not_found():
    with Client(app=api_app) as client, pytest.raises(NotFoundError):
        client.evaluations.get("nonexistent_id_404")


@pytest.mark.asyncio
async def test_sdk_async_client():
    from aireliability.sdk.async_client import AsyncClient

    async with AsyncClient(app=api_app) as async_client:
        h = await async_client.health()
        assert h["status"] == "healthy"
        res = await async_client.evaluations.create(
            input_text="async test", output_text="response"
        )
        assert res["passed"] is True
