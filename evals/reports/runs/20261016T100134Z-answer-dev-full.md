# Eval: answer, dev, full

2026-10-16T10:01:34+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 0.929 | 0.821 to 1.000 | 28 | pass |
| Comparison match (both values) | - | 1.000 | 1.000 to 1.000 | 10 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 0.928 | 0.780 to 1.000 | 45 | fail |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.935 | 0.852 to 1.000 | 11 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.096 | 0.019 to 0.173 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.714 | 0.600 to 0.814 | 70 |  |
| Route accuracy | - | 0.952 | 0.889 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | 3,720 ms | 3,442 ms to 4,170 ms | 43 | fail |
| Time to first token p95 | 2,000 ms | 9,647 ms | 5,677 ms to 13,867 ms | 43 | fail |
| Full answer p50 | - | 4,058 ms | 3,625 ms to 4,891 ms | 50 |  |
| Full answer p95 | 6,000 ms | 10,960 ms | 9,442 ms to 14,032 ms | 50 | fail |
| Route p50 | - | 665 ms | 619 ms to 702 ms | 65 |  |
| Route p95 | - | 1,147 ms | 965 ms to 1,961 ms | 65 |  |
| Facts p50 | - | 49 ms | 44 ms to 57 ms | 35 |  |
| Facts p95 | - | 96 ms | 78 ms to 98 ms | 35 |  |
| Retrieve p50 | - | 35 ms | 0 ms to 186 ms | 25 |  |
| Retrieve p95 | - | 305 ms | 204 ms to 311 ms | 25 |  |
| Generate p50 | - | 3,306 ms | 2,882 ms to 3,699 ms | 50 |  |
| Generate p95 | - | 9,392 ms | 7,932 ms to 13,282 ms | 50 |  |
| Regenerate p50 | - | 3,849 ms | 3,167 ms to 5,442 ms | 3 |  |
| Regenerate p95 | - | 5,442 ms | 3,167 ms to 5,442 ms | 3 |  |
| Input tokens per query | 8,000 | 3,476 | 2,752 to 4,258 | 67 | pass |
| Output tokens per query | 600 | 184 | 143 to 233 | 67 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0011 | $0.0008 to $0.0014 | 67 | pass |
| Cost per query, as billed | $0.0150 | $0.0000 | $0.0000 to $0.0000 | 67 | pass |
| Replies cut at max tokens | - | 0 | - | 70 |  |
| Errors | - | 3 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 65 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: router: out of scope 1 (n29); model: insufficient evidence 3 (x03, x05, x15); validation: no sentence held up 1 (x17).
- Errors: n25 (no answer within 30 s); x07 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); x20 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.)

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 67 | 72,196 | 5,263 |
| `gemini:gemini-3.5-flash-lite` | 55 | 55 | 163,761 | 7,246 |
