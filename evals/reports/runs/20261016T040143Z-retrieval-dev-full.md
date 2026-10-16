# Eval: retrieval, dev, full

2026-10-16T04:01:43+00:00 · golden set v1 (manifest 9985e3ca4a79, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-MiniLM-L-6-v2@233902d25c440f23af6f7d6e94d2946bac0bee0a`, 100 candidates, 512 tokens; refusal gate -3.0.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.705 | 0.514 to 0.864 | 14 | fail |
| MRR@10 | 0.700 | 0.800 | 0.586 to 1.000 | 14 | pass |
| nDCG@10 | - | 0.703 | 0.511 to 0.864 | 14 |  |
| Judged@10 (labeled share of the top 10) | - | 1.000 | 1.000 to 1.000 | 14 |  |
| Retrieval latency p50 | - | 2,530 ms | 2,439 ms to 2,669 ms | 70 |  |
| Retrieval latency p95 | 250 ms | 3,187 ms | 3,076 ms to 3,303 ms | 70 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 2,483 ms | 2,393 ms to 2,610 ms | 70 |  |
| Rerank p95 | - | 3,065 ms | 2,948 ms to 3,218 ms | 70 |  |

Notes:

- Retrieval quality rests on 14 textual questions, so its intervals are wide. Their passage gold is labeled by Claude and audited by a non-expert human, not human-verified (evals/eval-card.md).
- Retrieval latency is measured at 11,263 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
