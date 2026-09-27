"""Synthetic AI Agent Scenarios with Known Failures.

Provides realistic agent tasks across multiple domains (customer support,
data extraction, code generation, and order processing) along with intentionally
mutated versions to simulate known failure modes (wrong tools, order inversions,
schema mismatches, hallucinations, and latency/cost overuse).
"""

from typing import Any


# ==============================================================================
# 1. Customer Support Agent
# Task: Refund handling
# Expected flow: lookup_order -> verify_eligibility -> issue_refund -> send_email
# ==============================================================================
def support_agent_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    """Nominal customer support agent (satisfies all expectations)."""
    user_id = payload.get("user_id", "u123")
    order_id = payload.get("order_id", "ord_999")

    # Trace simulated tool invocations
    tools = [
        {"tool": "lookup_order", "args": {"order_id": order_id}},
        {"tool": "verify_eligibility", "args": {"order_id": order_id}},
        {"tool": "issue_refund", "args": {"order_id": order_id, "amount": 49.99}},
        {
            "tool": "send_email",
            "args": {"user_id": user_id, "template": "refund_confirmation"},
        },
    ]
    return {
        "status": "success",
        "message": f"Refund of $49.99 successfully issued for order {order_id}.",
        "tool_calls": tools,
    }


def support_agent_mutated_wrong_order(payload: dict[str, Any]) -> dict[str, Any]:
    """Mutated agent: tool order inversion failure (issues refund before verify)."""
    user_id = payload.get("user_id", "u123")
    order_id = payload.get("order_id", "ord_999")

    # Inverted order: issue_refund before verify_eligibility
    tools = [
        {"tool": "lookup_order", "args": {"order_id": order_id}},
        {"tool": "issue_refund", "args": {"order_id": order_id, "amount": 49.99}},
        {"tool": "verify_eligibility", "args": {"order_id": order_id}},
        {
            "tool": "send_email",
            "args": {"user_id": user_id, "template": "refund_confirmation"},
        },
    ]
    return {
        "status": "success",
        "message": f"Refund of $49.99 successfully issued for order {order_id}.",
        "tool_calls": tools,
    }


def support_agent_mutated_omitted_step(payload: dict[str, Any]) -> dict[str, Any]:
    """Mutated agent: fails to call verify_eligibility altogether."""
    user_id = payload.get("user_id", "u123")
    order_id = payload.get("order_id", "ord_999")

    tools = [
        {"tool": "lookup_order", "args": {"order_id": order_id}},
        {"tool": "issue_refund", "args": {"order_id": order_id, "amount": 49.99}},
        {
            "tool": "send_email",
            "args": {"user_id": user_id, "template": "refund_confirmation"},
        },
    ]
    return {
        "status": "success",
        "message": f"Refund issued for order {order_id}.",
        "tool_calls": tools,
    }


# ==============================================================================
# 2. Structured Extraction Agent
# Task: Extract invoice metadata conforming to JSON schema
# ==============================================================================
INVOICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["invoice_number", "total_amount", "currency", "line_items"],
    "properties": {
        "invoice_number": {"type": "string"},
        "total_amount": {"type": "number"},
        "currency": {"type": "string"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["description", "price"],
                "properties": {
                    "description": {"type": "string"},
                    "price": {"type": "number"},
                },
            },
        },
    },
}


def extraction_agent_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    """Nominal extraction agent returning valid schema."""
    return {
        "invoice_number": "INV-2026-001",
        "total_amount": 150.00,
        "currency": "USD",
        "line_items": [
            {"description": "AI Reliability Engine Subscription", "price": 100.00},
            {"description": "Setup Fee", "price": 50.00},
        ],
    }


def extraction_agent_mutated_schema_failure(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Mutated agent returning broken schema (missing total_amount)."""
    return {
        "invoice_number": "INV-2026-001",
        # Missing total_amount
        "currency": "USD",
        "line_items": [
            {
                "description": "AI Reliability Engine Subscription",
                "price": "invalid_number_string",
            },
        ],
    }


# ==============================================================================
# 3. Code Assistant Agent
# Task: Refactor and optimize code, providing correct solution and explanation
# ==============================================================================
def code_assistant_baseline(payload: dict[str, Any]) -> str:
    """Nominal code assistant agent."""
    return (
        "Here is the optimized function:\n"
        "```python\n"
        "def compute_total(items):\n"
        "    return sum(item.price for item in items)\n"
        "```\n"
        "Time complexity: O(N), Space complexity: O(1)."
    )


def code_assistant_mutated_hallucination(payload: dict[str, Any]) -> str:
    """Mutated agent returning hallucinated function name and missing O(1) space."""
    return (
        "Here is the function:\n"
        "```python\n"
        "def calculate_everything_now(x):\n"
        "    return 42\n"
        "```\n"
        "Time complexity: O(N^2)."
    )
