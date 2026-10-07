"""RAG test generation targeting retrieval grounding, ranking, context conflicts, and citation validity."""

from __future__ import annotations

from typing import Any

from aireliability.generation.models import (
    GeneratedTest,
    GenerationSourceType,
    GenerationStrategy,
    TestGenerationConfig,
    TestPriority,
    TestProvenance,
    TestRiskLevel,
    TestType,
)


class RAGTestGenerator:
    """Generates tests evaluating RAG retrieval, chunk conflict resolution, ranking, and grounding."""

    strategy = GenerationStrategy.RAG_FOCUSED

    def generate(
        self,
        source: Any,
        config: TestGenerationConfig,
    ) -> list[GeneratedTest]:
        rag_cases = [
            (
                "relevant_grounded_query",
                "What is the warranty period for Model X?",
                "Doc 1: Model X comes with a standard 3-year limited warranty covering parts and labor.",
                [{"doc_id": "doc_1", "text": "Model X warranty is 3 years limited."}],
                ["must answer 3 years", "must cite doc_1 as evidence source"],
                "3-year limited warranty",
                True,
            ),
            (
                "conflicting_evidence_chunks",
                "What is the return window for customer purchases?",
                "Chunk A: Items can be returned within 14 days of delivery.\nChunk B: Items can be returned within 30 days of purchase.",
                [
                    {"doc_id": "chunk_a", "text": "14 days of delivery"},
                    {"doc_id": "chunk_b", "text": "30 days of purchase"},
                ],
                [
                    "must acknowledge conflicting policies between chunk_a and chunk_b",
                    "must not fabricate arbitrary resolution",
                ],
                None,
                False,
            ),
            (
                "no_result_abstention",
                "What is the CEO's favorite breakfast cereal?",
                "",
                [],
                [
                    "must state that retrieved context does not contain answer",
                    "must not hallucinate facts",
                ],
                None,
                False,
            ),
            (
                "retrieval_ranking_distraction",
                "What is the headquarters address of the organization?",
                "Chunk 1 (Irrelevant): Our organization enjoys outdoor retreats.\nChunk 2 (Relevant): Headquarters is located at 100 Main Street, Seattle, WA.",
                [
                    {"doc_id": "c1", "text": "Outdoor retreats"},
                    {"doc_id": "c2", "text": "100 Main Street, Seattle, WA"},
                ],
                [
                    "must identify 100 Main Street, Seattle, WA",
                    "must ignore distractor chunk 1",
                ],
                "100 Main Street, Seattle, WA",
                True,
            ),
        ]

        tests: list[GeneratedTest] = []
        for name, query, context, docs, criteria, ref_ans, has_gt in rag_cases:
            if len(tests) >= config.max_candidates:
                break

            prov = TestProvenance(
                source_type=GenerationSourceType.SYNTHETIC,
                source_id=f"rag_{name}",
                generator_name="RAGTestGenerator",
                deterministic_seed=config.deterministic_seed,
                rationale=f"RAG evaluation case: {name}",
            )

            t = GeneratedTest(
                name=f"rag_{name}",
                test_type=TestType.RAG,
                strategy=self.strategy,
                input=query,
                expected_output=ref_ans,
                expected_criteria=criteria,
                reference_answer=ref_ans,
                has_ground_truth=has_gt,
                context=context,
                retrieved_documents=docs,
                provenance=prov,
                confidence=1.0,
                risk_level=TestRiskLevel.LOW,
                priority=TestPriority.HIGH,
                tags=["rag_focused", f"rag_scenario:{name}"],
                metadata={"documents_count": len(docs)},
                deterministic_seed=config.deterministic_seed,
            )
            tests.append(t)

        return tests
