# Eval: retrieval, dev, full

2026-11-05T21:52:01+00:00 · golden set v3 (manifest 58d844a9b523, today pinned to 2026-10-27) · index 11,375 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `914692732dd0` with uncommitted changes; source sha256 `a854f04331c42a7b`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.584 | 0.428 to 0.734 | 20 | fail |
| MRR@10 | 0.700 | 0.692 | 0.508 to 0.867 | 20 | inconclusive |
| nDCG@10 | - | 0.563 | 0.414 to 0.703 | 20 |  |
| Judged@10 (labeled share of the top 10) | - | 0.865 | 0.805 to 0.920 | 20 |  |
| Retrieval latency p50 | - | 188 ms | 184 ms to 192 ms | 100 |  |
| Retrieval latency p95 | 250 ms | 245 ms | 230 ms to 262 ms | 100 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 137 ms | 136 ms to 139 ms | 100 |  |
| Rerank p95 | - | 173 ms | 160 ms to 183 ms | 100 |  |

Notes:

- Retrieval quality rests on 20 textual questions, so its intervals are wide. Their passage gold is v2's labels moved to the re-parsed chunks by exact text or word overlap (AI-labeled, cross-checked blind by a second model; no human spot check) (evals/eval-card.md).
- Retrieval latency is measured at 11,375 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
