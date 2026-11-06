# Eval: all, test, full

2026-11-06T00:40:43+00:00 · golden set v3 (manifest 58d844a9b523, today pinned to 2026-10-27) · index 11,375 chunks, BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

Models: router `anthropic:claude-haiku-5-5`, primary `anthropic:claude-haiku-5-5` (thinking disabled, effort low), judge `groq:openai/gpt-oss-120b`; reranker `cross-encoder/ms-marco-TinyBERT-L-2-v2@81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc`, 50 candidates, 512 tokens; refusal gate -3.0.

Code: commit `914692732dd0` with uncommitted changes; source sha256 `986c1cd564e965b8`.

Prompt and schema sha256: router_system `18465e0ad2c4`, router_schema `2992f7981a0c`, answer_system `25e4578a6d3b`, judge_system `633151baefd1`, judge_schema `36dbdb93e034`.

## Retrieval

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.900 | 0.599 | 0.485 to 0.713 | 25 | fail |
| MRR@10 | 0.700 | 0.577 | 0.424 to 0.732 | 25 | inconclusive |
| nDCG@10 | - | 0.485 | 0.384 to 0.589 | 25 |  |
| Judged@10 (labeled share of the top 10) | - | 0.776 | 0.696 to 0.852 | 25 |  |
| Retrieval latency p50 | - | 200 ms | 191 ms to 221 ms | 55 |  |
| Retrieval latency p95 | 250 ms | 306 ms | 268 ms to 446 ms | 55 | not measured: the target is at about 250k chunks |
| Rerank p50 | - | 144 ms | 138 ms to 151 ms | 55 |  |
| Rerank p95 | - | 206 ms | 175 ms to 378 ms | 55 |  |

## Answer

| Metric | Target | Measured | 95% CI | n | Status |
| --- | --- | --- | --- | --- | --- |
| Numeric exact match (0.5%) | 0.920 | 1.000 | 0.758 to 1.000 | 12 | inconclusive |
| Comparison match (both values) | - | 0.875 | 0.529 to 0.978 | 8 |  |
| Citation precision (judge) | 0.950 | 1.000 | 1.000 to 1.000 | 42 | pass |
| Citation coverage (last reply before removal) | 0.950 | 0.945 | 0.891 to 0.987 | 43 | inconclusive |
| Faithfulness (judge) | 0.920 | 0.985 | 0.961 to 1.000 | 42 | pass |
| Draft citation pass rate | - | 0.937 | 0.872 to 0.985 | 26 |  |
| Correct refusal | 0.900 | 1.000 | 0.722 to 1.000 | 10 | inconclusive |
| False refusal | 0.050 | 0.067 | 0.023 to 0.179 | 45 | inconclusive |
| Router accuracy (route, tickers, years, metric) | - | 0.982 | 0.904 to 0.997 | 55 |  |
| Route accuracy | - | 1.000 | 0.930 to 1.000 | 51 |  |
| Time to first token p50 | 1,000 ms | 1,952 ms | 1,927 ms to 2,061 ms | 43 | fail |
| Time to first token p95 | 2,000 ms | 2,499 ms | 2,302 ms to 2,614 ms | 43 | fail |
| Full answer p50 | - | 3,530 ms | 2,707 ms to 3,868 ms | 47 |  |
| Full answer p95 | 6,000 ms | 6,735 ms | 4,544 ms to 7,506 ms | 47 | inconclusive |
| Route p50 | - | 1,013 ms | 955 ms to 1,109 ms | 55 |  |
| Route p95 | - | 1,784 ms | 1,506 ms to 2,360 ms | 55 |  |
| Facts p50 | - | 47 ms | 44 ms to 54 ms | 20 |  |
| Facts p95 | - | 96 ms | 61 ms to 106 ms | 20 |  |
| Retrieve p50 | - | 36 ms | 32 ms to 42 ms | 36 |  |
| Retrieve p95 | - | 63 ms | 51 ms to 74 ms | 36 |  |
| Generate p50 | - | 1,645 ms | 1,292 ms to 2,258 ms | 47 |  |
| Generate p95 | - | 3,165 ms | 2,768 ms to 3,296 ms | 47 |  |
| Regenerate p50 | - | 1,624 ms | 1,468 ms to 2,512 ms | 12 |  |
| Regenerate p95 | - | 3,360 ms | 2,512 ms to 3,360 ms | 12 |  |
| Input tokens per query | 8,000 | 9,057 | 7,563 to 10,571 | 55 | inconclusive |
| Output tokens per query | 600 | 458 | 360 to 567 | 55 | pass |
| Cost per query, paid-equivalent | $0.0150 | $0.0011 | $0.0009 to $0.0013 | 55 | pass |
| Cost per query, as billed | $0.0150 | $0.0011 | $0.0009 to $0.0013 | 55 | pass |
| Replies cut at max tokens | - | 0 | - | 55 |  |
| Errors | - | 0 | - | 55 |  |

Notes:

- Retrieval quality rests on 25 textual questions, so its intervals are very wide. Their passage gold is v2's labels moved to the re-parsed chunks by exact text or word overlap (AI-labeled, cross-checked blind by a second model; no human spot check) (evals/eval-card.md).
- Retrieval latency is measured at 11,375 chunks, in the eval process on this PC's CPU, each question a query in its company scope; the 250 ms target is for about 250k chunks, which this corpus cannot test.
- Latency comes only from questions whose model calls were all live: 55 of 55.
- Citation coverage is measured on the last reply before sentence removal; final answers are 100% covered by construction, since validation drops each sentence without a passing citation.
- Judge metrics count: Cohen's kappa 0.84 against labels by claude, not by the judge.
- Cost as billed is the prepaid credits Claude spends, from each call's usage, and $0 on the free tiers; the paid-equivalent uses the prices in evals/providers.json.
- False refusals by cause: validation: no sentence held up 1 (c19); relevance gate 1 (x21); model: insufficient evidence 1 (x42).

| Model | Calls | Live | Input tokens | Output tokens |
| --- | --- | --- | --- | --- |
| `anthropic:claude-haiku-5-5` | 117 | 117 | 498,133 | 25,200 |
| `groq:openai/gpt-oss-120b` | 42 | 36 | 56,557 | 14,709 |
