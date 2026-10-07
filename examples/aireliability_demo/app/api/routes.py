"""Demo specific FastAPI routes exposing RAG, Agent, Safety, and Workflow endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from aireliability_demo.app.agent.agent import ControlledAgent
from aireliability_demo.app.dashboard.data import DemoDashboardManager
from aireliability_demo.app.rag.pipeline import RAGPipeline
from aireliability_demo.app.reliability.workflows import run_full_workflow
from aireliability_demo.app.scenarios.safety_failure import run_safety_failure_scenario

demo_router = APIRouter(prefix="/api/v1/demo", tags=["Demo Workflows"])


@demo_router.post("/rag/run")
def run_demo_rag(
    query: str = Query(
        "What are the core capabilities of the AI reliability evaluation framework?"
    ),
    scenario: str = Query("NORMAL_RETRIEVAL"),
) -> dict[str, Any]:
    """Execute demo RAG query under normal or failure scenario."""
    pipeline = RAGPipeline()
    result = pipeline.run(query_text=query, scenario=scenario)
    return {
        "query": result["query"],
        "scenario": result["scenario"],
        "generated_answer": result["generated_answer"],
        "retrieved_chunks_count": len(result["retrieved_chunks"]),
    }


@demo_router.post("/agent/run")
def run_demo_agent(
    task: str = Query(
        "Calculate the projected reliability score after a 15% improvement from 0.80."
    ),
    scenario: str = Query("NORMAL_AGENT"),
) -> dict[str, Any]:
    """Execute controlled demo autonomous agent task."""
    agent = ControlledAgent("APIDemoAgent")
    run = agent.execute_task(task_text=task, scenario=scenario)
    return {
        "run_id": run.run_id,
        "agent_id": run.agent_id,
        "scenario": scenario,
        "final_response": run.final_response,
        "total_steps": run.trajectory.total_steps,
        "tools_used": run.tools,
        "failures_count": len(run.failures),
    }


@demo_router.post("/safety/validate")
def validate_demo_safety(
    critical_breach: bool = Query(False),
) -> dict[str, Any]:
    """Execute synthetic adversarial probe safety validation."""
    return run_safety_failure_scenario(simulate_critical_breach=critical_breach)


@demo_router.post("/workflow/execute")
def execute_complete_workflow() -> dict[str, Any]:
    """Execute complete 17-step end-to-end reliability workflow."""
    return run_full_workflow(verbose=False)


@demo_router.get("/dashboard/view", response_class=HTMLResponse)
def view_dashboard_html() -> HTMLResponse:
    """Render interactive lightweight HTML dashboard."""
    mgr = DemoDashboardManager()
    _d, _json_out, _md_out, html_out = mgr.generate_dashboard()
    return HTMLResponse(content=html_out)
