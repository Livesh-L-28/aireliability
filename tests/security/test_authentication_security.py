"""Authentication security tests for aireliability v1.4.0.

Verifies rejection of:
- missing credentials
- invalid API keys
- expired API keys
- revoked API keys
- malformed bearer tokens
- invalid service accounts
And verifies failure responses expose no internal secrets or traces.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from aireliability.api.app import api_app, create_app


def test_missing_credentials_rejected():
    """Verify requests lacking any authentication credentials return HTTP 401."""
    client = TestClient(api_app)
    response = client.get("/api/v1/evaluations/eval_123")
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Authentication credentials were not provided" in data["detail"]
    assert "Traceback" not in response.text
    assert "password" not in response.text.lower()
    assert "secret" not in response.text.lower()


def test_invalid_api_key_rejected():
    """Verify non-existent or fabricated API keys return HTTP 401."""
    client = TestClient(api_app)
    response = client.get(
        "/api/v1/evaluations/eval_123",
        headers={"X-API-Key": "airel_invalid_secret_key_1234567890"},
    )
    assert response.status_code == 401
    assert "Invalid API key credentials" in response.json()["detail"]


def test_expired_api_key_rejected():
    """Verify expired API keys are rejected with clear machine-readable status."""
    app = create_app()
    key_mgr = app.state.key_manager
    info, secret = key_mgr.create_key(tenant_id="tenant_exp", name="Expiring Key")

    # Manually expire the key
    record = key_mgr._keys[info.key_id]
    record.expires_at = datetime.now(UTC) - timedelta(days=1)

    client = TestClient(app)
    response = client.get(
        "/api/v1/evaluations/eval_test",
        headers={"X-API-Key": secret},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_revoked_api_key_rejected():
    """Verify revoked API keys are immediately rejected."""
    app = create_app()
    key_mgr = app.state.key_manager
    info, secret = key_mgr.create_key(tenant_id="tenant_rev", name="Revoking Key")

    assert key_mgr.revoke_key(info.key_id) is True

    client = TestClient(app)
    response = client.get(
        "/api/v1/evaluations/eval_test",
        headers={"X-API-Key": secret},
    )
    assert response.status_code == 401
    assert "revoked" in response.json()["detail"].lower()


def test_malformed_bearer_token_rejected():
    """Verify malformed Bearer tokens are rejected."""
    client = TestClient(api_app)

    # Malformed tokens
    for bad_token in [
        "Bearer",
        "Bearer ",
        "Bearer invalid_garbage_token",
        "Bearer not_a_real_bearer",
    ]:
        response = client.get(
            "/api/v1/evaluations/eval_test",
            headers={"Authorization": bad_token},
        )
        assert any(
            w in response.json()["detail"].lower()
            for w in ("malformed", "invalid", "not provided")
        )


def test_invalid_service_account_rejected():
    """Verify invalid service accounts are rejected."""
    client = TestClient(api_app)
    response = client.get(
        "/api/v1/evaluations/eval_test",
        headers={"X-Service-Account": "invalid_sa_format"},
    )
    assert response.status_code == 401
    assert "Invalid service account credentials" in response.json()["detail"]


def test_valid_authentication_methods_accepted():
    """Verify valid API key, Bearer token, and Service Account succeed."""
    app = create_app()
    key_mgr = app.state.key_manager
    info, secret = key_mgr.create_key(tenant_id="tenant_auth", name="Valid Key")

    client = TestClient(app)

    # 1. Valid API Key
    resp1 = client.get("/api/v1/datasets", headers={"X-API-Key": secret})
    assert resp1.status_code == 200

    # 2. Valid Bearer Token
    resp2 = client.get(
        "/api/v1/datasets",
        headers={"Authorization": "Bearer bearer_token_tenant_auth_user1_owner"},
    )
    assert resp2.status_code == 200

    # 3. Valid Service Account
    resp3 = client.get(
        "/api/v1/datasets",
        headers={"X-Service-Account": "sa_agent1_tenant_auth_owner"},
    )
    assert resp3.status_code == 200


def test_authentication_error_data_protection():
    """Verify failure responses expose no secrets, stack traces, credentials, or tenant info."""
    client = TestClient(api_app)
    response = client.post(
        "/api/v1/evaluations",
        headers={"X-API-Key": "airel_forbidden_probe_attempt"},
        json={"input_text": "probe", "output_text": "attempt"},
    )
    assert response.status_code == 401
    body = response.text
    assert 'File "' not in body
    assert "Traceback" not in body
    assert "airel_forbidden_probe_attempt" not in body
    assert "sqlite" not in body.lower()
    assert "postgres" not in body.lower()
