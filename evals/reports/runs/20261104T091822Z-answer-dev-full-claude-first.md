# Eval: answer, dev, full

2026-11-04T09:18:22+00:00 · golden set v2 (manifest 6e45714c9f4a, today pinned to 2026-10-27) · index 11,257 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `38a6ee7bdced` with uncommitted changes; source sha256 `b45f8c239c5bfe8e`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `25e4578a6d3b`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 0.912 to 1.000 | 40 | pass |
| Comparison match (both values) | - | 1.000 | 0.796 to 1.000 | 15 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 0.962 | 0.913 to 1.000 | 74 | pass |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.869 | 0.792 to 0.936 | 25 |  |
| Correct refusal | 0.900 | 1.000 | 0.867 to 1.000 | 25 | pass |
| False refusal | 0.050 | 0.013 | 0.002 to 0.072 | 75 | pass |
| Router accuracy (route, tickers, years, metric) | - | 1.000 | 0.963 to 1.000 | 100 |  |
| Route accuracy | - | 1.000 | 0.959 to 1.000 | 90 |  |
| Time to first token p50 | 1,000 ms | 2,490 ms | 2,368 ms to 2,556 ms | 75 | fail |
| Time to first token p95 | 2,000 ms | 4,072 ms | 3,163 ms to 4,950 ms | 75 | fail |
| Full answer p50 | - | 3,344 ms | 2,898 ms to 3,772 ms | 83 |  |
| Full answer p95 | 6,000 ms | 6,760 ms | 6,060 ms to 7,514 ms | 83 | fail |
| Route p50 | - | 1,470 ms | 1,385 ms to 1,574 ms | 100 |  |
| Route p95 | - | 2,531 ms | 1,913 ms to 3,070 ms | 100 |  |
| Facts p50 | - | 54 ms | 48 ms to 62 ms | 57 |  |
| Facts p95 | - | 96 ms | 85 ms to 102 ms | 57 |  |
| Retrieve p50 | - | 32 ms | 0 ms to 40 ms | 42 |  |
| Retrieve p95 | - | 65 ms | 55 ms to 71 ms | 42 |  |
| Generate p50 | - | 1,324 ms | 1,124 ms to 1,696 ms | 83 |  |
| Generate p95 | - | 3,051 ms | 2,719 ms to 3,583 ms | 83 |  |
| Regenerate p50 | - | 2,123 ms | 1,599 ms to 2,462 ms | 19 |  |
| Regenerate p95 | - | 3,535 ms | 2,582 ms to 3,535 ms | 19 |  |
| Input tokens per query | 8,000 | 7,128 | 5,946 to 8,387 | 100 | pass |
| Output tokens per query | 600 | 313 | 251 to 382 | 100 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0009 | $0.0007 to $0.0010 | 100 | pass |
| Cost per query, as billed | $0.0150 | $0.0009 | $0.0007 to $0.0010 | 100 | pass |
| Replies cut at max tokens | - | 0 | - | 100 |  |
| Errors | - | 0 | - | 100 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 100 of 100.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 1 (x15).

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 207 | 207 | 712,794 | 31,317 |
