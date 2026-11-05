# Eval: answer, dev, full

2026-11-03T16:28:05+00:00 · golden set v2 (manifest 6e45714c9f4a, today pinned to 2026-10-27) · index 11,257 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `38a6ee7bdced` with uncommitted changes; source sha256 `817d241227581619`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `a4da1c402e0a`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 0.950 | 0.835 to 0.986 | 40 | pass |
| Comparison match (both values) | - | 0.867 | 0.621 to 0.963 | 15 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 0.987 | 0.959 to 1.000 | 72 | pass |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.907 | 0.848 to 0.961 | 27 |  |
| Correct refusal | 0.900 | 1.000 | 0.867 to 1.000 | 25 | pass |
| False refusal | 0.050 | 0.013 | 0.002 to 0.072 | 75 | pass |
| Router accuracy (route, tickers, years, metric) | - | 1.000 | 0.963 to 1.000 | 100 |  |
| Route accuracy | - | 1.000 | 0.959 to 1.000 | 90 |  |
| Time to first token p50 | 1,000 ms | 2,311 ms | 2,235 ms to 2,417 ms | 72 | fail |
| Time to first token p95 | 2,000 ms | 2,983 ms | 2,773 ms to 3,703 ms | 72 | fail |
| Full answer p50 | - | 2,879 ms | 2,664 ms to 3,172 ms | 80 |  |
| Full answer p95 | 6,000 ms | 6,897 ms | 4,864 ms to 7,860 ms | 80 | fail |
| Route p50 | - | 1,385 ms | 1,354 ms to 1,516 ms | 98 |  |
| Route p95 | - | 1,983 ms | 1,741 ms to 3,082 ms | 98 |  |
| Facts p50 | - | 56 ms | 49 ms to 61 ms | 55 |  |
| Facts p95 | - | 102 ms | 81 ms to 120 ms | 55 |  |
| Retrieve p50 | - | 38 ms | 23 ms to 44 ms | 39 |  |
| Retrieve p95 | - | 58 ms | 50 ms to 68 ms | 39 |  |
| Generate p50 | - | 1,197 ms | 1,071 ms to 1,424 ms | 80 |  |
| Generate p95 | - | 3,191 ms | 2,741 ms to 3,772 ms | 80 |  |
| Regenerate p50 | - | 1,912 ms | 1,374 ms to 2,290 ms | 15 |  |
| Regenerate p95 | - | 3,381 ms | 2,484 ms to 3,381 ms | 15 |  |
| Input tokens per query | 8,000 | 6,603 | 5,479 to 7,774 | 98 | pass |
| Output tokens per query | 600 | 312 | 251 to 379 | 98 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0008 | $0.0007 to $0.0010 | 98 | pass |
| Cost per query, as billed | $0.0150 | $0.0008 | $0.0007 to $0.0010 | 98 | pass |
| Replies cut at max tokens | - | 0 | - | 100 |  |
| Errors | - | 2 | - | 100 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 98 of 100.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 1 (x15).
- Errors: c03 (UpstreamError: anthropic:claude-haiku-5-5 did not answer (APIConnectionError).); c05 (UpstreamError: anthropic:claude-haiku-5-5 did not answer (APIConnectionError).)

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 199 | 199 | 651,077 | 30,679 |
