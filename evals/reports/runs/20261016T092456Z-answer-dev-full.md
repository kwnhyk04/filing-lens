# Eval: answer, dev, full

2026-10-16T09:24:56+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 0.821 | 0.679 to 0.964 | 28 | fail |
| Comparison match (both values) | - | 0.700 | 0.400 to 1.000 | 10 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 1.000 | 1.000 to 1.000 | 40 | pass |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 0.920 | 0.833 to 1.000 | 12 |  |
| Correct refusal | 0.900 | 0.944 | 0.833 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.115 | 0.038 to 0.212 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.771 | 0.671 to 0.857 | 70 |  |
| Route accuracy | - | 0.968 | 0.921 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | - | - | 0 | not measured |
| Time to first token p95 | 2,000 ms | - | - | 0 | not measured |
| Full answer p95 | 6,000 ms | - | - | 0 | not measured |
| Input tokens per query | 8,000 | 3,325 | 2,604 to 4,108 | 63 | pass |
| Output tokens per query | 600 | 178 | 135 to 234 | 63 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0011 | $0.0007 to $0.0014 | 63 | pass |
| Cost per query, as billed | $0.0150 | $0.0000 | $0.0000 to $0.0000 | 63 | pass |
| Replies cut at max tokens | - | 0 | - | 70 |  |
| Errors | - | 7 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 0 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 4 (n24, c06, x03, x05); router: out of scope 2 (x15, x19).
- Errors: n04 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); n06 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); n17 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); n33 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); c10 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); c14 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); a02 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.)

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 0 | 72,196 | 5,227 |
| `gemini:gemini-3.5-flash-lite` | 51 | 50 | 144,521 | 6,614 |
