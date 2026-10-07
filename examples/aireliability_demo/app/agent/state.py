"""Agent state and memory management."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Represents current internal state and memory of an agent."""

    task_id: str
    current_step: int = 0
    variables: dict[str, Any] = field(default_factory=dict)
    memory_events: list[dict[str, Any]] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    is_completed: bool = False
    corrupted: bool = False

    def update_variable(self, key: str, value: Any) -> None:
        """Update an internal state variable."""
        self.variables[key] = value
        self.history.append(f"state_update:{key}={value}")

    def add_memory(self, content: str, source: str = "observation") -> None:
        """Add a memory event."""
        event = {
            "timestamp": time.time(),
            "content": content,
            "source": source,
            "step": self.current_step,
        }
        self.memory_events.append(event)
        self.history.append(f"memory_event:{content[:40]}")
