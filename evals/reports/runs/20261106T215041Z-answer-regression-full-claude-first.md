# Eval: answer, regression, full

2026-11-06T21:50:41+00:00 · golden set v3 (manifest 58d844a9b523, today pinned to 2026-10-27) · index 11,375 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `7e1bf05ab677` with uncommitted changes; source sha256 `3ab87e61644b502f`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `25e4578a6d3b`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | - | - | 0 | not measured |
| Comparison match (both values) | - | 1.000 | 0.342 to 1.000 | 2 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 1.000 | 1.000 to 1.000 | 2 | pass |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.000 | 0.000 to 0.000 | 1 |  |
| Correct refusal | 0.900 | - | - | 0 | not measured |
| False refusal | 0.050 | 0.000 | 0.000 to 0.658 | 2 | inconclusive |
| Router accuracy (route, tickers, years, metric) | - | 0.500 | 0.095 to 0.905 | 2 |  |
| Route accuracy | - | 0.500 | 0.095 to 0.905 | 2 |  |
| Time to first token p50 | 1,000 ms | 1,952 ms | 1,952 ms to 2,852 ms | 2 | fail |
| Time to first token p95 | 2,000 ms | 2,852 ms | 1,952 ms to 2,852 ms | 2 | inconclusive |
| Full answer p50 | - | 4,166 ms | 4,166 ms to 4,884 ms | 2 |  |
| Full answer p95 | 6,000 ms | 4,884 ms | 4,166 ms to 4,884 ms | 2 | pass |
| Route p50 | - | 872 ms | 872 ms to 1,535 ms | 2 |  |
| Route p95 | - | 1,535 ms | 872 ms to 1,535 ms | 2 |  |
| Facts p50 | - | 37 ms | 37 ms to 85 ms | 2 |  |
| Facts p95 | - | 85 ms | 37 ms to 85 ms | 2 |  |
| Retrieve p50 | - | 200 ms | 200 ms to 325 ms | 2 |  |
| Retrieve p95 | - | 325 ms | 200 ms to 325 ms | 2 |  |
| Generate p50 | - | 1,477 ms | 1,477 ms to 1,502 ms | 2 |  |
| Generate p95 | - | 1,502 ms | 1,477 ms to 1,502 ms | 2 |  |
| Regenerate p50 | - | 1,462 ms | 1,462 ms to 1,555 ms | 2 |  |
| Regenerate p95 | - | 1,555 ms | 1,462 ms to 1,555 ms | 2 |  |
| Input tokens per query | 8,000 | 19,082 | 18,978 to 19,185 | 2 | fail |
| Output tokens per query | 600 | 546 | 519 to 572 | 2 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0022 | $0.0022 to $0.0022 | 2 | pass |
| Cost per query, as billed | $0.0150 | $0.0022 | $0.0022 to $0.0022 | 2 | pass |
| Replies cut at max tokens | - | 0 | - | 2 |  |
| Errors | - | 0 | - | 2 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 2 of 2.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 6 | 6 | 38,163 | 1,091 |
