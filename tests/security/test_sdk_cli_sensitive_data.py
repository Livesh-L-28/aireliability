"""SDK security, CLI safety, sensitive-data protection, and serialization audit tests."""

from __future__ import annotations

import contextlib

import pytest

from aireliability.api.app import create_app
from aireliability.cli import main
from aireliability.sdk.async_client import AsyncClient
from aireliability.sdk.client import (
    AuthenticationError,
    Client,
    RateLimitError,
    TenantIsolationError,
)
from aireliability.tenancy.models import RateLimitAlgorithm, RateLimitPolicy


def test_sdk_exception_mapping_and_no_credential_leak():
    """Verify SDK maps HTTP errors to typed exceptions without leaking credentials."""
    app = create_app()

    # 1. Authentication failure
    with Client(app=app, api_key="airel_bad_key_12345") as client:
        with pytest.raises(AuthenticationError) as exc_info:
            client.evaluations.get("eval_x")
        # Ensure raw secret is not leaked in exception string
        assert "airel_bad_key_12345" not in str(exc_info.value)
        assert exc_info.value.status_code == 401


def test_sdk_tenant_isolation_error_mapping():
    """Verify cross-tenant 403 maps to TenantIsolationError."""
    app = create_app()
    key_mgr = app.state.key_manager
    _, secret_a = key_mgr.create_key(tenant_id="tenant_A", name="Key A", scopes=["*"])
    _, secret_b = key_mgr.create_key(tenant_id="tenant_B", name="Key B", scopes=["*"])

    with Client(app=app, api_key=secret_a) as client_a:
        res = client_a.evaluations.create(input_text="hello", output_text="world")
        eval_id = res["evaluation_id"]

    with (
        Client(app=app, api_key=secret_b) as client_b,
        pytest.raises(TenantIsolationError),
    ):
        client_b.evaluations.get(eval_id)


def test_sdk_rate_limit_error_mapping():
    """Verify 429 response maps to RateLimitError in SDK."""
    app = create_app()
    app.state.rate_limiter.set_policy(
        "tenant:tenant_rl_sdk",
        RateLimitPolicy(
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            rate=1.0,
            window_seconds=60.0,
        ),
    )
    _, secret = app.state.key_manager.create_key(
        tenant_id="tenant_rl_sdk", name="RL Key", scopes=["*"]
    )

    with Client(app=app, api_key=secret) as client:
        client.evaluations.create(input_text="1", output_text="1")
        with pytest.raises(RateLimitError):
            client.evaluations.create(input_text="2", output_text="2")


@pytest.mark.asyncio
async def test_async_sdk_error_handling():
    """Verify AsyncClient maps authentication errors correctly."""
    app = create_app()
    async with AsyncClient(app=app, api_key="airel_invalid_async_key") as async_client:
        with pytest.raises(AuthenticationError):
            await async_client.evaluations.create(input_text="a", output_text="b")


def test_cli_output_secrets_protection(capsys: pytest.CaptureFixture[str]):
    """Verify CLI commands do not leak credentials in stdout or stderr."""
    commands = [
        ["--help"],
        ["--version"],
        ["tenancy", "--help"],
        ["policy", "--help"],
        ["safety", "--help"],
        ["predict", "--help"],
        ["dashboard", "--help"],
        ["api", "--help"],
    ]

    for cmd in commands:
        with contextlib.suppress(SystemExit):
            main(cmd)
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "password" not in output.lower()
        assert "secret_hash" not in output
        assert "Traceback" not in output
