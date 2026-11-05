# Evals

The golden-set evals: commands and flags in `evals/harness.py`'s docstring, official results and how to read them in `evals/eval-card.md`. This file keeps the decisions taken from measured runs.

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
