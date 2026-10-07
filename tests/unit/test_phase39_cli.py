"""Unit tests for Phase 39 CLI commands and argument parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aireliability.cli import create_parser, main


def test_cli_rag_help() -> None:
    """Test CLI parser contains 'rag' subcommand and sub-actions."""
    parser = create_parser()
    actions = [action.dest for action in parser._actions]
    assert "command" in actions


def test_cli_rag_evaluate(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag evaluate' execution."""
    code = main(["rag", "evaluate", "--query", "What is AI reliability?"])
    assert code == 0
    captured = capsys.readouterr()
    assert "RAG Reliability Evaluation" in captured.out


def test_cli_rag_analyze(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag analyze' execution."""
    code = main(["rag", "analyze", "What is AI reliability?"])
    assert code == 0
    captured = capsys.readouterr()
    assert "RAG Query Analysis" in captured.out


def test_cli_rag_retrieve(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag retrieve' execution."""
    code = main(["rag", "retrieve"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Retrieval Evaluation" in captured.out


def test_cli_rag_grounding(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag grounding' execution."""
    code = main(["rag", "grounding"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Grounding & Faithfulness" in captured.out


def test_cli_rag_citations(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag citations' execution."""
    code = main(["rag", "citations"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Inline Citation Validation" in captured.out


def test_cli_rag_claims(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag claims' execution."""
    code = main(["rag", "claims", "Python was created by Guido van Rossum."])
    assert code == 0
    captured = capsys.readouterr()
    assert "Extracted Claims" in captured.out


def test_cli_rag_freshness(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag freshness' execution."""
    code = main(["rag", "freshness", "--freshness-window", "60"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Knowledge Freshness Audit" in captured.out


def test_cli_rag_drift(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag drift' execution."""
    code = main(["rag", "drift"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Statistical RAG Drift Analysis" in captured.out


def test_cli_rag_knowledge(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag knowledge' execution."""
    code = main(["rag", "knowledge"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Knowledge Base Health Audit" in captured.out


def test_cli_rag_conflicts(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag conflicts' execution."""
    code = main(["rag", "conflicts"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Context Contradiction Check" in captured.out


def test_cli_rag_failures(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag failures' execution."""
    code = main(["rag", "failures"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Diagnosed RAG Failures" in captured.out


def test_cli_rag_provenance(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag provenance' execution."""
    code = main(["rag", "provenance"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Provenance Trace" in captured.out


def test_cli_rag_monitor(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag monitor' execution."""
    code = main(["rag", "monitor"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Production RAG Monitoring Active" in captured.out


def test_cli_rag_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag report' execution."""
    code = main(["rag", "report", "--format", "markdown"])
    assert code == 0
    captured = capsys.readouterr()
    assert "RAG Reliability Report" in captured.out


def test_cli_rag_inspect(capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag inspect' execution."""
    code = main(["rag", "inspect"])
    assert code == 0
    captured = capsys.readouterr()
    assert "RAG Run Inspection" in captured.out


def test_cli_rag_regression(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test 'airel rag regression' execution with a test suite file."""
    suite_file = tmp_path / "rag_suite.json"
    suite_data = [
        {
            "query": "What is AI reliability?",
            "expected_answer": "AI reliability ensures safety.",
            "retrieved_documents": [
                {
                    "document_id": "d1",
                    "title": "T1",
                    "text": "AI reliability ensures safety.",
                }
            ],
            "retrieved_chunks": [
                {
                    "chunk_id": "c1",
                    "document_id": "d1",
                    "text": "AI reliability ensures safety.",
                    "retrieval_score": 0.9,
                }
            ],
            "generated_answer": "AI reliability ensures safety [1].",
        }
    ]
    suite_file.write_text(json.dumps(suite_data), encoding="utf-8")

    code = main(["rag", "regression", str(suite_file)])
    assert code == 0
    captured = capsys.readouterr()
    assert "RAG Regression Suite Evaluation" in captured.out
