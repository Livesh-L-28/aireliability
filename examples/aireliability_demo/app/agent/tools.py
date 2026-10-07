"""Deterministic safe tools for autonomous agent execution."""

from __future__ import annotations

import ast
import operator
from typing import Any

from aireliability.agent.models import ToolRiskLevel
from aireliability_demo.app.rag.documents import load_documents
from aireliability_demo.app.rag.retriever import DeterministicRetriever

_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[op_type](
                _eval_node(node.left), _eval_node(node.right)
            )
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[op_type](_eval_node(node.operand))
    raise ValueError("Unsupported or unsafe math expression")


def tool_calculator(expression: str) -> str:
    """Safely evaluate arithmetic expressions without eval() or shell execution."""
    clean_expr = expression.strip()
    try:
        parsed = ast.parse(clean_expr, mode="eval")
        result = _eval_node(parsed.body)
        return str(round(result, 4))
    except Exception as exc:
        return f"CALCULATION_ERROR: {exc}"


_GLOBAL_RETRIEVER: DeterministicRetriever | None = None


def _get_retriever() -> DeterministicRetriever:
    global _GLOBAL_RETRIEVER
    if _GLOBAL_RETRIEVER is None:
        docs = load_documents()
        _GLOBAL_RETRIEVER = DeterministicRetriever(docs)
    return _GLOBAL_RETRIEVER


def tool_knowledge_search(query: str) -> str:
    """Search knowledge base deterministically."""
    retriever = _get_retriever()
    _docs, chunks = retriever.retrieve(query, top_k=2)
    if not chunks:
        return "No matching documentation found."
    return "\n---\n".join([f"[{c.chunk_id}] {c.text}" for c in chunks])


def tool_document_lookup(doc_id: str) -> str:
    """Lookup specific document content by filename or id."""
    retriever = _get_retriever()
    if doc_id in retriever.documents:
        return retriever.documents[doc_id].text
    for key, doc in retriever.documents.items():
        if doc_id.lower() in key.lower():
            return doc.text
    return f"DOCUMENT_NOT_FOUND: {doc_id}"


def tool_status_lookup(component: str) -> str:
    """Lookup component operational status."""
    component_lower = component.lower()
    valid_components = {
        "evaluation": {"status": "HEALTHY", "active_tests": 1013},
        "rag": {"status": "HEALTHY", "index_size": 7},
        "agent": {"status": "HEALTHY", "max_concurrency": 4},
        "safety": {"status": "ACTIVE", "hard_veto_enforced": True},
        "prediction": {"status": "HEALTHY", "confidence": 0.94},
        "policy": {"status": "ENFORCING", "active_rules": 5},
    }
    for comp_name, data in valid_components.items():
        if comp_name in component_lower:
            return f"COMPONENT_STATUS: {data}"
    return f"UNKNOWN_COMPONENT: {component}"


DEMO_TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "calculator": {
        "function": tool_calculator,
        "description": "Evaluate arithmetic expressions safely.",
        "risk_level": ToolRiskLevel.LOW,
        "required_args": ["expression"],
    },
    "knowledge_search": {
        "function": tool_knowledge_search,
        "description": "Search knowledge base for reliability guidelines.",
        "risk_level": ToolRiskLevel.LOW,
        "required_args": ["query"],
    },
    "document_lookup": {
        "function": tool_document_lookup,
        "description": "Lookup full text of documentation.",
        "risk_level": ToolRiskLevel.LOW,
        "required_args": ["doc_id"],
    },
    "status_lookup": {
        "function": tool_status_lookup,
        "description": "Check operational status of platform components.",
        "risk_level": ToolRiskLevel.LOW,
        "required_args": ["component"],
    },
}
