"""Explicit registry and security validation for optimizable system variables."""

from __future__ import annotations

import re
from typing import Any

from aireliability.optimization.models import (
    ComponentCategory,
    OptimizationVariable,
    VariableDomain,
)
from aireliability.telemetry.sanitizer import SanitizationPolicy

# Patterns indicating potential command injection or code execution attempts
SUSPICIOUS_PATTERNS = [
    re.compile(r"[;&|`$><]"),
    re.compile(r"__(import|builtins)__"),
    re.compile(r"(exec|eval|system|subprocess|spawn)\s*\("),
    re.compile(r"\b(rm|cat|curl|wget|sh|bash|zsh)\b"),
]

STANDARD_VARIABLES: list[OptimizationVariable] = [
    # Generation
    OptimizationVariable(
        variable_id="temperature",
        name="Sampling Temperature",
        component=ComponentCategory.GENERATION,
        domain=VariableDomain.FLOAT,
        min_value=0.0,
        max_value=2.0,
        step=0.1,
        default_value=0.7,
        description="Controls randomness in model token generation.",
    ),
    OptimizationVariable(
        variable_id="max_tokens",
        name="Maximum Output Tokens",
        component=ComponentCategory.GENERATION,
        domain=VariableDomain.INT,
        min_value=16.0,
        max_value=4096.0,
        step=64.0,
        default_value=512,
        description="Upper bound on completion length.",
    ),
    OptimizationVariable(
        variable_id="top_p",
        name="Nucleus Sampling Top-P",
        component=ComponentCategory.GENERATION,
        domain=VariableDomain.FLOAT,
        min_value=0.0,
        max_value=1.0,
        step=0.05,
        default_value=0.9,
        description="Nucleus probability mass cutoff threshold.",
    ),
    OptimizationVariable(
        variable_id="frequency_penalty",
        name="Frequency Penalty",
        component=ComponentCategory.GENERATION,
        domain=VariableDomain.FLOAT,
        min_value=0.0,
        max_value=2.0,
        step=0.1,
        default_value=0.0,
        description="Penalizes repeated tokens based on frequency.",
    ),
    # Retrieval
    OptimizationVariable(
        variable_id="top_k",
        name="Retrieval Top-K",
        component=ComponentCategory.RETRIEVAL,
        domain=VariableDomain.INT,
        min_value=1.0,
        max_value=50.0,
        step=1.0,
        default_value=5,
        description="Number of context passages retrieved.",
    ),
    OptimizationVariable(
        variable_id="similarity_threshold",
        name="Vector Similarity Threshold",
        component=ComponentCategory.RETRIEVAL,
        domain=VariableDomain.FLOAT,
        min_value=0.0,
        max_value=1.0,
        step=0.05,
        default_value=0.7,
        description="Minimum cosine similarity cutoff for retrieved documents.",
    ),
    OptimizationVariable(
        variable_id="reranker_threshold",
        name="Neural Reranker Threshold",
        component=ComponentCategory.RETRIEVAL,
        domain=VariableDomain.FLOAT,
        min_value=0.0,
        max_value=1.0,
        step=0.05,
        default_value=0.5,
        description="Cross-encoder reranking relevance score cutoff.",
    ),
    OptimizationVariable(
        variable_id="hybrid_alpha",
        name="Hybrid Dense/Sparse Alpha",
        component=ComponentCategory.RETRIEVAL,
        domain=VariableDomain.FLOAT,
        min_value=0.0,
        max_value=1.0,
        step=0.1,
        default_value=0.5,
        description="Weighting between dense semantic search and BM25 sparse search.",
    ),
    OptimizationVariable(
        variable_id="context_size",
        name="Max Context Passages",
        component=ComponentCategory.RAG,
        domain=VariableDomain.INT,
        min_value=1.0,
        max_value=20.0,
        step=1.0,
        default_value=4,
        description="Maximum number of context chunks packed into prompt.",
    ),
    # RAG
    OptimizationVariable(
        variable_id="chunk_size",
        name="Document Chunk Size",
        component=ComponentCategory.RAG,
        domain=VariableDomain.INT,
        min_value=64.0,
        max_value=2048.0,
        step=64.0,
        default_value=256,
        description="Target token size for document chunking.",
    ),
    OptimizationVariable(
        variable_id="context_ordering",
        name="Context Ordering Strategy",
        component=ComponentCategory.RAG,
        domain=VariableDomain.CHOICE,
        choices=["relevance", "chronological", "reverse"],
        default_value="relevance",
        description="Order of retrieved chunks in the prompt context.",
    ),
    # Prompt
    OptimizationVariable(
        variable_id="prompt_version",
        name="Prompt Template Version",
        component=ComponentCategory.PROMPT,
        domain=VariableDomain.CHOICE,
        choices=["v1.0", "v1.1", "v1.2", "v2.0"],
        default_value="v1.0",
        description="Registered version identifier of the prompt template.",
    ),
    OptimizationVariable(
        variable_id="instruction_variant",
        name="Instruction Variant",
        component=ComponentCategory.PROMPT,
        domain=VariableDomain.CHOICE,
        choices=["standard", "concise", "chain_of_thought", "few_shot"],
        default_value="standard",
        description="Alternative instruction formulation style.",
    ),
    OptimizationVariable(
        variable_id="formatting_constraint",
        name="Output Formatting Constraint",
        component=ComponentCategory.PROMPT,
        domain=VariableDomain.CHOICE,
        choices=["plain", "json", "markdown", "structured_xml"],
        default_value="plain",
        description="Structural format required in model response.",
    ),
    # Tool
    OptimizationVariable(
        variable_id="tool_timeout",
        name="Tool Execution Timeout Seconds",
        component=ComponentCategory.TOOL,
        domain=VariableDomain.FLOAT,
        min_value=0.1,
        max_value=60.0,
        step=0.5,
        default_value=5.0,
        description="Maximum execution seconds per tool invocation.",
    ),
    OptimizationVariable(
        variable_id="tool_retry_count",
        name="Tool Retry Attempts",
        component=ComponentCategory.TOOL,
        domain=VariableDomain.INT,
        min_value=0.0,
        max_value=10.0,
        step=1.0,
        default_value=2,
        description="Max retry count with exponential backoff on tool failures.",
    ),
    # Agent
    OptimizationVariable(
        variable_id="max_steps",
        name="Agent Max Steps",
        component=ComponentCategory.AGENT,
        domain=VariableDomain.INT,
        min_value=1.0,
        max_value=50.0,
        step=1.0,
        default_value=10,
        description="Maximum reasoning steps before halting agent execution.",
    ),
    OptimizationVariable(
        variable_id="agent_retry_limit",
        name="Agent Error Retry Limit",
        component=ComponentCategory.AGENT,
        domain=VariableDomain.INT,
        min_value=0.0,
        max_value=10.0,
        step=1.0,
        default_value=2,
        description="Maximum recoverable planning retries.",
    ),
    # Infrastructure
    OptimizationVariable(
        variable_id="batch_size",
        name="Inference Batch Size",
        component=ComponentCategory.INFRASTRUCTURE,
        domain=VariableDomain.INT,
        min_value=1.0,
        max_value=128.0,
        step=1.0,
        default_value=1,
        description="Number of concurrent requests grouped per inference call.",
    ),
    OptimizationVariable(
        variable_id="concurrency",
        name="Evaluation Worker Concurrency",
        component=ComponentCategory.INFRASTRUCTURE,
        domain=VariableDomain.INT,
        min_value=1.0,
        max_value=32.0,
        step=1.0,
        default_value=4,
        description="Thread or task worker concurrency count.",
    ),
    # Model
    OptimizationVariable(
        variable_id="model_name",
        name="Registered Model Selection",
        component=ComponentCategory.MODEL,
        domain=VariableDomain.CHOICE,
        choices=["model-small", "model-medium", "model-large", "model-fast"],
        default_value="model-small",
        description="Registered, approved model candidate identifier.",
    ),
]


class VariableRegistry:
    """Registry maintaining explicitly authorized optimizable variables."""

    def __init__(
        self, initial_variables: list[OptimizationVariable] | None = None
    ) -> None:
        self._variables: dict[str, OptimizationVariable] = {}
        for var in initial_variables or STANDARD_VARIABLES:
            self.register(var)
        self._sanitizer = SanitizationPolicy()

    def register(self, variable: OptimizationVariable) -> None:
        """Register a new authorized optimizable variable."""
        self._variables[variable.variable_id] = variable

    def get(self, variable_id: str) -> OptimizationVariable:
        """Fetch a registered variable by its unique ID."""
        if variable_id not in self._variables:
            raise KeyError(
                f"Unregistered variable '{variable_id}'. Only explicitly registered variables can be optimized."
            )
        return self._variables[variable_id]

    def has(self, variable_id: str) -> bool:
        """Check if a variable ID is registered."""
        return variable_id in self._variables

    def list_variables(self) -> list[OptimizationVariable]:
        """Return all registered variables."""
        return list(self._variables.values())

    def validate_configuration(
        self,
        config: dict[str, Any],
        allowed_variables: list[OptimizationVariable] | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate candidate configuration values against registration and domain boundaries.

        Returns (is_valid, list_of_violations).
        """
        violations: list[str] = []
        allowed_map = (
            {v.variable_id: v for v in allowed_variables}
            if allowed_variables is not None
            else self._variables
        )

        for key, val in config.items():
            if key not in allowed_map and key not in self._variables:
                violations.append(
                    f"Forbidden or unregistered configuration key '{key}'"
                )
                continue

            var = allowed_map.get(key) or self._variables.get(key)
            if not var:
                continue

            # Security: check string values for code injection or shell execution patterns
            if isinstance(val, str):
                for pattern in SUSPICIOUS_PATTERNS:
                    if pattern.search(val):
                        violations.append(
                            f"Security violation in value for '{key}': contains forbidden execution tokens"
                        )
                        break

            # Type and bounds validation
            if var.domain in (VariableDomain.FLOAT, VariableDomain.INT):
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    violations.append(
                        f"Variable '{key}' expects numeric value, got {type(val).__name__}"
                    )
                    continue

                if var.min_value is not None and val < var.min_value:
                    violations.append(
                        f"Variable '{key}' value {val} is below minimum allowed {var.min_value}"
                    )
                if var.max_value is not None and val > var.max_value:
                    violations.append(
                        f"Variable '{key}' value {val} exceeds maximum allowed {var.max_value}"
                    )

            elif var.domain == VariableDomain.CHOICE:
                if var.choices and val not in var.choices:
                    violations.append(
                        f"Variable '{key}' value '{val}' is not in approved choices: {var.choices}"
                    )

            elif var.domain == VariableDomain.BOOL:
                if not isinstance(val, bool):
                    violations.append(
                        f"Variable '{key}' expects boolean, got {type(val).__name__}"
                    )

        return len(violations) == 0, violations


_default_registry = VariableRegistry()


def get_default_variable_registry() -> VariableRegistry:
    """Return the global default variable registry instance."""
    return _default_registry
