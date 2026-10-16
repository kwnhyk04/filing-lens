# Eval: retrieval, dev, full

2026-10-16T03:58:26+00:00 · golden set v1 (manifest 9985e3ca4a79, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-MiniLM-L-2-v2@1b5cd67b15209f24824c50370e0397743aa9b787`, 24 candidates, 256 tokens; refusal gate -3.0.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.601 | 0.443 to 0.732 | 14 | fail |
| MRR@10 | 0.700 | 0.720 | 0.500 to 0.917 | 14 | pass |
| nDCG@10 | - | 0.601 | 0.428 to 0.757 | 14 |  |
| Judged@10 (labeled share of the top 10) | - | 1.000 | 1.000 to 1.000 | 14 |  |
| Retrieval latency p50 | - | 214 ms | 209 ms to 220 ms | 70 |  |
| Retrieval latency p95 | 250 ms | 381 ms | 268 ms to 408 ms | 70 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 167 ms | 164 ms to 169 ms | 70 |  |
| Rerank p95 | - | 194 ms | 185 ms to 253 ms | 70 |  |

Notes:

- Retrieval quality rests on 14 textual questions, so its intervals are wide. Their passage gold is labeled by Claude and audited by a non-expert human, not human-verified (evals/eval-card.md).
- Retrieval latency is measured at 11,263 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
