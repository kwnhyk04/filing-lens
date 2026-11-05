# Eval: all, test, full

2026-11-05T07:15:54+00:00 · golden set v2 (manifest 6e45714c9f4a, today pinned to 2026-10-27) · index 11,257 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `38a6ee7bdced` with uncommitted changes; source sha256 `6fb20da4b325490d`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `25e4578a6d3b`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.596 | 0.490 to 0.698 | 25 | fail |
| MRR@10 | 0.700 | 0.628 | 0.480 to 0.772 | 25 | fail |
| nDCG@10 | - | 0.525 | 0.419 to 0.632 | 25 |  |
| Judged@10 (labeled share of the top 10) | - | 1.000 | 1.000 to 1.000 | 25 |  |
| Retrieval latency p50 | - | 171 ms | 168 ms to 175 ms | 55 |  |
| Retrieval latency p95 | 250 ms | 266 ms | 212 ms to 384 ms | 55 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 132 ms | 130 ms to 133 ms | 55 |  |
| Rerank p95 | - | 154 ms | 145 ms to 257 ms | 55 |  |

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 0.758 to 1.000 | 12 | pass |
| Comparison match (both values) | - | 1.000 | 0.676 to 1.000 | 8 |  |
| Citation precision (judge) | 0.950 | 0.993 | 0.977 to 1.000 | 43 | pass |
| Citation coverage (last reply before removal) | 0.950 | 0.950 | 0.882 to 1.000 | 43 | pass |
| Faithfulness (judge) | 0.920 | 0.976 | 0.946 to 1.000 | 43 | pass |
| Draft citation pass rate | - | 0.921 | 0.844 to 0.978 | 26 |  |
| Correct refusal | 0.900 | 1.000 | 0.722 to 1.000 | 10 | pass |
| False refusal | 0.050 | 0.044 | 0.012 to 0.148 | 45 | pass |
| Router accuracy (route, tickers, years, metric) | - | 0.982 | 0.904 to 0.997 | 55 |  |
| Route accuracy | - | 1.000 | 0.930 to 1.000 | 51 |  |
| Time to first token p50 | 1,000 ms | 2,414 ms | 2,235 ms to 2,504 ms | 43 | fail |
| Time to first token p95 | 2,000 ms | 3,032 ms | 2,898 ms to 3,250 ms | 43 | fail |
| Full answer p50 | - | 3,943 ms | 3,073 ms to 4,505 ms | 47 |  |
| Full answer p95 | 6,000 ms | 7,287 ms | 6,293 ms to 8,809 ms | 47 | fail |
| Route p50 | - | 1,321 ms | 1,144 ms to 1,432 ms | 55 |  |
| Route p95 | - | 2,036 ms | 1,698 ms to 3,224 ms | 55 |  |
| Facts p50 | - | 49 ms | 41 ms to 52 ms | 20 |  |
| Facts p95 | - | 86 ms | 52 ms to 93 ms | 20 |  |
| Retrieve p50 | - | 36 ms | 30 ms to 38 ms | 36 |  |
| Retrieve p95 | - | 65 ms | 45 ms to 73 ms | 36 |  |
| Generate p50 | - | 2,032 ms | 1,509 ms to 2,492 ms | 47 |  |
| Generate p95 | - | 3,514 ms | 3,156 ms to 3,909 ms | 47 |  |
| Regenerate p50 | - | 2,218 ms | 1,545 ms to 2,869 ms | 15 |  |
| Regenerate p95 | - | 3,842 ms | 2,869 ms to 3,842 ms | 15 |  |
| Input tokens per query | 8,000 | 9,408 | 7,827 to 11,025 | 55 | fail |
| Output tokens per query | 600 | 484 | 376 to 603 | 55 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0012 | $0.0010 to $0.0014 | 55 | pass |
| Cost per query, as billed | $0.0150 | $0.0012 | $0.0010 to $0.0014 | 55 | pass |
| Replies cut at max tokens | - | 0 | - | 55 |  |
| Errors | - | 0 | - | 55 |  |

Notes:

- Retrieval quality rests on 25 textual questions, so its intervals are very wide. Their passage gold is AI-labeled, cross-checked blind by a second model; no human spot check in v2 (evals/eval-card.md).
- Retrieval latency is measured at 11,257 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
- Latency comes only from questions whose model calls were all live: 55 of 55.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: relevance gate 1 (x21); model: insufficient evidence 1 (x42).

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 120 | 120 | 517,416 | 26,644 |
| `groq:openai/gpt-oss-120b` | 43 | 42 | 58,261 | 13,394 |

## claude-first beside the official run of 2026-10-31T15:31:56+00:00 (`gemini:gemini-3.5-flash-lite`)

| Metric | Official | This run |
| --- | --- | --- |
| Retrieval recall@10 | 0.596 | 0.596 |
| MRR@10 | 0.628 | 0.628 |
| nDCG@10 | 0.525 | 0.525 |
| Judged@10 (labeled share of the top 10) | 1.000 | 1.000 |
| Retrieval latency p50 | 227 ms | 171 ms |
| Retrieval latency p95 | 333 ms | 266 ms |
| Rerank p50 | 171 ms | 132 ms |
| Rerank p95 | 222 ms | 154 ms |
| Numeric exact match (0.5%) | 1.000 | 1.000 |
| Comparison match (both values) | 1.000 | 1.000 |
| Citation precision (judge) | 1.000 | 0.993 |
| Citation coverage (last reply before removal) | 1.000 | 0.950 |
| Faithfulness (judge) | 0.990 | 0.976 |
| Draft citation pass rate | 0.972 | 0.921 |
| Correct refusal | 1.000 | 1.000 |
| False refusal | 0.133 | 0.044 |
| Router accuracy (route, tickers, years, metric) | 0.564 | 0.982 |
| Route accuracy | 0.961 | 1.000 |
| Time to first token p50 | 1,473 ms | 2,414 ms |
| Time to first token p95 | 2,116 ms | 3,032 ms |
| Full answer p50 | 2,321 ms | 3,943 ms |
| Full answer p95 | 3,981 ms | 7,287 ms |
| Route p50 | 659 ms | 1,321 ms |
| Route p95 | 1,295 ms | 2,036 ms |
| Facts p50 | 54 ms | 49 ms |
| Facts p95 | 113 ms | 86 ms |
| Retrieve p50 | 38 ms | 36 ms |
| Retrieve p95 | 232 ms | 65 ms |
| Generate p50 | 1,451 ms | 2,032 ms |
| Generate p95 | 2,510 ms | 3,514 ms |
| Regenerate p50 | 1,538 ms | 2,218 ms |
| Regenerate p95 | 1,822 ms | 3,842 ms |
| Input tokens per query | 5,715 | 9,408 |
| Output tokens per query | 321 | 484 |
| Cost per query, paid-equivalent | $0.0021 | $0.0012 |
| Cost per query, as billed | $0.0000 | $0.0012 |
| Replies cut at max tokens | 0 | 0 |
| Errors | 0 | 0 |
