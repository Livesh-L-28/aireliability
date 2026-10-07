# Retrieval-Augmented Generation (RAG) Reliability

The Phase 39 RAG reliability system provides an 11-stage audit across the entire retrieval-augmented lifecycle.
It isolates retrieval errors from generation errors, ensuring pinpoint diagnosis of grounding failures.

## Key Lifecycle Stages
1. **Query Analysis**: Assesses query completeness, ambiguity, and retrieval difficulty.
2. **Retrieval Evaluation**: Measures document recall, precision, Hit Rate, MRR, and NDCG against ground truth.
3. **Context Quality**: Detects noisy chunks, cross-document conflicts, and stale knowledge.
4. **Claim Alignment & Grounding**: Extracts factual claims, aligns them with retrieved evidence, and flags ungrounded assertions.
5. **Citation Validation**: Verifies that cited markers accurately reference the specific chunks supporting each claim.
6. **Freshness Tracking**: Flags outdated information based on document timestamps and staleness thresholds.
