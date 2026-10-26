# Eval: answer, dev, full

2026-10-25T19:32:42+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `2ea7a1a76dc5`; source sha256 `33d5b4244222f3d0`.

Prompt and schema sha256: router_system `90a8d2a58d7f`, router_schema `2992f7981a0c`, answer_system `a72e8ef8b102`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 0.879 to 1.000 | 28 | pass |
| Comparison match (both values) | - | 1.000 | 0.722 to 1.000 | 10 |  |
| Citation precision (judge) | 0.950 | 0.976 | 0.946 to 1.000 | 52 | pass |
| Citation coverage (last reply before removal) | 0.950 | 0.962 | 0.927 to 0.991 | 52 | pass |
| Faithfulness (judge) | 0.920 | 0.938 | 0.867 to 0.990 | 52 | pass |
| Draft citation pass rate | - | 0.923 | 0.863 to 0.975 | 21 |  |
| Correct refusal | 0.900 | 0.944 | 0.742 to 0.990 | 18 | pass |
| False refusal | 0.050 | 0.019 | 0.003 to 0.101 | 52 | pass |
| Router accuracy (route, tickers, years, metric) | - | 0.800 | 0.692 to 0.877 | 70 |  |
| Route accuracy | - | 0.984 | 0.915 to 0.997 | 63 |  |
| Time to first token p50 | 1,000 ms | - | - | 0 | not measured |
| Time to first token p95 | 2,000 ms | - | - | 0 | not measured |
| Full answer p95 | 6,000 ms | - | - | 0 | not measured |
| Input tokens per query | 8,000 | 5,093 | 3,923 to 6,361 | 70 | pass |
| Output tokens per query | 600 | 311 | 241 to 398 | 70 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0006 | $0.0005 to $0.0008 | 70 | pass |
| Cost per query, as billed | $0.0150 | $0.0005 | $0.0004 to $0.0007 | 70 | pass |
| Replies cut at max tokens | - | 1 | - | 70 |  |
| Errors | - | 0 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 0 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 1 (x15).

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 0 | 72,196 | 5,237 |
| `anthropic:claude-haiku-5-5` | 67 | 67 | 284,347 | 16,550 |
| `groq:openai/gpt-oss-120b` | 52 | 52 | 48,022 | 12,122 |

## claude-primary (local) beside the official run of 2026-10-16T10:01:34+00:00 (`gemini:gemini-3.5-flash-lite`)

| Metric | Official | This run |
| --- | --- | --- |
| Numeric exact match (0.5%) | 0.929 | 1.000 |
| Comparison match (both values) | 1.000 | 1.000 |
| Citation precision (judge) | - | 0.976 |
| Citation coverage (last reply before removal) | 0.928 | 0.962 |
| Faithfulness (judge) | - | 0.938 |
| Draft citation pass rate | 0.935 | 0.923 |
| Correct refusal | 1.000 | 0.944 |
| False refusal | 0.096 | 0.019 |
| Router accuracy (route, tickers, years, metric) | 0.714 | 0.800 |
| Route accuracy | 0.952 | 0.984 |
| Time to first token p50 | 3,720 ms | - |
| Time to first token p95 | 9,647 ms | - |
| Full answer p50 | 4,058 ms | - |
| Full answer p95 | 10,960 ms | - |
| Route p50 | 665 ms | - |
| Route p95 | 1,147 ms | - |
| Facts p50 | 49 ms | - |
| Facts p95 | 96 ms | - |
| Retrieve p50 | 35 ms | - |
| Retrieve p95 | 305 ms | - |
| Generate p50 | 3,306 ms | - |
| Generate p95 | 9,392 ms | - |
| Regenerate p50 | 3,849 ms | - |
| Regenerate p95 | 5,442 ms | - |
| Input tokens per query | 3,476 | 5,093 |
| Output tokens per query | 184 | 311 |
| Cost per query, paid-equivalent | $0.0011 | $0.0006 |
| Cost per query, as billed | $0.0000 | $0.0005 |
| Replies cut at max tokens | 0 | 1 |
| Errors | 3 | 0 |
