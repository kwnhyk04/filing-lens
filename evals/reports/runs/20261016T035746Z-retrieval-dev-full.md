# Eval: retrieval, dev, full

2026-10-16T03:57:46+00:00 · golden set v1 (manifest 9985e3ca4a79, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.613 | 0.402 to 0.807 | 14 | fail |
| MRR@10 | 0.700 | 0.649 | 0.423 to 0.857 | 14 | fail |
| nDCG@10 | - | 0.584 | 0.377 to 0.782 | 14 |  |
| Judged@10 (labeled share of the top 10) | - | 1.000 | 1.000 to 1.000 | 14 |  |
| Retrieval latency p50 | - | 203 ms | 194 ms to 219 ms | 70 |  |
| Retrieval latency p95 | 250 ms | 323 ms | 273 ms to 356 ms | 70 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 142 ms | 138 ms to 150 ms | 70 |  |
| Rerank p95 | - | 217 ms | 175 ms to 229 ms | 70 |  |

Notes:

- Retrieval quality rests on 14 textual questions, so its intervals are wide. Their passage gold is labeled by Claude and audited by a non-expert human, not human-verified (evals/eval-card.md).
- Retrieval latency is measured at 11,263 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
