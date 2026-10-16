# Eval: answer, dev, full

2026-10-16T09:16:44+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking default), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 0.893 | 0.750 to 1.000 | 28 | fail |
| Comparison match (both values) | - | 0.500 | 0.200 to 0.800 | 10 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 0.857 | 0.679 to 1.000 | 38 | fail |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.920 | 0.828 to 1.000 | 10 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.077 | 0.019 to 0.154 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.771 | 0.671 to 0.857 | 70 |  |
| Route accuracy | - | 0.968 | 0.921 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | - | - | 0 | not measured |
| Time to first token p95 | 2,000 ms | - | - | 0 | not measured |
| Full answer p95 | 6,000 ms | - | - | 0 | not measured |
| Input tokens per query | 8,000 | 2,974 | 2,243 to 3,778 | 58 | pass |
| Output tokens per query | 600 | 176 | 130 to 236 | 58 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0009 | $0.0006 to $0.0013 | 58 | pass |
| Cost per query, as billed | $0.0150 | $0.0000 | $0.0000 to $0.0000 | 58 | pass |
| Replies cut at max tokens | - | 0 | - | 70 |  |
| Errors | - | 12 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 0 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 2 (x03, x05); router: out of scope 2 (x15, x19).
- Errors: n09 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); n21 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); n40 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); c01 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); c06 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); c07 (no answer within 30 s); c08 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); c10 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); x07 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); x09 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); x10 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); x20 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.)

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 0 | 72,196 | 5,227 |
| `gemini:gemini-3.5-flash-lite` | 48 | 48 | 123,268 | 6,244 |
