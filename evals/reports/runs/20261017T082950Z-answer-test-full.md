# Eval: answer, test, full

2026-10-17T08:29:50+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `77e59a095f90` with uncommitted changes; source sha256 `bff83173019144e3`.

Prompt and schema sha256: router_system `90a8d2a58d7f`, router_schema `2992f7981a0c`, answer_system `a72e8ef8b102`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 1.000 to 1.000 | 12 | pass |
| Comparison match (both values) | - | 1.000 | 1.000 to 1.000 | 5 |  |
| Citation precision (judge) | 0.950 | 1.000 | 1.000 to 1.000 | 23 | pass |
| Citation coverage (last reply before removal) | 0.950 | 1.000 | 1.000 to 1.000 | 23 | pass |
| Faithfulness (judge) | 0.920 | 0.979 | 0.930 to 1.000 | 23 | pass |
| Draft citation pass rate | - | 0.917 | 0.818 to 1.000 | 9 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 7 | pass |
| False refusal | 0.050 | 0.000 | 0.000 to 0.000 | 23 | pass |
| Router accuracy (route, tickers, years, metric) | - | 0.733 | 0.567 to 0.867 | 30 |  |
| Route accuracy | - | 1.000 | 1.000 to 1.000 | 27 |  |
| Time to first token p50 | 1,000 ms | 1,578 ms | 1,514 ms to 1,830 ms | 23 | fail |
| Time to first token p95 | 2,000 ms | 2,705 ms | 1,993 ms to 3,062 ms | 23 | fail |
| Full answer p50 | - | 2,066 ms | 1,855 ms to 2,924 ms | 24 |  |
| Full answer p95 | 6,000 ms | 5,323 ms | 3,584 ms to 6,786 ms | 24 | pass |
| Route p50 | - | 623 ms | 542 ms to 683 ms | 30 |  |
| Route p95 | - | 1,607 ms | 710 ms to 2,089 ms | 30 |  |
| Facts p50 | - | 47 ms | 42 ms to 55 ms | 17 |  |
| Facts p95 | - | 76 ms | 64 ms to 76 ms | 17 |  |
| Retrieve p50 | - | 35 ms | 0 ms to 225 ms | 13 |  |
| Retrieve p95 | - | 405 ms | 225 ms to 405 ms | 13 |  |
| Generate p50 | - | 1,151 ms | 1,071 ms to 1,636 ms | 24 |  |
| Generate p95 | - | 2,828 ms | 1,982 ms to 3,207 ms | 24 |  |
| Regenerate p50 | - | 2,164 ms | 1,634 ms to 2,840 ms | 5 |  |
| Regenerate p95 | - | 2,840 ms | 2,164 ms to 2,840 ms | 5 |  |
| Input tokens per query | 8,000 | 5,634 | 3,588 to 7,831 | 30 | pass |
| Output tokens per query | 600 | 336 | 220 to 472 | 30 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0007 | $0.0004 to $0.0010 | 30 | pass |
| Cost per query, as billed | $0.0150 | $0.0006 | $0.0003 to $0.0009 | 30 | pass |
| Replies cut at max tokens | - | 0 | - | 30 |  |
| Errors | - | 0 | - | 30 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 30 of 30.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 30 | 30 | 30,931 | 2,311 |
| `anthropic:claude-haiku-5-5` | 29 | 29 | 138,098 | 7,754 |
| `groq:openai/gpt-oss-120b` | 23 | 23 | 22,216 | 5,834 |
