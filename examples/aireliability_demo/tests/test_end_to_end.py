"""End-to-end integration tests for AI Reliability Demo platform."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from aireliability_demo.app.dashboard.data import DemoDashboardManager
from aireliability_demo.app.main import app
from aireliability_demo.app.reliability.integration import DemoReliabilityIntegrator
from aireliability_demo.app.reliability.workflows import run_full_workflow
from fastapi.testclient import TestClient

from aireliability.sdk.async_client import AsyncClient
from aireliability.sdk.client import Client


def test_full_17_step_workflow() -> None:
    res = run_full_workflow(verbose=False)
    assert res["workflow_status"] == "DEMO COMPLETE"
    assert res["total_steps"] == 17
    assert res["all_steps_passed"] is True


def test_dashboard_generation_and_exports() -> None:
    mgr = DemoDashboardManager()
    dash, json_out, md_out, html_out = mgr.generate_dashboard()

    assert dash.health_summary.overall_health > 0.5
    assert len(dash.panels) == 21
    assert '"overall_health"' in json_out
    assert "# Enterprise Reliability Intelligence" in md_out
    assert "<!DOCTYPE html>" in html_out
    assert "Enterprise Reliability Intelligence Dashboard" in html_out


def test_multi_tenancy_isolation() -> None:
    integrator = DemoReliabilityIntegrator()
    iso = integrator.verify_tenant_isolation()

    assert iso["alpha_own_access_allowed"] is True
    assert iso["beta_cross_access_denied"] is True
    assert iso["audit_deny_logged"] is True
    assert iso["isolation_status"] == "ENFORCED"


def test_platform_api_endpoints() -> None:
    with TestClient(app) as client:
        # Health
        resp_h = client.get("/health")
        assert resp_h.status_code == 200
        assert resp_h.json()["status"] == "healthy"

        # Demo RAG endpoint
        resp_rag = client.post(
            "/api/v1/demo/rag/run",
            params={
                "query": "What are evaluation capabilities?",
                "scenario": "NORMAL_RETRIEVAL",
            },
        )
        assert resp_rag.status_code == 200
        assert "generated_answer" in resp_rag.json()

        # Demo Agent endpoint
        resp_agent = client.post(
            "/api/v1/demo/agent/run",
            params={"task": "Calculate 2+2", "scenario": "NORMAL_AGENT"},
        )
        assert resp_agent.status_code == 200
        assert resp_agent.json()["total_steps"] >= 1

        # Demo Safety endpoint
        resp_safe = client.post(
            "/api/v1/demo/safety/validate", params={"critical_breach": True}
        )
        assert resp_safe.status_code == 200
        assert resp_safe.json()["hard_veto_applied"] is True

        # Demo HTML Dashboard
        resp_view = client.get("/api/v1/demo/dashboard/view")
        assert resp_view.status_code == 200
        assert "text/html" in resp_view.headers["content-type"]


def test_sdk_synchronous_client() -> None:
    with Client(app=app) as client:
        h = client.health()
        assert h["status"] == "healthy"

        eval_resp = client.evaluations.create(
            input_text="SDK E2E Input",
            output_text="SDK E2E Output",
        )
        assert eval_resp["passed"] is True

        dash_health = client.dashboard.get_health()
        assert dash_health["overall_health"] > 0.0


@pytest.mark.asyncio
async def test_sdk_asynchronous_client() -> None:
    async with AsyncClient(app=app) as async_client:
        h = await async_client.health()
        assert h["status"] == "healthy"

        eval_resp = await async_client.evaluations.create(
            input_text="Async SDK Input",
            output_text="Async SDK Output",
        )
        assert eval_resp["passed"] is True
