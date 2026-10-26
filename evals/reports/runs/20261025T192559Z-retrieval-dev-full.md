# Eval: retrieval, dev, full

2026-10-25T19:25:59+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-MiniLM-L-2-v2@1b5cd67b15209f24824c50370e0397743aa9b787`, 40 candidates, 256 tokens; refusal gate -3.0.

Code: commit `2ea7a1a76dc5`; source sha256 `33d5b4244222f3d0`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.579 | 0.421 to 0.713 | 14 | fail |
| MRR@10 | 0.700 | 0.720 | 0.500 to 0.917 | 14 | pass |
| nDCG@10 | - | 0.587 | 0.412 to 0.744 | 14 |  |
| Judged@10 (labeled share of the top 10) | - | 0.957 | 0.921 to 0.986 | 14 |  |
| Retrieval latency p50 | - | 325 ms | 315 ms to 330 ms | 70 |  |
| Retrieval latency p95 | 250 ms | 448 ms | 394 ms to 496 ms | 70 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 278 ms | 271 ms to 282 ms | 70 |  |
| Rerank p95 | - | 356 ms | 314 ms to 372 ms | 70 |  |

Notes:

- Retrieval quality rests on 14 textual questions, so its intervals are wide. Their passage gold is AI-labeled, spot-checked by a non-expert; it is not human-verified (evals/eval-card.md).
- Retrieval latency is measured at 11,263 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
