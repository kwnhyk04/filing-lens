# Eval: answer, regression, full

2026-11-06T22:12:54+00:00 · golden set v3 (manifest 58d844a9b523, today pinned to 2026-10-27) · index 11,375 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `7e1bf05ab677` with uncommitted changes; source sha256 `f117b4e51b4011d1`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `25e4578a6d3b`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | - | - | 0 | not measured |
| Comparison match (both values) | - | 1.000 | 0.439 to 1.000 | 3 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 1.000 | 1.000 to 1.000 | 3 | pass |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.000 | 0.000 to 0.000 | 1 |  |
| Correct refusal | 0.900 | - | - | 0 | not measured |
| False refusal | 0.050 | 0.000 | 0.000 to 0.561 | 3 | inconclusive |
| Router accuracy (route, tickers, years, metric) | - | 0.667 | 0.208 to 0.939 | 3 |  |
| Route accuracy | - | 0.667 | 0.208 to 0.939 | 3 |  |
| Time to first token p50 | 1,000 ms | 2,107 ms | 2,026 ms to 2,782 ms | 3 | fail |
| Time to first token p95 | 2,000 ms | 2,782 ms | 2,026 ms to 2,782 ms | 3 | fail |
| Full answer p50 | - | 2,804 ms | 2,509 ms to 4,911 ms | 3 |  |
| Full answer p95 | 6,000 ms | 4,911 ms | 2,509 ms to 4,911 ms | 3 | pass |
| Route p50 | - | 914 ms | 888 ms to 1,346 ms | 3 |  |
| Route p95 | - | 1,346 ms | 888 ms to 1,346 ms | 3 |  |
| Facts p50 | - | 116 ms | 39 ms to 128 ms | 3 |  |
| Facts p95 | - | 128 ms | 39 ms to 128 ms | 3 |  |
| Retrieve p50 | - | 354 ms | 0 ms to 356 ms | 3 |  |
| Retrieve p95 | - | 356 ms | 0 ms to 356 ms | 3 |  |
| Generate p50 | - | 1,466 ms | 1,466 ms to 1,521 ms | 3 |  |
| Generate p95 | - | 1,521 ms | 1,466 ms to 1,521 ms | 3 |  |
| Regenerate p50 | - | 1,626 ms | 1,626 ms to 1,626 ms | 1 |  |
| Regenerate p95 | - | 1,626 ms | 1,626 ms to 1,626 ms | 1 |  |
| Input tokens per query | 8,000 | 12,994 | 9,364 to 19,191 | 3 | fail |
| Output tokens per query | 600 | 350 | 287 to 456 | 3 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0015 | $0.0011 to $0.0021 | 3 | pass |
| Cost per query, as billed | $0.0150 | $0.0015 | $0.0011 to $0.0021 | 3 | pass |
| Replies cut at max tokens | - | 0 | - | 3 |  |
| Errors | - | 0 | - | 3 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 3 of 3.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 7 | 7 | 38,982 | 1,051 |
