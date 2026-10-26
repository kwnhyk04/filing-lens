# Eval: retrieval, dev, full

2026-10-25T19:23:10+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 256 tokens; refusal gate -3.0.

Code: commit `2ea7a1a76dc5`; source sha256 `33d5b4244222f3d0`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.581 | 0.435 to 0.718 | 14 | fail |
| MRR@10 | 0.700 | 0.677 | 0.463 to 0.871 | 14 | fail |
| nDCG@10 | - | 0.565 | 0.390 to 0.734 | 14 |  |
| Judged@10 (labeled share of the top 10) | - | 0.914 | 0.879 to 0.950 | 14 |  |
| Retrieval latency p50 | - | 146 ms | 135 ms to 155 ms | 70 |  |
| Retrieval latency p95 | 250 ms | 252 ms | 209 ms to 324 ms | 70 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 84 ms | 82 ms to 85 ms | 70 |  |
| Rerank p95 | - | 154 ms | 122 ms to 170 ms | 70 |  |

Notes:

- Retrieval quality rests on 14 textual questions, so its intervals are wide. Their passage gold is AI-labeled, spot-checked by a non-expert; it is not human-verified (evals/eval-card.md).
- Retrieval latency is measured at 11,263 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
