"""Deterministic normalization, fingerprinting, and near-duplicate similarity for generated tests."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from aireliability.generation.models import GeneratedTest


def _normalize_obj(obj: Any) -> Any:
    """Recursively normalize data structures for deterministic serialization."""
    if obj is None:
        return None
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, str):
        # Collapse excessive whitespace and trim
        return re.sub(r"\s+", " ", obj).strip().lower()
    if isinstance(obj, (list, tuple, set)):
        items = [_normalize_obj(x) for x in obj]
        # If all items are sortable primitives/strings, sort them
        if all(isinstance(x, (str, int, float, bool)) for x in items):
            try:
                return sorted(items, key=lambda x: str(x))
            except Exception:
                return items
        return items
    if isinstance(obj, dict):
        normalized_dict: dict[str, Any] = {}
        for k in sorted(obj.keys(), key=lambda x: str(x)):
            # Skip volatile keys that do not define behavioral semantics
            k_str = str(k).lower()
            if k_str in {
                "id",
                "test_id",
                "timestamp",
                "created_at",
                "generation_timestamp",
                "trace_id",
                "generator_version",
                "seed",
                "duration_ms",
                "fingerprint",
            }:
                continue
            normalized_dict[str(k)] = _normalize_obj(obj[k])
        return normalized_dict
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return _normalize_obj(obj.model_dump())
    return str(obj).strip().lower()


def compute_fingerprint(test: GeneratedTest) -> str:
    """Compute a deterministic, stable SHA-256 fingerprint of test semantics.

    Ignores volatile identifiers, timestamps, and transient metadata.
    """
    canonical_payload = {
        "strategy": str(test.strategy),
        "test_type": str(test.test_type),
        "input": _normalize_obj(test.input),
        "expected_output": _normalize_obj(test.expected_output),
        "expected_criteria": sorted(
            [c.strip().lower() for c in test.expected_criteria]
        ),
        "context": _normalize_obj(test.context) if test.context else None,
        "tool_definitions": _normalize_obj(test.tool_definitions),
        "expected_tool_calls": _normalize_obj(test.expected_tool_calls),
        "expected_trajectory_constraints": sorted(
            [c.strip().lower() for c in test.expected_trajectory_constraints]
        ),
        "mutation_type": test.provenance.mutation_type if test.provenance else None,
    }

    serialized = json.dumps(
        canonical_payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _tokenize(text: str) -> set[str]:
    """Tokenize a string into a set of lowercased alphanumeric tokens."""
    tokens = re.findall(r"\w+", text.lower())
    return set(tokens)


def _extract_textual_features(test: GeneratedTest) -> set[str]:
    """Extract set of tokens representing the textual content of a test."""
    tokens: set[str] = set()

    # Input tokens
    if isinstance(test.input, str):
        tokens.update(_tokenize(test.input))
    elif isinstance(test.input, dict):
        for v in test.input.values():
            if isinstance(v, str):
                tokens.update(_tokenize(v))
    else:
        tokens.update(_tokenize(str(test.input)))

    # Criteria tokens
    for c in test.expected_criteria:
        tokens.update(_tokenize(c))

    # Context tokens
    if test.context:
        tokens.update(_tokenize(test.context))

    # Reference tokens
    if test.reference_answer:
        tokens.update(_tokenize(test.reference_answer))

    # Tools
    for tool in test.tool_definitions:
        if isinstance(tool, dict) and "name" in tool:
            tokens.add(str(tool["name"]).lower())

    return tokens


def compute_token_similarity(test_a: GeneratedTest, test_b: GeneratedTest) -> float:
    """Compute token Jaccard similarity between two generated tests.

    Returns float in range [0.0, 1.0].
    """
    if (
        test_a.fingerprint
        and test_b.fingerprint
        and test_a.fingerprint == test_b.fingerprint
    ):
        return 1.0

    tokens_a = _extract_textual_features(test_a)
    tokens_b = _extract_textual_features(test_b)

    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(tokens_a.intersection(tokens_b))
    union = len(tokens_a.union(tokens_b))

    return float(intersection) / float(union) if union > 0 else 0.0
