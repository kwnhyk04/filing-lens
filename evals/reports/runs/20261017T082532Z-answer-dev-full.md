# Eval: answer, dev, full

2026-10-17T08:25:32+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `77e59a095f90` with uncommitted changes; source sha256 `989adfb3043b7669`.

Prompt and schema sha256: router_system `90a8d2a58d7f`, router_schema `2992f7981a0c`, answer_system `a72e8ef8b102`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 0.929 | 0.821 to 1.000 | 28 | pass |
| Comparison match (both values) | - | 1.000 | 1.000 to 1.000 | 10 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 0.933 | 0.856 to 0.989 | 49 | fail |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.889 | 0.797 to 0.964 | 19 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.058 | 0.000 to 0.135 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.743 | 0.643 to 0.843 | 70 |  |
| Route accuracy | - | 0.968 | 0.921 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | 3,030 ms | 3,030 ms to 3,030 ms | 1 | fail |
| Time to first token p95 | 2,000 ms | 3,030 ms | 3,030 ms to 3,030 ms | 1 | fail |
| Full answer p50 | - | 5,487 ms | 5,487 ms to 5,487 ms | 1 |  |
| Full answer p95 | 6,000 ms | 5,487 ms | 5,487 ms to 5,487 ms | 1 | pass |
| Route p50 | - | 744 ms | 744 ms to 744 ms | 1 |  |
| Route p95 | - | 744 ms | 744 ms to 744 ms | 1 |  |
| Retrieve p50 | - | 1,072 ms | 1,072 ms to 1,072 ms | 1 |  |
| Retrieve p95 | - | 1,072 ms | 1,072 ms to 1,072 ms | 1 |  |
| Generate p50 | - | 3,665 ms | 3,665 ms to 3,665 ms | 1 |  |
| Generate p95 | - | 3,665 ms | 3,665 ms to 3,665 ms | 1 |  |
| Input tokens per query | 8,000 | 5,338 | 4,030 to 6,729 | 70 | pass |
| Output tokens per query | 600 | 301 | 231 to 381 | 70 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0006 | $0.0005 to $0.0008 | 70 | pass |
| Cost per query, as billed | $0.0150 | $0.0005 | $0.0004 to $0.0007 | 70 | pass |
| Replies cut at max tokens | - | 0 | - | 70 |  |
| Errors | - | 0 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 1 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 2 (n17, n24); router: out of scope 1 (x15).

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 1 | 72,196 | 5,175 |
| `anthropic:claude-haiku-5-5` | 67 | 67 | 301,466 | 15,870 |
