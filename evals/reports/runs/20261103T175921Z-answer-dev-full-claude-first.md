# Eval: answer, dev, full

2026-11-03T17:59:21+00:00 · golden set v2 (manifest 6e45714c9f4a, today pinned to 2026-10-27) · index 11,257 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-sonnet-5-5` (thinking between_tools, effort high), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `38a6ee7bdced` with uncommitted changes; source sha256 `817d241227581619`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `a4da1c402e0a`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 0.912 to 1.000 | 40 | pass |
| Comparison match (both values) | - | 1.000 | 0.796 to 1.000 | 15 |  |
| Citation precision (judge) | 0.950 | 0.984 | 0.959 to 1.000 | 74 | pass |
| Citation coverage (last reply before removal) | 0.950 | 1.000 | 1.000 to 1.000 | 74 | pass |
| Faithfulness (judge) | 0.920 | 0.986 | 0.968 to 1.000 | 74 | pass |
| Draft citation pass rate | - | 0.990 | 0.968 to 1.000 | 26 |  |
| Correct refusal | 0.900 | 1.000 | 0.867 to 1.000 | 25 | pass |
| False refusal | 0.050 | 0.013 | 0.002 to 0.072 | 75 | pass |
| Router accuracy (route, tickers, years, metric) | - | 1.000 | 0.963 to 1.000 | 100 |  |
| Route accuracy | - | 1.000 | 0.959 to 1.000 | 90 |  |
| Time to first token p50 | 1,000 ms | - | - | 0 | not measured |
| Time to first token p95 | 2,000 ms | - | - | 0 | not measured |
| Full answer p95 | 6,000 ms | - | - | 0 | not measured |
| Input tokens per query | 8,000 | 7,100 | 5,888 to 8,367 | 100 | pass |
| Output tokens per query | 600 | 288 | 231 to 350 | 100 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0126 | $0.0097 to $0.0156 | 100 | pass |
| Cost per query, as billed | $0.0150 | $0.0126 | $0.0097 to $0.0156 | 100 | pass |
| Replies cut at max tokens | - | 0 | - | 100 |  |
| Errors | - | 0 | - | 100 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 0 of 100.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 1 (x15).

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 104 | 0 | 205,730 | 6,245 |
| `anthropic:claude-sonnet-5-5` | 102 | 0 | 504,274 | 22,599 |
| `groq:openai/gpt-oss-120b` | 74 | 64 | 67,939 | 18,297 |
