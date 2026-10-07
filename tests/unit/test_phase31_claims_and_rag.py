"""Unit tests for Phase 31 Claim extraction, Hallucination, and RAG evaluation."""

from __future__ import annotations

import pytest

from aireliability.core.models import (
    ExecutionTrace,
    StepType,
    TestCase,
    TraceStep,
)
from aireliability.diagnosis.models import RootCauseCategory
from aireliability.evaluation.claim.classifier import ClaimClassifier
from aireliability.evaluation.claim.extractor import ClaimExtractor
from aireliability.evaluation.claim.hallucination import (
    FaithfulnessEvaluator,
    GroundednessEvaluator,
    HallucinationEvaluator,
)
from aireliability.evaluation.claim.models import Claim, ClaimClassification
from aireliability.evaluation.rag.pipeline import RAGEvaluator
from aireliability.evaluation.rag.reranking import RerankingEvaluator
from aireliability.evaluation.rag.retrieval import RetrievalEvaluator


def test_claim_extractor():
    extractor = ClaimExtractor()
    text = (
        "Paris is the capital of France. The population is 2.1 million people. "
        "The Eiffel Tower was completed in 1889."
    )
    claims = extractor.extract(text)
    assert len(claims) >= 3
    assert any("Paris is the capital of France" in c.text for c in claims)
    assert any("1889" in c.text for c in claims)

    # Empty text
    assert extractor.extract("") == []

    # Custom extractor
    custom = ClaimExtractor(custom_extractor=lambda t: ["Claim A", "Claim B"])
    res = custom.extract("any text")
    assert len(res) == 2
    assert res[0].text == "Claim A"


def test_claim_classifier_overlap():
    classifier = ClaimClassifier(min_overlap_threshold=0.4)
    claim1 = Claim(text="The Eiffel Tower was built in Paris France")
    claim2 = Claim(text="The Colosseum is located in Rome Italy")
    context = (
        "The Eiffel Tower is a landmark located in Paris, France constructed in 1889."
    )

    res1 = classifier.classify_claim(claim1, context)
    assert res1.status == ClaimClassification.SUPPORTED

    res2 = classifier.classify_claim(claim2, context)
    assert res2.status in (
        ClaimClassification.UNSUPPORTED,
        ClaimClassification.CONTRADICTED,
    )


def test_hallucination_and_groundedness_evaluators():
    context_docs = [
        "Python was created by Guido van Rossum and first released in 1991.",
        "Python emphasizes code readability with significant indentation.",
    ]
    test_case = TestCase(
        name="python_facts",
        input="Tell me about Python",
        expected_output="Python was created by Guido van Rossum in 1991.",
        metadata={"context_docs": context_docs},
    )

    # Grounded trace
    trace_grounded = ExecutionTrace(
        test_id=test_case.id,
        input="Tell me about Python",
        output="Python was created by Guido van Rossum in 1991. It emphasizes readability.",
    )

    # Hallucinated trace
    trace_hallucinated = ExecutionTrace(
        test_id=test_case.id,
        input="Tell me about Python",
        output="Python was created by Brendan Eich at Netscape Communications in 1995 for browsers.",
    )

    hallucination_eval = HallucinationEvaluator(max_hallucination_rate=0.2)
    grounded_eval = GroundednessEvaluator(min_grounded_score=0.7)
    faith_eval = FaithfulnessEvaluator(min_faithfulness_score=0.7)

    # Grounded evaluation
    h_res = hallucination_eval.evaluate(trace_grounded, test_case)
    g_res = grounded_eval.evaluate(trace_grounded, test_case)
    f_res = faith_eval.evaluate(trace_grounded, test_case)

    assert h_res.passed is True
    assert g_res.passed is True
    assert f_res.passed is True
    assert g_res.score >= 0.7

    # Hallucinated evaluation
    h_fail = hallucination_eval.evaluate(trace_hallucinated, test_case)
    assert h_fail.passed is False
    assert h_fail.evidence["hallucination_rate"] > 0.2


def test_retrieval_and_reranking_evaluators():
    test_case = TestCase(
        name="retrieval_test",
        input="search query",
        metadata={"relevant_docs": ["doc_1", "doc_2", "doc_3"]},
    )

    step_retrieval = TraceStep(
        type=StepType.RETRIEVAL,
        name="retriever",
        output=[{"id": "doc_1"}, {"id": "doc_99"}, {"id": "doc_2"}, {"id": "doc_44"}],
    )

    trace = ExecutionTrace(
        test_id=test_case.id,
        input="search query",
        output="answer",
        steps=[step_retrieval],
    )

    retrieval_eval = RetrievalEvaluator(k=4, min_recall=0.5)
    result = retrieval_eval.evaluate(trace, test_case)

    assert result.passed is True
    assert result.evidence["precision_at_k"] == 0.5  # 2 of 4 relevant
    assert result.evidence["recall_at_k"] == pytest.approx(2.0 / 3.0, abs=1e-3)

    # Reranking evaluator
    step_rerank = TraceStep(
        type=StepType.RETRIEVAL,
        name="reranker",
        input=[{"id": "doc_99"}, {"id": "doc_1"}],
        output=[{"id": "doc_1"}, {"id": "doc_99"}],
    )
    trace_rerank = ExecutionTrace(
        test_id=test_case.id,
        input="search query",
        steps=[step_rerank],
    )
    rerank_eval = RerankingEvaluator(k=2)
    rerank_res = rerank_eval.evaluate(trace_rerank, test_case)
    assert rerank_res.passed is True
    assert (
        rerank_res.evidence["post_rerank_ndcg"]
        >= rerank_res.evidence["pre_rerank_ndcg"]
    )


def test_rag_pipeline_attribution():
    test_case = TestCase(
        name="mars_rag",
        input="What is the capital of Mars?",
        metadata={
            "relevant_docs": ["doc_mars_base"],
            "context_docs": ["Mars has no capital city or permanent government."],
        },
    )

    # Scenario 1: Retrieval failed (retrieved irrelevant docs)
    trace_retrieval_fail = ExecutionTrace(
        test_id=test_case.id,
        input="What is the capital of Mars?",
        output="The capital of Mars is Olympus City.",
        steps=[
            TraceStep(
                type=StepType.RETRIEVAL,
                name="retriever",
                output=[{"id": "doc_jupiter"}, {"id": "doc_saturn"}],
            )
        ],
    )

    rag_eval = RAGEvaluator(retrieval_k=2, min_retrieval_score=0.5)
    res_retrieval_fail = rag_eval.evaluate(trace_retrieval_fail, test_case)

    assert res_retrieval_fail.passed is False
    assert res_retrieval_fail.evidence["failure_stage"] in ("retrieval", "mixed")
    assert "root_cause_report" in res_retrieval_fail.evidence
    report = res_retrieval_fail.evidence["root_cause_report"]
    primary = report.get("primary_cause") or report.get("primary_root_cause")
    assert primary["category"] == RootCauseCategory.RETRIEVAL.value

    # Scenario 2: Retrieval succeeded, but Generation hallucinated
    trace_gen_fail = ExecutionTrace(
        test_id=test_case.id,
        input="What is the capital of Mars?",
        output="Mars capital is Olympus City with a million settlers.",
        steps=[
            TraceStep(
                type=StepType.RETRIEVAL,
                name="retriever",
                output=[
                    {
                        "id": "doc_mars_base",
                        "text": "Mars has no capital city or permanent government.",
                    }
                ],
            )
        ],
    )
    res_gen_fail = rag_eval.evaluate(trace_gen_fail, test_case)
    assert res_gen_fail.passed is False
    assert res_gen_fail.evidence["attribution"] == "GENERATION_FAILURE"
    assert res_gen_fail.evidence["failure_stage"] in ("generation", "output")
