# Eval: answer, dev, full

2026-10-17T07:57:34+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `anthropic:claude-haiku-5-5` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `77e59a095f90` with uncommitted changes; source sha256 `71e0f97a9cc7cd1b`.

Prompt and schema sha256: router_system `90a8d2a58d7f`, router_schema `2992f7981a0c`, answer_system `a72e8ef8b102`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 0.929 | 0.821 to 1.000 | 28 | pass |
| Comparison match (both values) | - | 1.000 | 1.000 to 1.000 | 10 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 0.987 | 0.956 to 1.000 | 45 | pass |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.963 | 0.909 to 1.000 | 16 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.115 | 0.038 to 0.212 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.743 | 0.643 to 0.843 | 70 |  |
| Route accuracy | - | 0.952 | 0.889 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | 1,584 ms | 1,529 ms to 2,320 ms | 48 | fail |
| Time to first token p95 | 2,000 ms | 4,232 ms | 3,612 ms to 4,989 ms | 48 | fail |
| Full answer p50 | - | 2,096 ms | 1,836 ms to 2,592 ms | 54 |  |
| Full answer p95 | 6,000 ms | 9,484 ms | 4,670 ms to 9,949 ms | 54 | fail |
| Route p50 | - | 583 ms | 568 ms to 605 ms | 69 |  |
| Route p95 | - | 801 ms | 679 ms to 886 ms | 69 |  |
| Facts p50 | - | 50 ms | 46 ms to 55 ms | 39 |  |
| Facts p95 | - | 100 ms | 88 ms to 141 ms | 39 |  |
| Retrieve p50 | - | 36 ms | 0 ms to 172 ms | 26 |  |
| Retrieve p95 | - | 263 ms | 185 ms to 282 ms | 26 |  |
| Generate p50 | - | 1,412 ms | 1,150 ms to 1,973 ms | 54 |  |
| Generate p95 | - | 4,435 ms | 3,730 ms to 4,713 ms | 54 |  |
| Regenerate p50 | - | 4,158 ms | 3,286 ms to 4,454 ms | 6 |  |
| Regenerate p95 | - | 4,544 ms | 4,454 ms to 4,544 ms | 6 |  |
| Input tokens per query | 8,000 | 4,557 | 3,528 to 5,700 | 69 | pass |
| Output tokens per query | 600 | 394 | 290 to 513 | 69 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0006 | $0.0005 to $0.0008 | 69 | pass |
| Cost per query, as billed | $0.0150 | $0.0005 | $0.0004 to $0.0007 | 69 | pass |
| Replies cut at max tokens | - | 4 | - | 70 |  |
| Errors | - | 1 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 69 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 2 (n17, n24); validation: no sentence held up 3 (x03, x17, x19); router: out of scope 1 (x15).
- Errors: x11 (UpstreamError: groq:openai/gpt-oss-20b answered 400.)

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 69 | 69 | 71,168 | 5,124 |
| `anthropic:claude-haiku-5-5` | 60 | 60 | 243,295 | 22,083 |
