"""Serialization and Deterministic Fingerprinting for Phase 40.

Provides JSON and JSONL serialization/deserialization for all agent models:
- AgentRun, AgentTrajectory, AgentStep, ToolCall, ToolResult, AgentFailure,
  AgentReliabilityScore, GoalVerification
Generates deterministic SHA-256 fingerprints across tasks, plans, actions,
tool calls, states, and trajectories for deduplication and regression testing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aireliability.agent.models import (
    AgentPlan,
    AgentReliabilityScore,
    AgentRun,
    AgentStep,
    AgentTask,
    AgentTrajectory,
    GoalVerification,
    ToolCall,
)


def compute_sha256_fingerprint(data: Any) -> str:
    """Compute a canonical SHA-256 hash for arbitrary nested data."""
    if isinstance(data, dict):
        canonical_str = json.dumps(data, sort_keys=True, default=str)
    elif hasattr(data, "model_dump"):
        canonical_str = json.dumps(
            data.model_dump(mode="json"), sort_keys=True, default=str
        )
    else:
        canonical_str = str(data)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:16]


class AgentSerializer:
    """Handles serialization, export, import, and fingerprinting for agent entities."""

    @staticmethod
    def fingerprint_task(task: AgentTask) -> str:
        """Generate deterministic fingerprint for an agent task."""
        data = {
            "request_text": task.request_text.strip(),
            "constraints": sorted(task.constraints),
            "expected_outputs": sorted(task.expected_outputs),
        }
        return compute_sha256_fingerprint(data)

    @staticmethod
    def fingerprint_plan(plan: AgentPlan) -> str:
        """Generate deterministic fingerprint for a planned sequence."""
        data = {
            "steps": plan.steps,
            "dependencies": {
                k: sorted(v) for k, v in sorted(plan.dependencies.items())
            },
        }
        return compute_sha256_fingerprint(data)

    @staticmethod
    def fingerprint_tool_call(tool_call: ToolCall) -> str:
        """Generate deterministic fingerprint for a tool call."""
        data = {
            "tool_name": tool_call.tool_name,
            "arguments": tool_call.arguments,
            "authorization_scope": tool_call.authorization_scope,
        }
        return compute_sha256_fingerprint(data)

    @staticmethod
    def fingerprint_trajectory(trajectory: AgentTrajectory) -> str:
        """Generate deterministic fingerprint for an ordered trajectory sequence."""
        step_signatures = [
            f"{s.action_type.value}:{s.tool_call.tool_name if s.tool_call else ''}:{s.action}"
            for s in sorted(trajectory.steps, key=lambda s: s.sequence)
        ]
        return compute_sha256_fingerprint(step_signatures)

    @staticmethod
    def to_json(
        entity: AgentRun
        | AgentTrajectory
        | AgentStep
        | AgentReliabilityScore
        | GoalVerification,
    ) -> str:
        """Serialize entity to JSON string."""
        return entity.model_dump_json(indent=2)

    @staticmethod
    def to_json_file(entity: AgentRun | AgentTrajectory, path: Path | str) -> None:
        """Save entity to a JSON file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(entity.model_dump_json(indent=2), encoding="utf-8")

    @staticmethod
    def from_json(json_str: str, entity_cls: type[Any] = AgentRun) -> Any:
        """Deserialize entity from JSON string."""
        return entity_cls.model_validate_json(json_str)

    @staticmethod
    def from_json_file(path: Path | str, entity_cls: type[Any] = AgentRun) -> Any:
        """Load entity from a JSON file."""
        content = Path(path).read_text(encoding="utf-8")
        return entity_cls.model_validate_json(content)

    @staticmethod
    def export_runs_jsonl(runs: list[AgentRun], path: Path | str) -> None:
        """Export multiple AgentRuns as JSON Lines."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            for r in runs:
                f.write(r.model_dump_json() + "\n")

    @staticmethod
    def load_runs_jsonl(path: Path | str) -> list[AgentRun]:
        """Load multiple AgentRuns from a JSON Lines file."""
        runs: list[AgentRun] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    runs.append(AgentRun.model_validate_json(line.strip()))
        return runs
