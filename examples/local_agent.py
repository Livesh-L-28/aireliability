"""Realistic deterministic customer support agent for Phase 15.

Runs completely locally without external LLM APIs.
Simulates customer support workflows such as:
1. get_order(order_id)
2. cancel_order(order_id)
3. refund_order(order_id)

Emits structured tool events / ToolCallRecords during execution.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aireliability.execution.adapters import ToolCallRecord


class LocalSupportAgent:
    """Local, deterministic customer-support agent with configurable tool behavior.

    In nominal mode:
        get_order -> cancel_order -> refund_order -> confirmation message

    In faulty mode (reversing order):
        get_order -> refund_order -> cancel_order -> confirmation message
    """

    def __init__(
        self,
        *,
        mode: str = "nominal",
        delay_seconds: float = 0.0,
        tool_call_listener: Callable[[ToolCallRecord], None] | None = None,
    ) -> None:
        """Initialize LocalSupportAgent.

        Args:
            mode: 'nominal' for correct execution order, 'faulty' for inverted order.
            delay_seconds: Optional sleep simulation.
            tool_call_listener: Optional callback receiving each ToolCallRecord.
        """
        self.mode = mode
        self.delay_seconds = delay_seconds
        self.tool_call_listener = tool_call_listener
        self.tool_calls: list[ToolCallRecord] = []
        self._orders_db = {
            "123": {"status": "active", "amount": 99.99, "items": ["Item A"]},
            "456": {
                "status": "shipped",
                "amount": 149.50,
                "items": ["Item B", "Item C"],
            },
        }

    def reset(self) -> None:
        """Reset captured tool calls history."""
        self.tool_calls = []

    def _record_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        result: Any,
        start_time: datetime,
    ) -> ToolCallRecord:
        end_time = datetime.now(UTC)
        duration_ms = max(0.0, (end_time - start_time).total_seconds() * 1000.0)
        record = ToolCallRecord(
            name=name,
            arguments=arguments,
            result=result,
            started_at=start_time,
            completed_at=end_time,
            duration_ms=duration_ms,
            status="completed",
        )
        self.tool_calls.append(record)
        if self.tool_call_listener:
            self.tool_call_listener(record)
        return record

    def get_order(self, order_id: str) -> dict[str, Any]:
        """Look up order details."""
        start = datetime.now(UTC)
        order = self._orders_db.get(order_id, {"status": "not_found", "amount": 0.0})
        res = {"order_id": order_id, **order}
        self._record_tool_call("get_order", {"order_id": order_id}, res, start)
        return res

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an existing order."""
        start = datetime.now(UTC)
        res = {
            "order_id": order_id,
            "status": "cancelled",
            "cancelled_at": datetime.now(UTC).isoformat(),
        }
        self._record_tool_call("cancel_order", {"order_id": order_id}, res, start)
        return res

    def refund_order(self, order_id: str) -> dict[str, Any]:
        """Process refund for an order."""
        start = datetime.now(UTC)
        res = {
            "order_id": order_id,
            "status": "refunded",
            "refunded_at": datetime.now(UTC).isoformat(),
        }
        self._record_tool_call("refund_order", {"order_id": order_id}, res, start)
        return res

    def run(self, user_prompt: str | dict[str, Any]) -> str:
        """Execute customer support request based on user prompt."""
        self.reset()

        # Extract order_id if present
        order_id = "123"
        if isinstance(user_prompt, dict):
            order_id = str(user_prompt.get("order_id", "123"))
        elif isinstance(user_prompt, str):
            for token in user_prompt.replace(".", " ").replace(",", " ").split():
                if token.isdigit():
                    order_id = token
                    break

        if self.mode == "faulty":
            # Buggy sequence: refund before cancel
            self.get_order(order_id)
            self.refund_order(order_id)
            self.cancel_order(order_id)
            return (
                f"Your refund and cancellation for order {order_id} has been processed."
            )

        # Nominal sequence: get -> cancel -> refund
        self.get_order(order_id)
        self.cancel_order(order_id)
        self.refund_order(order_id)
        return f"Your refund and cancellation for order {order_id} has been processed."
