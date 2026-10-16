# Eval: answer, dev, full

2026-10-16T09:07:21+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `None`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 1.000 to 1.000 | 28 | pass |
| Comparison match (both values) | - | 0.800 | 0.500 to 1.000 | 10 |  |
| Citation precision (judge) | 0.950 | - | - | 0 | not measured |
| Citation coverage (last reply before removal) | 0.950 | 0.949 | 0.844 to 1.000 | 46 | fail |
| Faithfulness (judge) | 0.920 | - | - | 0 | not measured |
| Draft citation pass rate | - | 1.000 | 1.000 to 1.000 | 13 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.077 | 0.019 to 0.154 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.771 | 0.671 to 0.857 | 70 |  |
| Route accuracy | - | 0.968 | 0.921 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | 4,239 ms | 3,938 ms to 5,467 ms | 46 | fail |
| Time to first token p95 | 2,000 ms | 9,257 ms | 6,715 ms to 17,014 ms | 46 | fail |
| Full answer p50 | - | 4,862 ms | 4,355 ms to 6,023 ms | 53 |  |
| Full answer p95 | 6,000 ms | 15,952 ms | 8,875 ms to 21,355 ms | 53 | fail |
| Route p50 | - | 664 ms | 633 ms to 694 ms | 68 |  |
| Route p95 | - | 947 ms | 856 ms to 1,070 ms | 68 |  |
| Facts p50 | - | 52 ms | 46 ms to 55 ms | 39 |  |
| Facts p95 | - | 151 ms | 89 ms to 267 ms | 39 |  |
| Retrieve p50 | - | 302 ms | 281 ms to 322 ms | 23 |  |
| Retrieve p95 | - | 441 ms | 328 ms to 512 ms | 23 |  |
| Generate p50 | - | 3,802 ms | 3,468 ms to 4,993 ms | 53 |  |
| Generate p95 | - | 14,822 ms | 7,084 ms to 19,770 ms | 53 |  |
| Regenerate p50 | - | 3,990 ms | 3,990 ms to 4,337 ms | 2 |  |
| Regenerate p95 | - | 4,337 ms | 3,990 ms to 4,337 ms | 2 |  |
| Input tokens per query | 8,000 | 3,180 | 2,547 to 3,873 | 68 | pass |
| Output tokens per query | 600 | 176 | 140 to 219 | 68 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0010 | $0.0007 to $0.0013 | 68 | pass |
| Cost per query, as billed | $0.0150 | $0.0000 | $0.0000 to $0.0000 | 68 | pass |
| Replies cut at max tokens | - | 0 | - | 70 |  |
| Errors | - | 2 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 68 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 2 (c06, x03); router: out of scope 2 (x15, x19).
- Errors: c09 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); x05 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.)

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 70 | 72,196 | 5,227 |
| `gemini:gemini-3.5-flash-lite` | 55 | 55 | 146,117 | 6,846 |
