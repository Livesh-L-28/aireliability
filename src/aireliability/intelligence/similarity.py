"""Deterministic normalization, fingerprinting, and structural similarity for failures."""

from __future__ import annotations

import hashlib
import re

from aireliability.core.models import ExecutionTrace, FailureReport
from aireliability.diagnosis.models import RootCause
from aireliability.intelligence.models import NormalizedFailure
from aireliability.telemetry.sanitizer import SanitizationPolicy

# Patterns for volatile substrings in error messages
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+|\b[0-9a-f]{16,64}\b")
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b"
)
_NUMERIC_RE = re.compile(r"\b\d+\b")


class FailureNormalizer:
    """Normalizes raw failure reports and execution traces into canonical, privacy-safe representations."""

    def __init__(self, sanitizer: SanitizationPolicy | None = None) -> None:
        self.sanitizer = sanitizer or SanitizationPolicy()

    def sanitize_message(self, message: str) -> str:
        """Strip volatile identifiers, timestamps, memory addresses, and sensitive values."""
        if not message:
            return ""

        # 1. Privacy sanitization (passwords, tokens, API keys)
        sanitized = self.sanitizer.sanitize(message)
        if not isinstance(sanitized, str):
            sanitized = str(sanitized)

        # 2. Strip volatile tokens
        sanitized = _UUID_RE.sub("<UUID>", sanitized)
        sanitized = _TIMESTAMP_RE.sub("<TIMESTAMP>", sanitized)
        sanitized = _HEX_RE.sub("<HEX>", sanitized)
        sanitized = _NUMERIC_RE.sub("<NUM>", sanitized)

        # 3. Normalize whitespace
        return " ".join(sanitized.split()).strip()

    def extract_component(
        self,
        failure: FailureReport,
        root_cause: RootCause | None = None,
        trace: ExecutionTrace | None = None,
    ) -> str:
        """Determine the primary system component associated with the failure."""
        meta = failure.metadata or {}
        if "component" in meta:
            return str(meta["component"])
        if "tool_name" in meta:
            return f"tool:{meta['tool_name']}"
        if "retriever" in meta:
            return f"retriever:{meta['retriever']}"
        if "model" in meta:
            return f"model:{meta['model']}"

        if root_cause and root_cause.affected_step:
            return f"step:{root_cause.affected_step}"

        if trace and trace.metadata:
            if "model" in trace.metadata:
                return f"model:{trace.metadata['model']}"
            if "retriever" in trace.metadata:
                return f"retriever:{trace.metadata['retriever']}"

        cat = getattr(failure.category, "value", str(failure.category)).lower()
        return f"system:{cat}"

    def compute_fingerprint(
        self,
        category: str,
        failure_type: str,
        root_cause_cat: str | None = None,
        root_cause_type: str | None = None,
        evaluator: str | None = None,
        component: str | None = None,
        sanitized_message: str = "",
    ) -> str:
        """Generate a stable deterministic hex hash fingerprint representing failure identity."""
        return compute_fingerprint(
            category=category,
            failure_type=failure_type,
            root_cause_cat=root_cause_cat,
            root_cause_type=root_cause_type,
            evaluator=evaluator,
            component=component,
            sanitized_message=sanitized_message,
        )

    def normalize(
        self,
        failure: FailureReport,
        root_cause: RootCause | None = None,
        trace: ExecutionTrace | None = None,
    ) -> NormalizedFailure:
        """Transform a FailureReport into a NormalizedFailure."""
        cat_str = getattr(failure.category, "value", str(failure.category)).lower()
        type_str = getattr(failure.type, "value", str(failure.type)).lower()
        sanitized_msg = self.sanitize_message(failure.message)
        comp = self.extract_component(failure, root_cause, trace)

        rc_cat = None
        rc_type = None
        if root_cause:
            rc_cat = getattr(
                root_cause.category, "value", str(root_cause.category)
            ).lower()
            rc_type = getattr(root_cause.type, "value", str(root_cause.type)).lower()

        evaluator = None
        metric = None
        if isinstance(failure.evidence, dict):
            evaluator = failure.evidence.get("evaluator")
            metric = failure.evidence.get("metric")
        elif failure.metadata:
            evaluator = failure.metadata.get("evaluator")
            metric = failure.metadata.get("metric")

        fingerprint = self.compute_fingerprint(
            category=cat_str,
            failure_type=type_str,
            root_cause_cat=rc_cat,
            root_cause_type=rc_type,
            evaluator=evaluator,
            component=comp,
            sanitized_message=sanitized_msg,
        )

        return NormalizedFailure(
            fingerprint=fingerprint,
            failure_id=failure.failure_id,
            category=cat_str,
            failure_type=type_str,
            root_cause_category=rc_cat,
            root_cause_type=rc_type,
            evaluator=evaluator,
            metric=metric,
            component=comp,
            test_id=failure.test_id,
            trace_id=failure.trace_id,
            severity=str(getattr(failure.severity, "value", failure.severity)),
            confidence=failure.confidence,
            sanitized_message=sanitized_msg,
            metadata=dict(failure.metadata or {}),
        )


def compute_fingerprint(
    category: str,
    failure_type: str,
    root_cause_cat: str | None = None,
    root_cause_type: str | None = None,
    evaluator: str | None = None,
    component: str | None = None,
    sanitized_message: str = "",
) -> str:
    """Generate a stable deterministic hex hash fingerprint representing failure identity."""
    msg_skeleton = sanitized_message[:120].lower()
    parts = [
        category.lower().strip(),
        failure_type.lower().strip(),
        (root_cause_cat or "").lower().strip(),
        (root_cause_type or "").lower().strip(),
        (evaluator or "").lower().strip(),
        (component or "").lower().strip(),
        msg_skeleton,
    ]
    raw_key = "||".join(parts)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


def token_similarity(str_a: str, str_b: str) -> float:
    """Compute Jaccard token overlap similarity between two strings."""
    if not str_a and not str_b:
        return 1.0
    if not str_a or not str_b:
        return 0.0

    tokens_a = set(re.findall(r"\w+", str_a.lower()))
    tokens_b = set(re.findall(r"\w+", str_b.lower()))

    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(tokens_a.intersection(tokens_b))
    union = len(tokens_a.union(tokens_b))
    return intersection / union if union > 0 else 0.0


def failure_similarity(f1: NormalizedFailure, f2: NormalizedFailure) -> float:
    """Calculate multi-attribute structural similarity between two normalized failures."""
    # Fast path: identical fingerprints
    if f1.fingerprint == f2.fingerprint:
        return 1.0

    # 1. Category match (weight: 0.25)
    score_cat = 1.0 if f1.category == f2.category else 0.0

    # 2. Failure type match (weight: 0.20)
    score_type = 1.0 if f1.failure_type == f2.failure_type else 0.0

    # 3. Root cause match (weight: 0.20)
    rc_match = 0.0
    if (
        f1.root_cause_category
        and f2.root_cause_category
        and f1.root_cause_category == f2.root_cause_category
    ):
        rc_match = 0.5
        if (
            f1.root_cause_type
            and f2.root_cause_type
            and f1.root_cause_type == f2.root_cause_type
        ):
            rc_match = 1.0
    score_rc = rc_match

    # 4. Component match (weight: 0.15)
    score_comp = (
        1.0 if f1.component and f2.component and f1.component == f2.component else 0.0
    )

    # 5. Message token similarity (weight: 0.20)
    score_msg = token_similarity(f1.sanitized_message, f2.sanitized_message)

    total_sim = (
        0.25 * score_cat
        + 0.20 * score_type
        + 0.20 * score_rc
        + 0.15 * score_comp
        + 0.20 * score_msg
    )
    return round(min(1.0, max(0.0, total_sim)), 4)
