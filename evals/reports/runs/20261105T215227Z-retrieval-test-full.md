# Eval: retrieval, test, full

2026-11-05T21:52:27+00:00 · golden set v3 (manifest 58d844a9b523, today pinned to 2026-10-27) · index 11,375 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `914692732dd0` with uncommitted changes; source sha256 `a854f04331c42a7b`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.599 | 0.485 to 0.713 | 25 | fail |
| MRR@10 | 0.700 | 0.577 | 0.424 to 0.732 | 25 | inconclusive |
| nDCG@10 | - | 0.485 | 0.384 to 0.589 | 25 |  |
| Judged@10 (labeled share of the top 10) | - | 0.776 | 0.696 to 0.852 | 25 |  |
| Retrieval latency p50 | - | 186 ms | 178 ms to 190 ms | 55 |  |
| Retrieval latency p95 | 250 ms | 265 ms | 251 ms to 272 ms | 55 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 138 ms | 136 ms to 141 ms | 55 |  |
| Rerank p95 | - | 190 ms | 150 ms to 205 ms | 55 |  |

Notes:

- Retrieval quality rests on 25 textual questions, so its intervals are very wide. Their passage gold is v2's labels moved to the re-parsed chunks by exact text or word overlap (AI-labeled, cross-checked blind by a second model; no human spot check) (evals/eval-card.md).
- Retrieval latency is measured at 11,375 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
