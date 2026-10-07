"""Deterministic generator for benchmark test datasets across SMALL, MEDIUM, and LARGE scales."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


def generate_documents(count: int) -> list[dict[str, Any]]:
    """Generate deterministic knowledge documents."""
    docs = []
    categories = [
        "evaluation",
        "rag",
        "agents",
        "safety",
        "prediction",
        "policy",
        "governance",
    ]
    for i in range(count):
        cat = categories[i % len(categories)]
        docs.append(
            {
                "doc_id": f"doc_{cat}_{i:05d}",
                "title": f"Production Reliability Guide: {cat.capitalize()} Module {i}",
                "category": cat,
                "content": (
                    f"This document provides verified specifications for {cat} module {i}. "
                    f"Operational parameters dictate deterministic verification across boundaries. "
                    f"Invariants must hold under load condition {i % 10}. Reference key: REF-{cat.upper()}-{i}."
                ),
                "metadata": {"version": "1.4.0", "index": i, "status": "active"},
            }
        )
    return docs


def generate_failures(count: int) -> list[dict[str, Any]]:
    """Generate synthetic failure reports for intelligence and regression benchmarking."""
    failures = []
    categories = ["TOOL", "TASK", "PERFORMANCE", "SCHEMA", "SAFETY"]
    types = [
        "WRONG_TOOL",
        "WRONG_ORDER",
        "LATENCY",
        "TASK_INCORRECT",
        "INSUFFICIENT_CONTEXT",
    ]
    for i in range(count):
        cat = categories[i % len(categories)]
        ftype = types[i % len(types)]
        failures.append(
            {
                "failure_id": f"fail_{i:06d}",
                "category": cat,
                "failure_type": ftype,
                "message": f"Deterministic failure injected at step {i}: {cat}.{ftype}",
                "trace_id": f"tr_{i:06d}",
                "confidence": 0.85 + ((i % 15) / 100.0),
                "timestamp": "2026-10-07T12:00:00Z",
            }
        )
    return failures


def generate_agent_steps(count: int) -> list[dict[str, Any]]:
    """Generate sequential agent trajectory steps."""
    tools = ["calculator", "knowledge_search", "document_lookup", "status_lookup"]
    steps = []
    for i in range(count):
        tname = tools[i % len(tools)]
        steps.append(
            {
                "step_number": i + 1,
                "tool_name": tname,
                "input_args": {"query": f"item_{i}", "param": i * 10},
                "output": f"Result_{i} verified.",
                "duration_ms": 1.2 + (i % 5),
                "status": "completed",
            }
        )
    return steps


def ensure_datasets() -> None:
    """Create and cache JSON datasets for small, medium, and large scales."""
    scales = {
        "small": 10,
        "medium": 100,
        "large": 1000,
    }

    for scale, count in scales.items():
        sdir = DATASETS_DIR / scale
        sdir.mkdir(parents=True, exist_ok=True)

        docs = generate_documents(count)
        with open(sdir / "documents.json", "w", encoding="utf-8") as f:
            json.dump(docs, f, indent=2)

        fails = generate_failures(count)
        with open(sdir / "failures.json", "w", encoding="utf-8") as f:
            json.dump(fails, f, indent=2)

        steps = generate_agent_steps(count)
        with open(sdir / "agent_steps.json", "w", encoding="utf-8") as f:
            json.dump(steps, f, indent=2)


if __name__ == "__main__":
    ensure_datasets()
    print("Benchmark datasets generated successfully.")
