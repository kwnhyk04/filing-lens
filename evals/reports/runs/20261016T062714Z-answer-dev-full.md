# Eval: answer, dev, full

2026-10-16T06:27:14+00:00 · golden set v1 (manifest e3ecaba53c6b, today pinned to 2026-10-16) · index 11,263 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `groq:openai/gpt-oss-20b`, primary `gemini:gemini-3.5-flash-lite` (thinking minimal), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -100.0.

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 1.000 to 1.000 | 28 | pass |
| Comparison match (both values) | - | 1.000 | 1.000 to 1.000 | 10 |  |
| Citation precision (judge) | 0.950 | 0.981 | 0.936 to 1.000 | 47 | not measured: judge not calibrated |
| Citation coverage (last reply before removal) | 0.950 | 0.988 | 0.962 to 1.000 | 49 | pass |
| Faithfulness (judge) | 0.920 | 0.937 | 0.873 to 0.986 | 47 | not measured: judge not calibrated |
| Draft citation pass rate | - | 0.946 | 0.865 to 1.000 | 15 |  |
| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 18 | pass |
| False refusal | 0.050 | 0.058 | 0.000 to 0.135 | 52 | fail |
| Router accuracy (route, tickers, years, metric) | - | 0.800 | 0.700 to 0.886 | 70 |  |
| Route accuracy | - | 0.984 | 0.952 to 1.000 | 63 |  |
| Time to first token p50 | 1,000 ms | - | - | 0 | not measured |
| Time to first token p95 | 2,000 ms | - | - | 0 | not measured |
| Full answer p95 | 6,000 ms | - | - | 0 | not measured |
| Input tokens per query | 8,000 | 3,431 | 2,770 to 4,147 | 68 | pass |
| Output tokens per query | 600 | 175 | 141 to 217 | 68 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0011 | $0.0008 to $0.0014 | 68 | pass |
| Cost per query, as billed | $0.0150 | $0.0000 | $0.0000 to $0.0000 | 68 | pass |
| Replies cut at max tokens | - | 0 | - | 70 |  |
| Errors | - | 2 | - | 70 |  |

Notes:

- Latency comes only from questions whose model calls were all live: 0 of 70.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- The judge is not calibrated (make calibrate needs kappa 0.7 or more), so citation precision and faithfulness count as not measured.
- Cost as billed is $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: model: insufficient evidence 3 (x03, x05, x15).
- Errors: x06 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.); x17 (UpstreamError: gemini:gemini-3.5-flash-lite answered 503.)

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `groq:openai/gpt-oss-20b` | 70 | 0 | 72,196 | 5,237 |
| `gemini:gemini-3.5-flash-lite` | 60 | 3 | 173,036 | 7,296 |
| `groq:openai/gpt-oss-120b` | 47 | 0 | 39,263 | 10,197 |
