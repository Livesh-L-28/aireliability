"""API hardening tests covering input validation, error leakage, rate limiting,
idempotency, webhook signatures, and job security.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from aireliability.api.app import create_app
from aireliability.api.jobs import JobManager
from aireliability.api.models import JobStatus
from aireliability.api.webhooks import WebhookManager
from aireliability.tenancy.models import RateLimitAlgorithm, RateLimitPolicy


def test_malformed_input_validation():
    """Verify malformed JSON and schema mismatches return structured 422 validation errors."""
    app = create_app()
    client = TestClient(app)
    auth_header = {"Authorization": "Bearer bearer_token_tenant1_user1_owner"}

    # 1. Missing required field 'input_text'
    res_missing = client.post(
        "/api/v1/evaluations",
        headers=auth_header,
        json={"output_text": "only output"},
    )
    assert res_missing.status_code == 422
    assert "detail" in res_missing.json()

    # 2. Invalid data type for items (expected list, passed integer)
    res_invalid_type = client.post(
        "/api/v1/datasets",
        headers=auth_header,
        json={"name": "Dataset A", "items": 12345},
    )
    assert res_invalid_type.status_code == 422


def test_error_handling_stack_trace_leakage_prevention():
    """Verify exceptions never leak Python stack traces, file paths, or credentials."""
    app = create_app()
    client = TestClient(app)

    # Intentionally trigger not found
    res = client.get(
        "/api/v1/evaluations/non_existent_id",
        headers={"Authorization": "Bearer bearer_token_tenant1_user1_owner"},
    )
    assert res.status_code == 404
    assert "Traceback" not in res.text
    assert "/Users/" not in res.text
    assert ".py" not in res.text


def test_api_rate_limiting():
    """Verify rate limits enforce quotas and return machine-readable HTTP 429."""
    app = create_app()
    rate_limiter = app.state.rate_limiter
    # Configure tight limit: 2 requests per 60 seconds for tenant 'tenant_rl'
    rate_limiter.set_policy(
        "tenant:tenant_rl",
        RateLimitPolicy(
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            rate=2.0,
            window_seconds=60.0,
        ),
    )

    client = TestClient(app)
    auth_header = {"Authorization": "Bearer bearer_token_tenant_rl_user1_owner"}

    # Request 1: OK
    r1 = client.post(
        "/api/v1/evaluations",
        headers=auth_header,
        json={"input_text": "a", "output_text": "b"},
    )
    assert r1.status_code == 200

    # Request 2: OK
    r2 = client.post(
        "/api/v1/evaluations",
        headers=auth_header,
        json={"input_text": "a", "output_text": "b"},
    )
    assert r2.status_code == 200

    # Request 3: Exceeded -> HTTP 429
    r3 = client.post(
        "/api/v1/evaluations",
        headers=auth_header,
        json={"input_text": "a", "output_text": "b"},
    )
    assert r3.status_code == 429
    detail = r3.json()["detail"]
    assert detail["error"] == "rate_limit_exceeded"
    assert "Retry-After" in r3.headers


def test_idempotency_caching_and_conflict_rejection():
    """Verify Idempotency-Key prevents duplicate execution and rejects modified payloads."""
    app = create_app()
    client = TestClient(app)
    auth_header = {
        "Authorization": "Bearer bearer_token_tenant_idem_user1_owner",
        "Idempotency-Key": "idem_eval_001",
    }

    payload1 = {"input_text": "question 1", "output_text": "answer 1"}
    r1 = client.post("/api/v1/evaluations", headers=auth_header, json=payload1)
    assert r1.status_code == 200
    eval_id_first = r1.json()["evaluation_id"]

    # Re-send same payload with same idempotency key -> returns original evaluation safely
    r2 = client.post("/api/v1/evaluations", headers=auth_header, json=payload1)
    assert r2.status_code == 200
    assert r2.json()["evaluation_id"] == eval_id_first

    # Send conflicting payload with same idempotency key -> HTTP 409 Conflict
    payload_conflicting = {
        "input_text": "different question",
        "output_text": "different answer",
    }
    r3 = client.post(
        "/api/v1/evaluations", headers=auth_header, json=payload_conflicting
    )
    assert r3.status_code == 409
    assert "Idempotency key conflict" in r3.json()["detail"]


def test_webhook_hmac_signature_and_replay_protection():
    """Verify HMAC SHA-256 signature, payload integrity, and timestamp replay prevention."""
    mgr = WebhookManager()
    secret = "whsec_super_secret_signing_key_123"
    payload = b'{"event": "safety.completed", "status": "safe"}'

    # 1. Valid Signature
    sig, timestamp = mgr.sign_payload_with_timestamp(secret, payload)
    assert mgr.verify_signature_with_timestamp(secret, payload, sig, timestamp) is True

    # 2. Tampered Payload Rejection
    tampered = b'{"event": "safety.completed", "status": "UNSAFE"}'
    assert (
        mgr.verify_signature_with_timestamp(secret, tampered, sig, timestamp) is False
    )

    # 3. Wrong Secret Rejection
    assert (
        mgr.verify_signature_with_timestamp("wrong_secret", payload, sig, timestamp)
        is False
    )

    # 4. Replay Prevention
    # The first verification passed; a replay of the exact same signature is rejected
    assert mgr.verify_signature_with_timestamp(secret, payload, sig, timestamp) is False

    # 5. Expired timestamp rejection
    expired_ts = time.time() - 400.0  # 400s old (window is 300s)
    sig_old, _ = mgr.sign_payload_with_timestamp(secret, payload, timestamp=expired_ts)
    assert (
        mgr.verify_signature_with_timestamp(secret, payload, sig_old, expired_ts)
        is False
    )


def test_webhook_secrets_never_exposed_in_models():
    """Verify that registering a webhook returns secret_hash, never the raw secret."""
    app = create_app()
    client = TestClient(app)
    auth_header = {"Authorization": "Bearer bearer_token_tenant_wh_user1_owner"}

    raw_secret = "whsec_confidential_raw_secret_value"
    res = client.post(
        "/api/v1/webhooks",
        headers=auth_header,
        json={"url": "https://example.com/webhook", "secret": raw_secret},
    )
    assert res.status_code == 200
    data = res.json()
    assert "secret_hash" in data
    assert raw_secret not in str(data)
    assert raw_secret not in res.text


def test_async_job_security_and_tenant_scoping():
    """Verify async jobs cannot be viewed or cancelled across tenant boundaries."""
    mgr = JobManager()

    job_a = mgr.submit_job(operation="eval", payload={"p": 1}, tenant_id="tenant_A")
    job_b = mgr.submit_job(operation="eval", payload={"p": 2}, tenant_id="tenant_B")

    # Tenant A accesses Tenant A job: OK
    assert mgr.get_job(job_a.job_id, tenant_id="tenant_A") is not None
    assert mgr.get_job(job_b.job_id, tenant_id="tenant_B") is not None

    # Tenant B accesses Tenant A job: Denied (returns None)
    assert mgr.get_job(job_a.job_id, tenant_id="tenant_B") is None

    # Tenant B attempts to cancel Tenant A job: Fails
    assert mgr.cancel_job(job_a.job_id, tenant_id="tenant_B") is False
    assert mgr.get_job(job_a.job_id, tenant_id="tenant_A").status != JobStatus.CANCELLED

    # Tenant A cancels own job: Succeeds
    assert mgr.cancel_job(job_a.job_id, tenant_id="tenant_A") is True
    assert mgr.get_job(job_a.job_id, tenant_id="tenant_A").status == JobStatus.CANCELLED
