"""Unit tests for Phase 37 RemediationSerializer across all supported formats."""

import json

import pytest

from aireliability.remediation.models import (
    RemediationLifecycleState,
    RemediationPatch,
    RemediationProposal,
    RepairType,
    SimulationResult,
)
from aireliability.remediation.serialization import RemediationSerializer


@pytest.fixture
def sample_proposal() -> RemediationProposal:
    patch = RemediationPatch(
        repair_type=RepairType.CONFIG,
        target_component_id="llm_runtime",
        description="Temperature reduction",
        original_value={"temperature": 0.7},
        patched_value={"temperature": 0.1},
        diff_summary="temperature: 0.7 -> 0.1",
    )
    sim = SimulationResult(
        passed=True,
        total_tests_run=5,
        tests_passed=5,
        tests_failed=0,
        regressions_count=0,
        summary="5/5 passed",
    )
    prop = RemediationProposal(
        title="Reduce Output Temperature",
        description="Ensure deterministic output formatting",
        repair_type=RepairType.CONFIG,
        state=RemediationLifecycleState.APPROVED,
        patches=[patch],
        simulation=sim,
    )
    return prop


def test_serialization_json_roundtrip(sample_proposal: RemediationProposal) -> None:
    """JSON serialization produces valid schema parseable back to RemediationProposal."""
    json_str = RemediationSerializer.to_json(sample_proposal)
    assert sample_proposal.proposal_id in json_str
    assert "temperature: 0.7 -> 0.1" in json_str

    parsed_data = json.loads(json_str)
    reloaded = RemediationProposal.model_validate(parsed_data)
    assert reloaded.proposal_id == sample_proposal.proposal_id
    assert reloaded.repair_type == sample_proposal.repair_type
    assert len(reloaded.patches) == 1


def test_serialization_jsonl(sample_proposal: RemediationProposal) -> None:
    """JSONL exports one JSON record per proposal line."""
    jsonl_str = RemediationSerializer.to_jsonl([sample_proposal, sample_proposal])
    lines = jsonl_str.strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        data = json.loads(line)
        assert data["proposal_id"] == sample_proposal.proposal_id


def test_serialization_csv(sample_proposal: RemediationProposal) -> None:
    """CSV export includes header and appropriate values."""
    csv_str = RemediationSerializer.to_csv([sample_proposal])
    assert "proposal_id,title,repair_type" in csv_str
    assert sample_proposal.proposal_id in csv_str
    assert sample_proposal.repair_type.value in csv_str


def test_serialization_markdown(sample_proposal: RemediationProposal) -> None:
    """Markdown export includes table and formatted sections."""
    md_str = RemediationSerializer.to_markdown([sample_proposal])
    assert "# AI Reliability Self-Healing Remediation Report" in md_str
    assert f"`{sample_proposal.proposal_id}`" in md_str
    assert "temperature: 0.7 -> 0.1" in md_str
