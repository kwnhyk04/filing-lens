# Eval: retrieval, dev, full

2026-10-25T19:23:55+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 30 candidates, 384 tokens; refusal gate -3.0.

Code: commit `2ea7a1a76dc5`; source sha256 `33d5b4244222f3d0`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.606 | 0.400 to 0.798 | 14 | fail |
| MRR@10 | 0.700 | 0.661 | 0.429 to 0.875 | 14 | fail |
| nDCG@10 | - | 0.594 | 0.388 to 0.790 | 14 |  |
| Judged@10 (labeled share of the top 10) | - | 0.936 | 0.893 to 0.979 | 14 |  |
| Retrieval latency p50 | - | 121 ms | 119 ms to 127 ms | 70 |  |
| Retrieval latency p95 | 250 ms | 247 ms | 208 ms to 359 ms | 70 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 77 ms | 76 ms to 79 ms | 70 |  |
| Rerank p95 | - | 136 ms | 92 ms to 205 ms | 70 |  |

Notes:

- Retrieval quality rests on 14 textual questions, so its intervals are wide. Their passage gold is AI-labeled, spot-checked by a non-expert; it is not human-verified (evals/eval-card.md).
- Retrieval latency is measured at 11,263 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
