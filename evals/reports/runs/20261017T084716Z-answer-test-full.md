# Eval: answer, test, full

2026-10-17T08:47:16+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `77e59a095f90` with uncommitted changes; source sha256 `08bbeaee98fd8686`.

Prompt and schema sha256: router_system `90a8d2a58d7f`, router_schema `2992f7981a0c`, answer_system `a72e8ef8b102`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 1.000 to 1.000 | 12 | pass |
| Comparison match (both values) | - | 1.000 | 1.000 to 1.000 | 5 |  |
| Citation precision (judge) | 0.950 | 0.958 | 0.880 to 1.000 | 20 | pass |
| Citation coverage (last reply before removal) | 0.950 | 1.000 | 1.000 to 1.000 | 20 | pass |
| Faithfulness (judge) | 0.920 | 0.944 | 0.857 to 1.000 | 20 | pass |
| Draft citation pass rate | - | 0.792 | 0.500 to 1.000 | 6 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 7 | pass |
| False refusal | 0.050 | 0.130 | 0.000 to 0.261 | 23 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.767 | 0.600 to 0.900 | 30 |  |
| Route accuracy | - | 0.889 | 0.778 to 1.000 | 27 |  |
| Time to first token p50 | 1,000 ms | - | - | 0 | not measured |
| Time to first token p95 | 2,000 ms | - | - | 0 | not measured |
| Full answer p95 | 6,000 ms | - | - | 0 | not measured |
| Input tokens per query | 8,000 | 4,853 | 3,028 to 6,951 | 30 | pass |
| Output tokens per query | 600 | 278 | 168 to 425 | 30 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0006 | $0.0004 to $0.0009 | 30 | pass |
| Cost per query, as billed | $0.0150 | $0.0005 | $0.0003 to $0.0008 | 30 | pass |
| Replies cut at max tokens | - | 0 | - | 30 |  |
| Errors | - | 0 | - | 30 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 0 of 30.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: router: out of scope 3 (x13, x14, x18).

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 30 | 0 | 30,931 | 2,264 |
| `anthropic:claude-haiku-5-5` | 26 | 26 | 114,659 | 6,066 |
| `groq:openai/gpt-oss-120b` | 20 | 14 | 18,154 | 4,800 |
