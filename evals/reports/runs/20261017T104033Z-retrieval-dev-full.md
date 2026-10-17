# Eval: retrieval, dev, full

2026-10-17T10:40:33+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `70057d9e1bec` with uncommitted changes; source sha256 `d9a2098aeef293fb`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.613 | 0.402 to 0.807 | 14 | fail |
| MRR@10 | 0.700 | 0.649 | 0.423 to 0.857 | 14 | fail |
| nDCG@10 | - | 0.585 | 0.377 to 0.784 | 14 |  |
| Judged@10 (labeled share of the top 10) | - | 1.000 | 1.000 to 1.000 | 14 |  |
| Retrieval latency p50 | - | 182 ms | 179 ms to 184 ms | 70 |  |
| Retrieval latency p95 | 250 ms | 251 ms | 207 ms to 258 ms | 70 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 136 ms | 135 ms to 136 ms | 70 |  |
| Rerank p95 | - | 156 ms | 143 ms to 172 ms | 70 |  |

Notes:

- Retrieval quality rests on 14 textual questions, so its intervals are wide. Their passage gold is AI-labeled, spot-checked by a non-expert; it is not human-verified (evals/eval-card.md).
- Retrieval latency is measured at 11,263 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
