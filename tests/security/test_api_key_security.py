"""API key lifecycle, rotation, revocation, and scope enforcement tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from aireliability.api.app import create_app
from aireliability.api.auth import APIKeyManager, KeyStatus


def test_plaintext_secret_never_persisted_in_models():
    """Verify that APIKey / APIKeyInfo models never store plaintext secret."""
    mgr = APIKeyManager()
    info, secret = mgr.create_key(tenant_id="tenant_p1", name="Security Key")

    assert not hasattr(info, "secret")
    assert not hasattr(info, "raw_secret")
    dumped = info.model_dump()
    assert "secret" not in dumped
    assert secret not in str(dumped)


def test_rotation_invalidates_previous_credential():
    """Verify key rotation revokes previous secret and issues valid replacement."""
    mgr = APIKeyManager()
    info1, secret1 = mgr.create_key(tenant_id="tenant_rot", name="Key 1")

    # Initial secret is valid
    assert mgr.verify_key(secret1) is not None

    # Rotate
    info2, secret2 = mgr.rotate_key(info1.key_id)
    assert secret2 != secret1

    # Old secret is immediately revoked
    assert mgr.verify_key(secret1) is None
    status1, _ = mgr.check_key_status(secret1)
    assert status1 == KeyStatus.REVOKED

    # New secret is valid
    assert mgr.verify_key(secret2) is not None
    status2, _ = mgr.check_key_status(secret2)
    assert status2 == KeyStatus.VALID


def test_revocation_works():
    """Verify key revocation immediately disables access."""
    mgr = APIKeyManager()
    info, secret = mgr.create_key(tenant_id="tenant_rev", name="Revoke Test")

    assert mgr.verify_key(secret) is not None
    assert mgr.revoke_key(info.key_id) is True
    assert mgr.verify_key(secret) is None

    # Redundant revocation returns False
    assert mgr.revoke_key("nonexistent_key_id") is False


def test_expiration_works():
    """Verify expiration timestamp check correctly invalidates key."""
    mgr = APIKeyManager()
    info, secret = mgr.create_key(
        tenant_id="tenant_exp", name="Expiring Test", expires_in_days=30
    )

    # Manually expire
    rec = mgr._keys[info.key_id]
    rec.expires_at = datetime.now(UTC) - timedelta(seconds=10)

    status, inspected = mgr.check_key_status(secret)
    assert status == KeyStatus.EXPIRED
    assert mgr.verify_key(secret) is None


def test_tenant_binding_and_scoped_listing():
    """Verify API keys are strictly bound to creating tenant."""
    mgr = APIKeyManager()
    info_a, secret_a = mgr.create_key(tenant_id="tenant_A", name="Key A")
    info_b, secret_b = mgr.create_key(tenant_id="tenant_B", name="Key B")

    assert info_a.tenant_id == "tenant_A"
    assert info_b.tenant_id == "tenant_B"

    keys_a = mgr.list_keys_for_tenant("tenant_A")
    keys_b = mgr.list_keys_for_tenant("tenant_B")

    assert len(keys_a) == 1
    assert keys_a[0].key_id == info_a.key_id
    assert len(keys_b) == 1
    assert keys_b[0].key_id == info_b.key_id


def test_wrong_tenant_key_access():
    """Verify that an API key belonging to Tenant A cannot access Tenant B resources."""
    app = create_app()
    key_mgr = app.state.key_manager
    _, secret_a = key_mgr.create_key(tenant_id="tenant_alpha", name="Key Alpha")
    _, secret_b = key_mgr.create_key(tenant_id="tenant_beta", name="Key Beta")

    client = TestClient(app)

    # Tenant A creates an evaluation
    resp_create = client.post(
        "/api/v1/evaluations",
        headers={"X-API-Key": secret_a},
        json={"input_text": "input_a", "output_text": "output_a"},
    )
    assert resp_create.status_code == 200
    eval_id = resp_create.json()["evaluation_id"]

    # Tenant B attempts to read Tenant A's evaluation
    resp_cross = client.get(
        f"/api/v1/evaluations/{eval_id}",
        headers={"X-API-Key": secret_b},
    )
    assert resp_cross.status_code == 403
    assert "Cross-tenant access forbidden" in resp_cross.json()["detail"]


def test_scopes_enforcement():
    """Verify that API keys with restricted scopes cannot execute unauthorized actions."""
    app = create_app()
    key_mgr = app.state.key_manager

    # Key with 'viewer' scope only (cannot write or create evaluations)
    _, viewer_secret = key_mgr.create_key(
        tenant_id="tenant_viewer",
        name="Viewer Key",
        scopes=["viewer"],
    )

    client = TestClient(app)

    # Viewer attempts mutation
    resp_eval = client.post(
        "/api/v1/evaluations",
        headers={"X-API-Key": viewer_secret},
        json={"input_text": "hello", "output_text": "world"},
    )
    assert resp_eval.status_code == 403
    assert "Forbidden" in resp_eval.json()["detail"]
