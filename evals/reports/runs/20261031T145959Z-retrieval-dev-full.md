# Eval: retrieval, dev, full

2026-10-31T14:59:59+00:00 · golden set v2 (manifest 6e45714c9f4a, today pinned to 2026-10-27) · index 11,257 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `a2b71ecde5a5` with uncommitted changes; source sha256 `0765e0302b30b2b8`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.595 | 0.437 to 0.750 | 20 | fail |
| MRR@10 | 0.700 | 0.742 | 0.558 to 0.908 | 20 | pass |
| nDCG@10 | - | 0.590 | 0.434 to 0.742 | 20 |  |
| Judged@10 (labeled share of the top 10) | - | 1.000 | 1.000 to 1.000 | 20 |  |
| Retrieval latency p50 | - | 206 ms | 201 ms to 213 ms | 100 |  |
| Retrieval latency p95 | 250 ms | 328 ms | 289 ms to 356 ms | 100 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 156 ms | 153 ms to 160 ms | 100 |  |
| Rerank p95 | - | 235 ms | 211 ms to 311 ms | 100 |  |

Notes:

- Retrieval quality rests on 20 textual questions, so its intervals are wide. Their passage gold is AI-labeled, cross-checked blind by a second model; no human spot check in v2 (evals/eval-card.md).
- Retrieval latency is measured at 11,257 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
