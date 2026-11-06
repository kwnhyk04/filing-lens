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

### 2026-11-06: the stricter amount check changed no verdict, and the re-parsed corpus no cited quote

- **Question:** what did the stricter amount check and the parser fix change, and which one changed what?
- **Runs:** golden set v3's test split, 55 questions on `corpus-v3`, one source sha256 (`986c1cd564e965b8`), judged by Groq gpt-oss-120b.
  - Claude first: `evals/reports/2026-11-06-claude-first` (00:40 UTC, `--claude-first --tag=v3-1106 --judge-budget=180000 --max-usd=0.10`), against `evals/reports/2026-11-05-claude-first` (golden v2, `corpus-v2`, 07:15 UTC). All five prompt and schema hashes match, so what differs is the code, the corpus, the labels and the model's own randomness.
  - Free models only: `evals/reports/2026-11-06` (00:41 to 01:12 UTC, `--tag=v3-1106`), against `evals/reports/2026-10-31`. No free run was made on 2026-11-05, so this pair also spans answer rule 4's prompt change. A Groq 429 stopped its first pass at 34 of 55; the rest resumed from the cache on a second Groq account's key, with the same judge model.

Claude first:

| Metric | Target | 2026-11-05 | 2026-11-06 | Paired difference (95% CI) |
| --- | --- | --- | --- | --- |
| Numeric exact match (0.5%), n 12 | 0.92 | 1.000 | 1.000 | +0.000 |
| Comparison match, n 8 | - | 1.000 | 0.875 | - |
| Citation coverage | 0.95 | 0.950 (n 43) | 0.945 (n 43) | - |
| Citation precision (judge) | 0.95 | 0.993 (n 43) | 1.000 (n 42) | +0.007 (0.000 to +0.023), n 42 |
| Faithfulness (judge) | 0.92 | 0.976 (n 43) | 0.985 (n 42) | +0.009 (-0.001 to +0.028), n 42 |
| Correct refusal, n 10 | 0.90 | 1.000 | 1.000 | - |
| False refusal, n 45 | 5% or lower | 4.4% (x21, x42) | 6.7% (c19, x21, x42) | - |
| Router accuracy, n 55 | - | 0.982 | 0.982 | - |
| Retrieval recall@10, n 25 | 0.90 | 0.596 | 0.599 | +0.003 (-0.048 to +0.049), labels differ |
| MRR@10, n 25 | 0.70 | 0.628 | 0.577 | -0.051 (-0.143 to +0.029), labels differ |
| Time to first token p50 | 1.0 s | 2.41 s (n 43) | 1.95 s (n 43) | - |
| Time to first token p95 | 2.0 s | 3.03 s (n 43) | 2.50 s (n 43) | - |
| Full answer p95 | 6 s | 7.29 s (n 47) | 6.74 s (n 47) | - |
| Answer model's own first token p50 | - | 0.825 s | 0.688 s | -0.138 s (-0.293 to -0.074), n 47 |
| Answer model's own first token p95 | - | 1.707 s | 0.895 s | -0.812 s (-1.301 to -0.348), n 47 |
| Answer model's own full reply p95 | - | 3.512 s | 3.162 s | -0.349 s (-0.798 to +0.111), n 47 |
| Cost per query, n 55 | $0.015 | $0.0012 | $0.0011 | - |

Free models only:

| Metric | Target | 2026-10-31 | 2026-11-06 | Paired difference (95% CI) |
| --- | --- | --- | --- | --- |
| Numeric exact match (0.5%), n 12 | 0.92 | 1.000 | 1.000 | +0.000 |
| Comparison match, n 8 | - | 1.000 | 1.000 | - |
| Citation coverage | 0.95 | 1.000 (n 39) | 0.991 (n 39) | - |
| Citation precision (judge) | 0.95 | 1.000 (n 37) | 0.992 (n 39) | +0.000 on the 36 judged in both |
| Faithfulness (judge) | 0.92 | 0.990 (n 37) | 0.990 (n 39) | +0.000 (-0.030 to +0.029), n 36 |
| Correct refusal, n 10 | 0.90 | 1.000 | 1.000 | - |
| False refusal, n 45 | 5% or lower | 13.3% (x21, x25, x26, x35, x40, x42) | 13.3% (x21, x25, x26, x36, x40, x42) | - |
| Router accuracy, n 55 | - | 0.564 | 0.509 | - |
| Time to first token p50 | 1.0 s | 1.47 s (n 38) | 1.97 s (n 37) | - |
| Time to first token p95 | 2.0 s | 2.12 s (n 38) | 8.10 s (n 37) | - |
| Full answer p95 | 6 s | 3.98 s (n 44) | 9.09 s (n 42) | - |
| Answer model's own first token p50 | - | 0.817 s | 1.254 s | +0.437 s (+0.237 to +0.986), n 41 |
| Answer model's own first token p95 | - | 1.199 s | 6.075 s | +4.876 s (+3.030 to +6.035), n 41 |
| Answer model's own full reply p95 | - | 2.508 s | 7.811 s | +5.304 s (+2.033 to +7.678), n 41 |

- **The stricter amount check changed nothing here.** Every distinct draft of both 2026-11-06 runs that tried to answer went through the check as it stood before and as it stands now, offline: 346 sentences in 106 drafts. 280 pass both, 121 of them holding amounts; 66 fail both; 0 differ. The replay matches the runs: on 80 of 82 first drafts it agrees with whether the run rewrote, and on the other 2 the run dropped a citation instead. So on this split the check neither caught a wrong figure nor dropped a right one. Its case rests on its tests, not on these runs.
- **The corpus gave the models different text, and they quoted none of the difference.** 30 of the 55 questions saw at least one different passage. Yet all 130 quotes cited on 2026-11-06 are also in `corpus-v2`, and all 138 cited before are also in `corpus-v3`, read the way the quote check reads them and with table separators ignored. So no figure in these answers depends on the digits the parser restored.
- **Redrafts cannot be split between the corpus and chance.** Under Claude first, drafts rewritten fell from 15 to 12 and answers with sentences removed from 11 to 7. Of the 17 drafted questions with unchanged passages, 3 changed either way (c23, n42, x25), all for the better. Of the 30 with changed passages, 9 changed: 4 better, 5 worse. Those samples are too small to separate the corpus from the model's randomness.
- **c19 is the one new false refusal, and the old check refuses it too.** Every sentence gets the same verdict from both checks. On both days the first draft fails the sentence stating the difference: "it compares figures without stating those of [F1], [F2]", a rule from #35. On 2026-11-05 the rewrite kept the first sentence, which holds both figures. On 2026-11-06 Haiku split it into four sentences: one cites nothing, two cite K1 with one fact (a rule from #36), and the last compares again. None held, so a right answer was refused, and comparison match fell to 7 of 8. Neither draft of 2026-11-06 cites a passage, and 1 of the question's 12 passages changed.
- **The free models' false refusals swapped one question.** x35 (10 of 12 passages changed) now answers; x36 (2 of 12 changed) now refuses as insufficient evidence. x25's refusal moved from the relevance gate to the model. The answer prompt also changed between these runs, so the cause is not confirmed. Router accuracy fell by 3 of 55 under the same router prompt, with 11 questions flipping both ways.
- **Latency moved with the models' own time, not with either change.**
  - Claude first was faster: its own first token beyond the 95% interval, and routing p50 from 1.32 s to 1.01 s. The runs were at different hours.
  - The free models were slower. Gemini's own first token took over 3 s on 12 of 43 calls, against none on 2026-10-31 (slowest 1.36 s), in two bursts, 00:41 to 00:43 and at 01:10 UTC. Nine of the 12 were numeric questions with a prompt of about 420 tokens and no passage, so neither the corpus nor the check is involved. The cause is not confirmed.
  - The latency floors set from this run are loose for that reason. CI does not gate latency.
- **Retrieval does not compare yet.** recall@10 and MRR@10 both stay within their paired intervals, but v3 leaves 33 of this split's gold passages out until a person reviews them, and judged@10 fell from 1.000 to 0.776, since the new chunks a search finds carry no label yet.
- **Spent:** Claude about $0.06 (117 live calls); the judge 125,158 tokens of the 180,000 cap, 71,266 for Claude first and 53,892 for the free models. The dev ci run behind the floors took 32,361 gpt-oss-20b tokens, past the 28K estimate, and 21 Gemini requests, 2 of them c06's retry after a Gemini 503.

## Evaluation

Golden set v3 (`evals/golden/v3`, 2026-11-06) is the set in use: golden v2's 155 questions, byte for byte, with v2's labels moved by `evals/carry.py` to the re-parsed corpus `corpus-v3` (11,375 chunks). No label was made new, and v2 stays as it was.

- **Moved:** of v2's 1,129 labels, 678 kept their exact text (201 gold) and 243 moved to the one chunk holding at least 90% of their words, 25 points ahead of any other (63 gold). `remap-report.md` lists each with its score.
- **Waiting for a person:** 208 passages no chunk holds confidently (54 gold, 33 of them on test), in `review.md`. They keep their v2 label there and stay out of the metrics. Every question keeps at least one gold passage. So v3's recall is measured on 264 of 318 gold, and its numbers do not compare with v2's until the review is done.
- **Offline run, no model call (2026-11-06):** retrieval, dev, recall@10 0.584 (0.428 to 0.734, n 20), MRR@10 0.692 (0.508 to 0.867), judged@10 0.865; test, recall@10 0.599 (0.485 to 0.713, n 25), MRR@10 0.577 (0.424 to 0.732), judged@10 0.776. Judged@10 was 1.000 on v2: the new chunks a search finds carry no label yet.
- The official results below ran on v3 and `corpus-v3` on 2026-11-06. Its floors come from the free models' runs of that day (`evals/eval-card.md`).

Golden set v2 (`evals/golden/v2`, frozen 2026-10-31) holds 155 questions: v1's 100, all in dev now, and 55 new test questions, hashed before any fix of the answer-quality round. Its corpus is the re-parsed dev database (11,257 chunks, release asset `corpus-v2`). How it was built and labeled is in `evals/eval-card.md` (Golden set v2).

- Textual gold is AI-labeled, cross-checked blind by a second model; no human spot check in v2.
- Claude labeled the 591 passages that carry no v1 label, under v1's rule plus the qualifier rule: a passage is gold only if it answers the question as asked, qualifier included. The other 538 keep v1's final label (below).
- **v2's gold mixes two labelling standards.** About 10 of the 150 carried gold passages would fail the strict qualifier rule (a read-only check, 2026-10-31). They were left as they are, so Claude's 168 gold follow the qualifier rule and the 150 carried follow v1's looser rule.
- The cross-check: the judge model (gpt-oss-120b, another model family) labeled a fixed-seed sample of 50 of Claude's labels without seeing them. Agreement 90.0%, Cohen's kappa 0.80 (95% CI 0.62 to 0.96). Two models agreeing does not show the labels are right.
- Its labels only measure agreement: on the 5 disagreements Claude's labels stand.

### The about category

`evals/golden/about.jsonl` holds 25 questions outside the frozen set: 17 about FilingLens itself (the app, who made it, the collection, loosely worded or not, a company it holds, two it does not) and 8 near-misses that must go to the filings or be refused. `make eval-about` runs them through the router and the answer pipeline with no answer model, and checks where each landed and the figures it should state. It has no floors and CI skips it.

Golden v2's files, manifest and floors are unchanged. A test pins that none of its 155 questions reaches the about routes, so each sends the router the same prompt and schema as before and its cached reply still answers. The router's extra prompt text quotes several of these questions, so they are not held out.

Run live on 2026-11-05 (`evals/reports/runs/20261105T162342Z-about` and `20261105T162355Z-about`, replayed from the live calls of `20261105T162150Z-about` and `20261105T162255Z-about`):

| Router | Route right | Landed right | Figures said | Tokens | Cost |
| --- | --- | --- | --- | --- | --- |
| Groq gpt-oss-20b | 15 of 15 | 15 of 15 | 10 of 10 | 19,963 | free tier |
| Claude Haiku 5.5 | 15 of 15 | 15 of 15 | 10 of 10 | 35,396 | $0.00386 |

Run live again on 2026-11-06 with who made it and the loosely worded collection questions, b16 to b25 (`evals/reports/runs/20261106T033142Z-about` and `20261106T033227Z-about`, `--tag=about-1106`). Each took one router call, no second look:

| Router | Route right | Landed right | Figures said | Tokens | Cost |
| --- | --- | --- | --- | --- | --- |
| Groq gpt-oss-20b | 25 of 25 | 25 of 25 | 17 of 17 | 33,977 | free tier |
| Claude Haiku 5.5 | 25 of 25 | 25 of 25 | 17 of 17 | 60,004 | $0.0065 |

b12, "What can you tell me about Tesla's risk factors?", routes right but gets no answer: the search runs, and its best rerank score, -4.82, falls under the relevance gate's -3.0. It counts as landing on the filings, and this work changed neither the search nor the gate.

### What the official results measured

Read these before the table below (the architecture review of 2026-11-06, E1 to E4).

- **Corpus:** both runs used `corpus-v3` (11,375 chunks) in the dev database, with the parser fix of 2026-11-06, which restored 8,950 digits lost from table cells across all 30 filings and changed nearly every chunk id. Production has served the same corpus since its re-parse that day (`docs/deploy.md`, steps 64 to 70).
- **Code:** both runs measured the same source, sha256 `986c1cd564e965b8`, with the review fixes of 2026-11-05 and the amount check of 2026-11-06. Each report's "uncommitted changes" means nobody can check out exactly what ran; its source sha256 pins it instead.
- **Models:** the fallback models never answered a measured question, since evals turn fallbacks off, and the degraded search path was never measured, since evals give the reranker 60 s and stop if a search degrades.
- **Numeric and comparison gold** was built with `get_financial_fact` and the router's `METRICS`, the function and map that answer in production, and pairs where the lookup was known to be wrong were left out. Exact match shows the model repeats the figure the lookup returned, not that the lookup is right. The scorer compares absolute values, so it does not see a wrong sign.
- **Passage gold and the judge:** Claude labeled the passages, Claude's labels calibrated the judge, and Claude Haiku wrote the Claude-first answers. A second model cross-checked 50 passages (kappa 0.80), and Claude's label stood on all five disagreements. v3 moved those labels to the re-parsed chunks, and 33 of this split's gold passages wait in `review.md`. No human checked v2 or v3. A sample of 20 gold answers for a hand check was drawn on 2026-11-06.
- **Test split:** no prompt was tuned on it. Its answers were read by hand on 2026-11-05, and the amount parsing that both validation and the exact-match scorer use changed 90 minutes after that day's Claude-first run, before these runs. Treat it as seen.
- **Pass or fail:** the harness prints "inconclusive" unless the whole 95% interval clears or misses the target; reports saved before 2026-11-06 print "pass" on the point estimate. False refusal for Claude first is 3 of 45, and its interval straddles 5%.

### Official results, golden v3: test split

Two runs of the same 55 test questions on the same code, both judged by gpt-oss-120b. Their comparison with the runs before is under Measured decisions, above.
- **Claude first (the headline):** Claude Haiku 5.5 routes and answers, as the live site runs while its credits last (`evals/reports/2026-11-06-claude-first`, 00:40 UTC).
- **Free models only:** Gemini 3.5 Flash-Lite answers and gpt-oss-20b routes. The site falls back to them when Claude stops, and v3's test floors come from this run (`evals/reports/2026-11-06`, 01:12 UTC).

| Metric | Target | Claude first (headline), 95% CI | Status | Free models only, 95% CI | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 (n 25) | 0.90 | 0.599 (0.485 to 0.713) | fail | 0.599, the same search | fail |
| MRR@10 (n 25) | 0.70 | 0.577 (0.424 to 0.732) | inconclusive | 0.577, the same search | inconclusive |
| Numeric exact match (n 12) | 0.92 | 1.000 (0.758 to 1.000) | inconclusive | 1.000 (0.758 to 1.000) | inconclusive |
| Comparison match (n 8) | - | 0.875 (0.529 to 0.978) | - | 1.000 (0.676 to 1.000) | - |
| Citation precision (judge) | 0.95 | 1.000 (1.000 to 1.000, n 42) | pass | 0.992 (0.974 to 1.000, n 39) | pass |
| Citation coverage | 0.95 | 0.945 (0.891 to 0.987, n 43) | inconclusive | 0.991 (0.971 to 1.000, n 39) | pass |
| Faithfulness (judge) | 0.92 | 0.985 (0.961 to 1.000, n 42) | pass | 0.990 (0.968 to 1.000, n 39) | pass |
| Correct refusal (n 10) | 0.90 | 1.000 (0.722 to 1.000) | inconclusive | 1.000 (0.722 to 1.000) | inconclusive |
| False refusal (n 45) | 5% or lower | 6.7% (2.3% to 17.9%; c19, x21, x42) | inconclusive | 13.3% (6.3% to 26.2%; x21, x25, x26, x36, x40, x42) | fail |
| Router accuracy (route, tickers, years, metric, n 55) | - | 0.982 (0.904 to 0.997) | - | 0.509 (0.381 to 0.636) | - |
| Time to first token p50 | 1.0 s | 1.95 s (1.93 to 2.06, n 43) | fail | 1.97 s (1.84 to 3.46, n 37) | fail |
| Time to first token p95 | 2.0 s | 2.50 s (2.30 to 2.61, n 43) | fail | 8.10 s (6.83 to 10.93, n 37) | fail |
| Full answer latency p95 | 6 s | 6.74 s (4.54 to 7.51, n 47) | inconclusive | 9.09 s (6.96 to 11.12, n 42) | fail |
| Tokens per query, in | 8,000 | 9,057 (7,563 to 10,571, n 55) | inconclusive | 5,746 (4,618 to 6,931, n 55) | pass |
| Tokens per query, out | 600 | 458 (360 to 567, n 55) | pass | 340 (270 to 415, n 55) | pass |
| Cost per query, as billed | $0.015 | $0.0011 in credits ($0.0009 to $0.0013, n 55) | pass | $0 | pass |

- **Claude first:** the whole interval misses on recall and on first token. Numeric match, refusals, coverage, MRR, full answer latency and input tokens are too thin to call.
- **Free models only:** false refusal (13.3%) and all three latency rows miss across their whole interval, the latency on Gemini's slow bursts (above). Their router reads 51% of questions fully right, against Claude's 98%.
- Recall@10 (0.599) misses for both: the search is the same, its gold labels are Claude's, and 33 of them wait for a person (above).
- Golden v2's results below are history.

### Golden v2's official results: test split (history)

Two runs of the same 55 test questions on `corpus-v2`, both judged by gpt-oss-120b. Both predate the parser fix and the amount check of 2026-11-06.
- **Claude first (the headline):** Claude Haiku 5.5 routes and answers, as the live site runs while its credits last (`evals/reports/2026-11-05-claude-first`, 07:15 UTC). Its comparison with the run of 2026-10-31 is under Measured decisions, above.
- **Free models only:** Gemini 3.5 Flash-Lite answers and gpt-oss-20b routes. The site falls back to them when Claude stops, and v2's test floors come from this run (`evals/reports/2026-10-31`, 15:31 UTC). It predates answer rule 4's four significant digits.
- Both ran on uncommitted branches; each report pins its source sha256. These reports print "pass" on the point estimate; the table below reads the whole interval.

| Metric | Target | Claude first (headline), 95% CI | Status | Free models only, 95% CI | Status |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 (n 25) | 0.90 | 0.596 (0.490 to 0.698) | fail | 0.596, the same search | fail |
| MRR@10 (n 25) | 0.70 | 0.628 (0.480 to 0.772) | inconclusive | 0.628, the same search | inconclusive |
| Numeric exact match (n 12) | 0.92 | 1.000 (0.758 to 1.000) | inconclusive | 1.000 (0.758 to 1.000) | inconclusive |
| Citation precision (judge) | 0.95 | 0.993 (0.977 to 1.000, n 43) | pass | 1.000 (1.000 to 1.000, n 37) | pass |
| Citation coverage | 0.95 | 0.950 (0.882 to 1.000, n 43) | inconclusive | 1.000 (1.000 to 1.000, n 39) | pass |
| Faithfulness (judge) | 0.92 | 0.976 (0.946 to 1.000, n 43) | pass | 0.990 (0.968 to 1.000, n 37) | pass |
| Correct refusal (n 10) | 0.90 | 1.000 (0.722 to 1.000) | inconclusive | 1.000 (0.722 to 1.000) | inconclusive |
| False refusal (n 45) | 5% or lower | 4.4% (1.2% to 14.8%; x21, x42) | inconclusive | 13.3% (6.3% to 26.2%; x21, x25, x26, x35, x40, x42) | fail |
| Router accuracy (route, tickers, years, metric, n 55) | - | 0.982 (0.904 to 0.997) | - | 0.564 (0.433 to 0.686) | - |
| Time to first token p50 | 1.0 s | 2.41 s (2.24 to 2.50, n 43) | fail | 1.47 s (1.39 to 1.61, n 38) | fail |
| Time to first token p95 | 2.0 s | 3.03 s (2.90 to 3.25, n 43) | fail | 2.12 s (1.85 to 2.38, n 38) | inconclusive |
| Full answer latency p95 | 6 s | 7.29 s (6.29 to 8.81, n 47) | fail | 3.98 s (3.73 to 4.70, n 44) | pass |
| Tokens per query, in | 8,000 | 9,408 (7,827 to 11,025, n 55) | inconclusive | 5,715 (4,589 to 6,905, n 55) | pass |
| Tokens per query, out | 600 | 484 (376 to 603, n 55) | inconclusive | 321 (256 to 392, n 55) | pass |
| Cost per query, as billed | $0.015 | $0.0012 in credits ($0.0010 to $0.0014, n 55) | pass | $0 | pass |

- **Claude first:** the whole interval misses on recall and on speed. Numeric match, refusals, coverage, MRR and tokens are too thin to call. It routes in 1.32 s at p50 against Groq's 0.66 s, its first draft takes longer (2.03 s against 1.45 s at p50), and it redrafts more often (draft citation pass rate 0.921 against 0.972). Its routing prompt is about twice Groq's in tokens.
- **Free models only:** false refusal (13.3%) and time to first token p50 miss across their whole interval. Their router reads 56% of questions fully right, against Claude's 98%.
- Recall@10 (0.596) misses for both: the search is the same, and its gold labels are Claude's (above).
- Golden v1's results below are history.

Golden set v1 (`evals/golden/v1`, frozen 2026-10-16) holds 100 questions over the 30 companies' latest 10-Ks. How it was built and labeled is in `evals/eval-card.md`.

- Textual gold is AI-labeled, spot-checked by a non-expert. Claude labeled every pooled passage.
- The human check was a fast spot-check by a non-expert, which cannot validate the labels on its own. The passage labels are not human-verified.
- Blind agreement on 79 passages was 49.4%, Cohen's kappa 0.10 (95% CI -0.07 to 0.26), which is not distinguishable from chance.
- The human then made the final call on the 40 disagreements and kept Claude's label on 37. That review showed Claude's reason, so it was not independent.
- Later, after reading the passage text, the human corrected 2 of their 3 overrides back to not gold. The final key now differs from Claude's labels on one passage.
- The judge behind citation precision and faithfulness (gpt-oss-120b) is calibrated against labels by Claude, a different and stronger model than the judge, not by a human. On 29 sentences it agreed 93.1%, Cohen's kappa 0.84 (95% CI 0.59 to 1.00), so those metrics count. Every negative in that sample was constructed. A follow-up spot check on natural sentences that fail the validator (2026-10-17) found the judge failing 3 of the 4 that Claude labeled not supported.
- While a golden set is in use (v3 now), don't run `make seed-real` or queue ingest jobs (see `make seed-real` in `docs/guide.md`).

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
