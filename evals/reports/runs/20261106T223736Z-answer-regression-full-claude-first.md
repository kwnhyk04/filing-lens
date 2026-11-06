# Eval: answer, regression, full

2026-11-06T22:37:36+00:00 · golden set v3 (manifest 58d844a9b523, today pinned to 2026-10-27) · index 11,375 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `7e1bf05ab677` with uncommitted changes; source sha256 `f117b4e51b4011d1`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `25e4578a6d3b`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | - | - | 0 | not measured |
| Comparison match (both values) | - | 1.000 | 0.857 to 1.000 | 23 |  |
| Citation precision (judge) | 0.950 | 1.000 | 1.000 to 1.000 | 23 | pass |
| Citation coverage (last reply before removal) | 0.950 | 1.000 | 1.000 to 1.000 | 23 | pass |
| Faithfulness (judge) | 0.920 | 1.000 | 1.000 to 1.000 | 23 | pass |
| Draft citation pass rate | - | 0.947 | 0.880 to 1.000 | 12 |  |
| Correct refusal | 0.900 | - | - | 0 | not measured |
| False refusal | 0.050 | 0.000 | 0.000 to 0.143 | 23 | inconclusive |
| Router accuracy (route, tickers, years, metric) | - | 1.000 | 0.857 to 1.000 | 23 |  |
| Route accuracy | - | 1.000 | 0.857 to 1.000 | 23 |  |
| Time to first token p50 | 1,000 ms | 1,878 ms | 1,816 ms to 2,072 ms | 23 | fail |
| Time to first token p95 | 2,000 ms | 2,349 ms | 2,195 ms to 2,527 ms | 23 | fail |
| Full answer p50 | - | 2,765 ms | 2,436 ms to 3,574 ms | 23 |  |
| Full answer p95 | 6,000 ms | 4,858 ms | 4,204 ms to 5,665 ms | 23 | pass |
| Route p50 | - | 1,017 ms | 952 ms to 1,056 ms | 23 |  |
| Route p95 | - | 1,508 ms | 1,245 ms to 1,538 ms | 23 |  |
| Facts p50 | - | 61 ms | 51 ms to 83 ms | 23 |  |
| Facts p95 | - | 139 ms | 91 ms to 140 ms | 23 |  |
| Retrieve p50 | - | 0 ms | 0 ms to 0 ms | 23 |  |
| Retrieve p95 | - | 0 ms | 0 ms to 0 ms | 23 |  |
| Generate p50 | - | 1,586 ms | 1,393 ms to 1,722 ms | 23 |  |
| Generate p95 | - | 2,188 ms | 1,739 ms to 2,303 ms | 23 |  |
| Regenerate p50 | - | 1,360 ms | 1,216 ms to 1,669 ms | 8 |  |
| Regenerate p95 | - | 1,803 ms | 1,562 ms to 1,803 ms | 8 |  |
| Input tokens per query | 8,000 | 13,032 | 11,523 to 14,710 | 23 | fail |
| Output tokens per query | 600 | 439 | 364 to 524 | 23 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0015 | $0.0013 to $0.0017 | 23 | pass |
| Cost per query, as billed | $0.0150 | $0.0015 | $0.0013 to $0.0017 | 23 | pass |
| Replies cut at max tokens | - | 0 | - | 23 |  |
| Errors | - | 0 | - | 23 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 23 of 23.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 54 | 54 | 299,740 | 10,108 |
| `groq:openai/gpt-oss-120b` | 23 | 23 | 24,269 | 7,055 |
