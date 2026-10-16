# Eval: answer, dev, full

2026-10-16T05:56:08+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -100.0.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 0.821 | 0.679 to 0.964 | 28 | fail |
| Comparison match (both values) | - | 0.200 | 0.000 to 0.500 | 10 |  |
| Citation precision (judge) | 0.950 | 1.000 | 1.000 to 1.000 | 37 | not measured: judge not calibrated |
| Citation coverage (last reply before removal) | 0.950 | 0.984 | 0.946 to 1.000 | 37 | pass |
| Faithfulness (judge) | 0.920 | 0.952 | 0.889 to 1.000 | 37 | not measured: judge not calibrated |
| Draft citation pass rate | - | 0.970 | 0.906 to 1.000 | 13 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.288 | 0.173 to 0.423 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.671 | 0.557 to 0.786 | 70 |  |
| Route accuracy | - | 1.000 | 1.000 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | 1,796 ms | 1,556 ms to 1,966 ms | 36 | fail |
| Time to first token p95 | 2,000 ms | 2,276 ms | 2,079 ms to 2,353 ms | 36 | fail |
| Full answer p50 | - | 2,173 ms | 1,905 ms to 2,384 ms | 50 |  |
| Full answer p95 | 6,000 ms | 9,288 ms | 3,485 ms to 11,564 ms | 50 | fail |
| Route p50 | - | 594 ms | 579 ms to 610 ms | 69 |  |
| Route p95 | - | 849 ms | 693 ms to 1,072 ms | 69 |  |
| Facts p50 | - | 57 ms | 50 ms to 66 ms | 25 |  |
| Facts p95 | - | 98 ms | 72 ms to 123 ms | 25 |  |
| Retrieve p50 | - | 341 ms | 286 ms to 417 ms | 27 |  |
| Retrieve p95 | - | 593 ms | 419 ms to 761 ms | 27 |  |
| Generate p50 | - | 1,155 ms | 1,082 ms to 1,336 ms | 50 |  |
| Generate p95 | - | 8,426 ms | 2,161 ms to 10,737 ms | 50 |  |
| Regenerate p50 | - | 1,502 ms | 1,502 ms to 2,573 ms | 2 |  |
| Regenerate p95 | - | 2,573 ms | 1,502 ms to 2,573 ms | 2 |  |
| Input tokens per query | 8,000 | 2,974 | 2,313 to 3,674 | 70 | pass |
| Output tokens per query | 600 | 150 | 119 to 192 | 70 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0010 | $0.0007 to $0.0013 | 70 | pass |
| Cost per query, as billed | $0.0150 | $0.0000 | $0.0000 to $0.0000 | 70 | pass |
| Replies cut at max tokens | - | 0 | - | 70 |  |
| Errors | - | 0 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 69 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- The judge is not calibrated (make calibrate needs kappa 0.7 or more), so citation precision and faithfulness count as not measured.
- Cost as billed is $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 69 | 43,776 | 4,821 |
| `gemini:gemini-3.5-flash-lite` | 53 | 53 | 164,436 | 5,690 |
| `groq:openai/gpt-oss-120b` | 37 | 37 | 33,244 | 7,932 |
