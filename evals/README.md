# Evals

The golden-set evals: commands and flags in `docs/guide.md` and `evals/harness.py`'s docstring, how the sets were built and how to read the results in `evals/eval-card.md`. This file keeps the decisions taken from measured runs and the official results.

## Measured decisions

### 2026-11-04: Claude Haiku 5.5 stays the answer model, not Claude Sonnet 5.5

- **Question:** does Claude Sonnet 5.5 answer well enough above Claude Haiku 5.5, production's answer model, to pay for it?
- **Runs:** golden set v2's dev split, 100 questions, the router unchanged (Haiku). The three arms' answers were generated live one after another on 2026-11-03 (reports at 16:28, 16:34 and 16:40 UTC), then judged from the reply cache by one judge, Groq gpt-oss-120b. Both Sonnet arms reused Haiku's router replies (`--router-primary`), so all three got the same routes.
  - Haiku as production runs it: thinking off, effort low, 1,052-token cap. Reports `runs/20261103T162805Z` (answers) and `runs/20261103T175043Z` (judged).
  - Sonnet, thinking off (`between_tools`), effort high, 1,052-token cap: `runs/20261103T163401Z`, `runs/20261103T175921Z`.
  - Sonnet, adaptive thinking, effort high, 4,096-token cap: `runs/20261103T164010Z`, `runs/20261104T000849Z`.

| Metric | Target | Haiku | Sonnet, thinking off | Sonnet, adaptive |
| --- | --- | --- | --- | --- |
| Numeric exact match (0.5%), n 40 | 0.92 | 0.950 | 1.000 | 1.000 |
| Citation coverage | 0.95 | 0.987 | 1.000 | 1.000 |
| Citation precision (judge) | 0.95 | 0.985 | 0.984 | 0.994 |
| Faithfulness (judge) | 0.92 | 0.993 | 0.986 | 0.993 |
| Correct refusal, n 25 | 0.90 | 1.000 | 1.000 | 1.000 |
| False refusal, n 75 | 5% or lower | 1.3% | 1.3% | 1.3% |
| Time to first token p50 | 1.0 s | 2.31 s | 3.12 s (estimate) | 2.97 s (estimate) |
| Full answer p95 | 6 s | 6.90 s | 8.52 s (estimate) | 12.61 s (estimate) |
| Answer model's own first token p50 | - | 0.72 s | 1.46 s | 1.05 s |
| Cost per query | $0.015 | $0.0008 | $0.0126 | $0.0131 |

- **Latency:** Haiku's is measured end to end. The Sonnet arms' routes came from the cache, so their end-to-end figures are estimates: Haiku's live route time on the same question plus the arm's measured time after it. They lean slightly slow, since a live route overlaps the early search (about 40 ms). The answer model's own first token is measured in all three.
- **Findings:**
  - Quality is equal. Paired against Haiku question by question (`--compare`), neither Sonnet arm differs in citation precision or faithfulness: every 95% interval spans 0. Refusals are the same in all three.
  - The numeric gap was rounding only. Haiku's two misses, n24 and n39, cite the right fact, fiscal year and unit, and round to one decimal in billions: $4.1 billion for 4,121,000,000 (0.51% off) and $6.7 billion for 6,747,000,000 (0.70%). Validation passes them under the rounding rule (`validate.rounded`); exact match counts within 0.5% only.
  - Sonnet costs about 16 times as much per question, and it is slower: its own first token comes 0.74 s (thinking off) and 0.33 s (adaptive) later at p50, and adaptive thinking's p95 is 9.6 s against Haiku's 1.1 s.
- **Decision (user, 2026-11-04):** Haiku stays. The rounding is fixed in the answer prompt instead: rule 4 asks for at least four significant digits (`docs/prompt-log.md`).
- **Spent:** Claude $2.60 of credits; the judge 232,185 Groq tokens over two UTC days.
- **The fix, measured (2026-11-04):** Haiku again on dev, fully live with the new rule 4 (`runs/20261104T091822Z`, judged `runs/20261104T092734Z`).
  - Numeric exact match 1.000, Sonnet's level. Of the 40 figures, 17 are stated as the source states them and 23 rounded within 0.5%, none outside (before: 7, 31 and 2).
  - Paired against the earlier Haiku run, no metric is worse beyond its 95% interval; citation precision rose (0.995, +0.016).
  - Claude $0.09; the judge 85,462 tokens.

### 2026-11-05: rule 4 held on the test split, and quality did not fall

- **Question:** does the rounding fix hold on questions it was not written from, and did anything get worse?
- **Run:** golden set v2's test split, 55 questions, Claude Haiku 5.5 routing and answering as production runs it, judged in the same pass by Groq gpt-oss-120b: `evals/reports/2026-11-05-claude-first` (07:07 to 07:15 UTC, `--claude-first --tag=rule4-1105 --judge-budget=180000 --max-usd=0.5`). Against `evals/reports/2026-10-31-claude-first`, the same questions on the earlier prompt (16:01 UTC). Nothing was tuned on this set: rule 4 and n40's fix came from dev.

| Metric | Target | 2026-10-31 | 2026-11-05 | Paired difference (95% CI) |
| --- | --- | --- | --- | --- |
| Numeric exact match (0.5%), n 12 | 0.92 | 1.000 | 1.000 | +0.000 |
| Comparison match, n 8 | - | 1.000 | 1.000 | - |
| Citation coverage | 0.95 | 0.950 | 0.950 | - |
| Citation precision (judge) | 0.95 | 0.980 (n 42) | 0.993 (n 43) | +0.013 (-0.014 to +0.040) |
| Faithfulness (judge) | 0.92 | 0.968 (n 42) | 0.976 (n 43) | +0.008 (-0.034 to +0.051) |
| Correct refusal, n 10 | 0.90 | 1.000 | 1.000 | - |
| False refusal, n 45 | 5% or lower | 4.4% (x21, x42) | 4.4% (x21, x42) | - |
| Router accuracy | - | 0.982 | 0.982 | - |
| Time to first token p50 | 1.0 s | 2.11 s | 2.41 s | - |
| Time to first token p95 | 2.0 s | 5.06 s | 3.03 s | - |
| Full answer p95 | 6 s | 7.07 s | 7.29 s | - |
| Answer model's own first token p50 | - | 0.75 s | 0.83 s | +0.07 s (+0.01 to +0.24) |
| Answer model's own first token p95 | - | 0.93 s | 1.71 s | +0.78 s (+0.26 to +1.23) |
| Answer model's own full reply p95 | - | 3.10 s | 3.51 s | +0.41 s (+0.08 to +0.86) |
| Cost per query | $0.015 | $0.0012 | $0.0012 | - |

- **Rule 4 held.**
  - The test split has one question of n24's kind, where one decimal in billions falls outside 0.5%: n49, 6,835,000,000. Haiku wrote $6.8 billion on 2026-10-31, and passed only because the same answer repeated the full figure. It now writes $6.835 billion.
  - Of the 12 figures, 5 are stated as the source states them and 7 rounded within 0.5%, none outside (before: 3, 9 and 0). Every rounded figure keeps at least four significant digits; before, 8 of the 9 did not. The counts come from the same method that gives dev's 17, 23 and 0.
  - A figure quoted from a passage stays as the passage has it, as rule 4 allows ($15.5 billion in c20, $24.1 billion in x22).
- **Worse, measured:** the answer model's own time. Its first token p50 and p95 and its full reply p95 are slower beyond their 95% intervals, and end to end time to first token p50 is 0.30 s slower. The prompt is not longer: input tokens per query fell from 9,534 to 9,408. The runs were at different hours of the day, and the PC had started its production stack minutes earlier; the cause is not confirmed. Time to first token p95 fell from 5.06 s with 2026-10-31's retrieve-stage outlier gone (retrieve p95 3.56 s, now 65 ms).
- **Worse, by reading the answers:**
  - x40 (Pfizer on Seagen) kept 1 of 5 sentences, the acquisition's tax liabilities, where 2026-10-31 gave a four-sentence answer. The judge scores that sentence 1 of 1, so no metric shows it. The regeneration's quotes joined text with "...", which is not word for word; the cause of the removals is not confirmed.
  - x37 (Lilly's manufacturing) added "The filing does not provide further detail" with a citation: precision and faithfulness 1 of 2.
  - Per-share figures changed style: n44 and n51 now read "3.04 USD" and "51.32 USD", from the fact's own quote, not "$3.04". Both are right. The amount check could not read that form when this run was made; it has read it since the review fixes of the same day, and the saved replies replay unchanged (`docs/memory.md`, 2026-11-05).
- **Spent:** Claude $0.065 (120 live calls, 544,060 tokens); the judge 71,019 tokens (42 live calls, 12 per-minute 429s waited out, none daily). About as approved: $0.07 and 72k.
- **Sonnet:** measured on dev only, above, never on this split, so its figures do not compare with this table. Its decision stands: on dev, quality equal to Haiku's at about 16 times the cost.

## Evaluation

Golden set v2 (`evals/golden/v2`, frozen 2026-10-31) is the set in use. It holds 155 questions: v1's 100, all in dev now, and 55 new test questions, hashed before any fix of the answer-quality round. Its corpus is the re-parsed dev database (11,257 chunks, release asset `corpus-v2`). How it was built and labeled is in `evals/eval-card.md` (Golden set v2).

- Textual gold is AI-labeled, cross-checked blind by a second model; no human spot check in v2.
- Claude labeled the 591 passages that carry no v1 label, under v1's rule plus the qualifier rule: a passage is gold only if it answers the question as asked, qualifier included. The other 538 keep v1's final label (below).
- **v2's gold mixes two labelling standards.** About 10 of the 150 carried gold passages would fail the strict qualifier rule (a read-only check, 2026-10-31). They were left as they are, so Claude's 168 gold follow the qualifier rule and the 150 carried follow v1's looser rule.
- The cross-check: the judge model (gpt-oss-120b, another model family) labeled a fixed-seed sample of 50 of Claude's labels without seeing them. Agreement 90.0%, Cohen's kappa 0.80 (95% CI 0.62 to 0.96). Two models agreeing does not show the labels are right.
- Its labels only measure agreement: on the 5 disagreements Claude's labels stand.

### Official results, golden v2: test split

Two runs of the same 55 test questions, both judged by gpt-oss-120b. Nothing was tuned on this set.
- **Claude first (the headline):** Claude Haiku 5.5 routes and answers, as the live site runs while its credits last (`evals/reports/2026-11-05-claude-first`, 07:15 UTC). Its comparison with the run of 2026-10-31 is under Measured decisions, above.
- **Free models only:** Gemini 3.5 Flash-Lite answers and gpt-oss-20b routes. The site falls back to them when Claude stops, and CI's test floors come from this run (`evals/reports/2026-10-31`, 15:31 UTC). It predates answer rule 4's four significant digits.
- Both ran on uncommitted branches; each report pins its source sha256.

| Metric | Target | Claude first (headline) | Free models only |
| --- | --- | --- | --- |
| Retrieval recall@10 (n 25) | 0.90 | 0.596 | 0.596 (the same search) |
| MRR@10 | 0.70 | 0.628 | 0.628 |
| Numeric exact match (n 12) | 0.92 | 1.000 | 1.000 |
| Citation precision (judge) | 0.95 | 0.993 (n 43) | 1.000 (n 37) |
| Citation coverage | 0.95 | 0.950 | 1.000 |
| Faithfulness (judge) | 0.92 | 0.976 | 0.990 |
| Correct refusal (n 10) | 0.90 | 1.000 | 1.000 |
| False refusal (n 45) | 5% or lower | 4.4% (x21, x42) | 13.3% (x21, x25, x26, x35, x40, x42) |
| Router accuracy (route, tickers, years, metric) | - | 0.982 | 0.564 |
| Time to first token p50 / p95 | 1.0 s / 2.0 s | 2.41 s / 3.03 s | 1.47 s / 2.12 s |
| Full answer latency p95 | 6 s | 7.29 s | 3.98 s |
| Tokens per query, in / out | 8,000 / 600 | 9,408 / 484 | 5,715 / 321 |
| Cost per query, as billed | $0.015 | $0.0012 in credits | $0 |

- **Claude first** misses only speed and input tokens. It routes in 1.32 s at p50 against Groq's 0.66 s, its first draft takes longer (2.03 s against 1.45 s at p50), and it redrafts more often (draft citation pass rate 0.921 against 0.972). Its routing prompt is about twice Groq's in tokens.
- **Free models only** miss false refusal (13.3%) and time to first token p50. Their router reads 56% of questions fully right, against Claude's 98%.
- Recall@10 (0.596) misses for both: the search is the same, and its gold labels are Claude's (above).
- Golden v1's results below are history.

Golden set v1 (`evals/golden/v1`, frozen 2026-10-16) holds 100 questions over the 30 companies' latest 10-Ks. How it was built and labeled is in `evals/eval-card.md`.

- Textual gold is AI-labeled, spot-checked by a non-expert. Claude labeled every pooled passage.
- The human check was a fast spot-check by a non-expert, which cannot validate the labels on its own. The passage labels are not human-verified.
- Blind agreement on 79 passages was 49.4%, Cohen's kappa 0.10 (95% CI -0.07 to 0.26), which is not distinguishable from chance.
- The human then made the final call on the 40 disagreements and kept Claude's label on 37. That review showed Claude's reason, so it was not independent.
- Later, after reading the passage text, the human corrected 2 of their 3 overrides back to not gold. The final key now differs from Claude's labels on one passage.
- The judge behind citation precision and faithfulness (gpt-oss-120b) is calibrated against labels by Claude, a different and stronger model than the judge, not by a human. On 29 sentences it agreed 93.1%, Cohen's kappa 0.84 (95% CI 0.59 to 1.00), so those metrics count. Every negative in that sample was constructed. A follow-up spot check on natural sentences that fail the validator (2026-10-17) found the judge failing 3 of the 4 that Claude labeled not supported.
- While a golden set is in use (v2 now), don't run `make seed-real` or queue ingest jobs (see `make seed-real` in `docs/guide.md`).

### Golden v1's official results: test split, 2026-10-17 (history)

The run covers 30 questions on the free tiers. Gemini 3.5 Flash-Lite answers, gpt-oss-20b routes and gpt-oss-120b judges (report `evals/reports/2026-10-17.md`). The test floors in `evals/thresholds.json` come from this run. The dev floors that CI gates come from the dev reports of 2026-10-17. Retrieval accuracy floors sit one question's share below the measured value, because retrieval calls no model and repeats exactly (`evals/eval-card.md`).

The Haiku column is a comparison with Claude Haiku 5.5 pinned as the answer model: thinking off, judge on, nothing tuned (`evals/reports/runs/20261017T084716Z-answer-test-full.md`).
- It reuses the exact router replies of Gemini's run (`--router-primary=gemini:gemini-3.5-flash-lite --primary-tag=fair`), so both models answer identical inputs.
- It replaces an earlier Haiku run (`20261017T082950Z`) that asked the router again. The router then routed x13, x14 and x18 as textual, so that run's refusal figures differed by the router, not the answer model.
- With every router reply reused, no question had all its calls live. So Haiku's end-to-end latency is not measured, and its latency cells compare the answer models' own calls, paired by question.

| Metric | Target | Gemini (official), 95% CI | n | Status | Haiku (comparison), 95% CI |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.90 | 0.583 (0.314 to 0.816) | 6 | fail | same retrieval |
| MRR@10 | 0.70 | 0.833 (0.500 to 1.000) | 6 | pass | same retrieval |
| Retrieval latency p95 | 250 ms at about 250k chunks | 336 ms (275 to 364) at 11,263 chunks | 30 | not measured | same retrieval |
| Numeric exact match | 0.92 | 1.000 (1.000 to 1.000) | 12 | pass | 1.000 (1.000 to 1.000) |
| Citation precision | 0.95 | 0.944 (0.833 to 1.000) | 20 | fail | 0.958 (0.880 to 1.000) |
| Citation coverage | 0.95 | 0.971 (0.914 to 1.000) | 20 | pass | 1.000 (1.000 to 1.000) |
| Faithfulness | 0.92 | 0.970 (0.906 to 1.000) | 20 | pass | 0.944 (0.857 to 1.000) |
| Correct refusal | 0.90 | 1.000 (1.000 to 1.000) | 7 | pass | 1.000 (1.000 to 1.000) |
| False refusal | 5% or lower | 13.0% (0.0 to 26.1%) | 23 | fail | 13.0% (0.0 to 26.1%), the same 3 router calls |
| Time to first token p50 | 1.0 s | 1.55 s (1.45 to 1.62) | 19 | fail | not measured end to end; own first token 0.72 s against Gemini's 0.85 s, paired (difference −0.13 s, CI −0.18 to −0.07), n 22 |
| Time to first token p95 | 2.0 s | 1.84 s (1.67 to 1.84) | 19 | pass | not measured end to end; own first token 0.94 s against 1.13 s |
| Full answer latency p95 | 6 s | 2.15 s (1.97 to 4.89) | 21 | pass | not measured end to end; own reply 2.36 s against 2.10 s |
| Tokens per query, in / out | 8,000 / 600 | 3,188 (2,196 to 4,236) / 161 (119 to 221) | 30 | pass | 4,853 / 278 |
| Cost per query, paid-equivalent | $0.015 | $0.0010 ($0.0006 to $0.0014) | 30 | pass | $0.0006 ($0.0004 to $0.0009) |
| Cost per query, as billed | $0.015 | $0 | 30 | pass | $0.0005 in credits ($0.0003 to $0.0008) |
| Ingestion | 500 filings in under 2 hours | - | - | not measured | - |

Every miss, explained:

- **False refusal 13.0%:**
  - All three are the router (gpt-oss-20b) sending a textual question out of scope with no ticker: x13 (UnitedHealth's businesses), x14 (Pfizer's patent expiries) and x18 (the Grasberg mine in September 2025).
  - Retrieval ranked their gold first, so a correct route would likely have answered.
  - Asked again in the first Haiku run, the same router routed all three as textual, so it is not deterministic. That is why the Haiku comparison was rerun on Gemini's router replies.
- **Citation precision 0.944:** one sentence, 34 of 36 pairs pass.
  - c02 concludes "Therefore, Alphabet's total revenue was higher in fiscal 2025 [1][2]" from two cited facts.
  - The sources state both figures but not the comparison, so the judge rates it "partly" under the written criterion, as in calibration.
- **Recall@10 0.583:** it rests on 6 textual questions, so one question moves it by about 0.17, and the interval runs from 0.31 to 0.82.
  - x12 (Lilly's growth drivers) found none of its 3 gold passages in the top 10.
  - The passage gold is AI-labeled, spot-checked by a non-expert.
- **Time to first token p50 1.55 s:**
  - The stages run in sequence: the router (p50 0.62 s), then facts or retrieval, then Gemini's first token.
  - Gemini's own first token drifts with the hour on the free tier: on the same dev questions on 2026-10-16, p50 0.97 s at 05:56 UTC and 3.37 s at 09:00 UTC. This run's p95 pass reflects a fast hour.
  - Starting the search while the router runs saves a median 268 ms where the router agrees (dev).
  - On the same routes, Haiku's own first token was 0.13 s faster at p50 (95% CI 0.07 to 0.18 s). The answer model is a small part of the miss.
- **Not measured:** retrieval latency at the 250k-chunk scale, and ingestion of 500 filings.

Known weaknesses, with v2 ideas (nothing here is tuned on test results):

- **Router out-of-scope calls:** in code, a question that names a tracked company (`router.guess`) is never out of scope; or the router prompt gets in-scope examples. Measure either on a new dev set.
- **Router missing tickers:** t10 (a time trap) and a03 (an absent figure) were refused as "nothing relevant enough", because the router gave no ticker. Fill a single named company from `router.guess` when the router gives none.
- **Comparison conclusions:** check "higher" or "lower" against the cited fact values in code, like a derived-number check, so a correct conclusion can count as supported. Haiku's c12 conclusion ("decreased") got the same "partly".
- **Recall:** a v2 golden set with 20 or more textual test questions and human-verified passage labels. On dev, the MiniLM-L-6 reranker showed headroom at about 14 times the rerank time.
- **Time to first token:** skip the router call when code can route, or start the answer model on the early search. Measure across several hours, or on a paid tier with steadier latency.
- **Fact headings:** a year-end balance taken from the next year's 10-Q carries that 10-Q's period ("fiscal 2025 Q2"). Haiku refused two dev questions over it (n17, n24), and on test it hedged n28 (Prologis' liabilities, labeled "fiscal 2025 Q1"), which the judge rated "partly". Label instant facts by their date and the period asked for.
- **Judge:** the follow-up check passed one natural unsupported sentence (t07). Calibrate on a larger, human-labeled set of natural negatives.
- **Scale:** retrieval latency at about 250k chunks (`make seed-fake`), and ingestion timing at 500 filings.
