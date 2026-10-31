# Eval card: FilingLens golden sets v2 and v1

## Golden set v2 (frozen 2026-10-31)

Golden set v2 is the set in use. Its passage gold is AI-labeled, cross-checked blind by a second model; no human spot check in v2.

Its gold mixes two labelling standards. About 10 of the 150 carried gold passages would fail the strict qualifier rule, and they were left as they are. So Claude's 168 gold follow the qualifier rule and the 150 carried follow v1's looser rule (details below).

- **Questions:** 155, in `evals/golden/v2/questions.jsonl`.
  - v1's 100, unchanged and all in dev now, with v1's ci flags: the answer-quality round read v1's test answers, so v1's test split is no longer held out.
  - 55 new test questions (`V2_*` in `evals/golden.py`), written in free phrasing and hashed (sha256 `bf12aaa6...4224c`) before any fix of the round.
  - Numeric and comparison gold: XBRL facts by the latest-filed rule, as in v1.
- **Corpus:** the dev database after the four 10-Ks with a separate financial section (JPM, CVX, NVDA, PLD) were re-parsed, so their MD&A and statements sit under Items 7 and 8.
  - 30 indexed 10-Ks, 677 sections, 11,257 chunks with model A vectors (`embedding`), 856,438 facts, revision 0008.
  - Published for CI as the release asset `corpus-v2` (46.5 MB, sha256 pinned in `evals/corpus.py`).
- **Pools:** 59 (v1's 30 and 29 new), 1,129 passages.
  - v1's pools keep their passages by text hash: 538, 36 of them under new chunk ids.
  - They also take the chunks overlapping the 5 v1 passages whose text changed, and what v1's pool sources find on the re-parsed corpus.
  - New pools come from v1's pool sources.
- **Labels:**
  - The 538 kept passages carry v1's final label (`carried.jsonl`), described under golden set v1 below. About 10 of their 150 gold would fail the strict qualifier rule; they were left as they are.
  - Claude labeled the other 591, each with a one-line reason, under v1's guideline plus the qualifier rule: "A passage is gold only if it answers the question as asked, qualifier included." The passage itself must establish the qualifier, never outside knowledge.
  - Before the sample was drawn, one Claude reviewer checked all 180 of Claude's gold labels against the qualifier rule. 6 questions were labeled again in full, and 12 passages went to not gold.
  - Gold: 318 passages, 150 carried and 168 Claude's. Every textual question has gold; no absent question has any.
- **Cross-check (2026-10-31):** the judge model (`LLM_JUDGE`, `groq:openai/gpt-oss-120b`, another model family than Claude) labeled the fixed-seed blind sample of 50.
  - The sample comes from Claude's v2 labels only: 31 questions, 28 Claude-gold, none carried.
  - The judge saw what `make audit`'s blind screen shows (the question and its kind, the company, the item and the passage), never Claude's label or reason. Its rule was the one above, worded as the audit screen words it.
  - Its labels went through `make audit`'s path (`labels.jsonl`, `golden.audit_stats`), so the numbers come out as v1's did (`python -m evals.label crosscheck`).
  - **Agreement:** 90.0% (45 of 50), Cohen's kappa 0.80 (95% bootstrap CI 0.62 to 0.96). Claude said gold on 28, the judge on 25.
  - **Disagreements, 5:**
    - Claude gold, judge not gold, 4: x26 (Amazon's AI infrastructure spending; the passage says spending rises to support AI, and the judge wanted an amount); x31 (what ConocoPhillips gained from Marathon Oil; the judge read the transaction terms only); x35 (Goldman winding down its consumer business; Apple Card markdowns, with no statement about winding down); x38 (UnitedHealth's medical cost trends in 2025; the judge found no mention of 2025).
    - Judge gold, Claude not gold, 1: x43 (how Linde delivers industrial gases; Claude read an inventory policy, the judge read delivery methods).
  - A model's labels only measure agreement. They never become final, and nothing reviewed the 5: Claude's labels stand.
  - Two models agreeing does not show that the labels are right.
  - Cost: 50 calls, 35,388 gpt-oss-120b tokens on Groq's free tier.
- **The carried labels under the qualifier rule (2026-10-31, read only):** one fresh Claude reviewer checked the 150 carried gold labels as Claude's 180 had been checked. 10 would fail; nothing was changed.
  - 8 of the 10 were Claude's v1 labels and 2 the human's (of the 150: 123 and 27).
  - By question: x14 4 (Pfizer's patent expiries: the passages never establish "most significant products"), x05 2 (Tesla's plants, never said to build vehicles), and 1 each in x02 (no effect on sales to China stated), x09 (the acquisition never named as Hess), x19 (strategic capital never named) and x20 (electric and gas states listed together).
  - Two of x14's depend on reading "most significant" as a qualifier the passage must establish.
  - So v2's gold holds two standards: Claude's 168 under the qualifier rule, and the 150 carried under v1's rule, of which the qualifier rule would drop about 7%.
- **What the labels support:** retrieval metrics on v2 measure agreement with Claude's relevance judgments, and with v1's for the carried passages. Numeric, comparison and refusal gold does not depend on these labels.
- **Judge calibration:** v2 keeps v1's judge prompt, schema and model, so v2 reports cite v1's calibration (`evals/calibration/v1/result.json`, kappa 0.84; below). A test pins the prompt and schema hashes to those v1's official report recorded.
- **Floors:** keyed by golden version in `evals/thresholds.json` (`v2:...`; v1's keep theirs as `v1:...`). The dev floors CI gates come from E8 (2026-10-31), run on the free models CI uses, by the floor rule:
  - `v2:answer:dev:ci:gemini:gemini-3.5-flash-lite` from `evals/reports/runs/20261031T144658Z-answer-dev-ci` (25 questions, no judge): numeric exact match 1.000 (n 8), comparison match 1.000 (3), citation coverage 1.000 (14), correct refusal 1.000 (10), false refusal 0.067 (1 of 15: x15), time to first token p50 1.61 s and p95 2.71 s, full answer p95 3.85 s.
  - `v2:retrieval:dev:full` from `evals/reports/runs/20261031T145959Z-retrieval-dev-full` (20 textual questions): recall@10 0.595, MRR@10 0.742, nDCG@10 0.590, retrieval p95 328 ms at 11,257 chunks.
- **Results (2026-10-31, the 55 test questions, two runs, both judged by gpt-oss-120b; README has the table):**
  - **Claude first, the headline** (`evals/reports/2026-10-31-claude-first`, labelled; Claude Haiku 5.5 routes and answers, as production runs it): false refusal 4.4% (2 of 45), citation precision 0.980, faithfulness 0.968, coverage 0.950, numeric and comparison 1.000, correct refusal 1.000, router accuracy 0.982. Misses: time to first token p50 2.11 s and p95 5.06 s, full answer p95 7.07 s, 9,534 input tokens per query. $0.0012 of credits per query, about $0.066 in all.
  - **Free models only** (`evals/reports/2026-10-31`; Gemini 3.5 Flash-Lite answers, gpt-oss-20b routes): false refusal 13.3% (6 of 45), citation precision 1.000, faithfulness 0.990, router accuracy 0.564, time to first token p50 1.47 s. v2's test floors (`v2:...:test:full`) come from this run, as CI's floors must come from the free models.
  - Retrieval, the same search in both: recall@10 0.596 and MRR@10 0.628 over 25 textual questions.
  - Both ran on the uncommitted branch (each report pins its source sha256) at about 15:30 and 16:00 UTC, not at the 07:20 UTC of v1's run, so their latency reflects that hour.

## Golden set v1

- 100 questions, written on 2026-10-16 against the dev database: the latest 10-K of 30 companies in 11 sectors (11,263 chunks) and their XBRL facts.
  - 40 numeric, 20 textual, 15 comparison.
  - 15 unanswerable: 10 absent from the filings, 3 out of scope, 2 about companies FilingLens does not track.
  - 10 time traps, asking about the fiscal year after a company's latest 10-K.
- Splits: 70 dev and 30 test, stratified by category with a fixed seed. A 20-question ci subset is drawn from dev.
- Gold:
  - Numeric and comparison questions: XBRL facts by the latest-filed rule (`get_financial_fact`), with fact id and value.
  - Unanswerable questions and time traps: a refusal.
  - Textual questions: passages, labeled as described below.
- Frozen with a sha256 per file in `evals/golden/v1/manifest.json`, hashed with LF line ends. Any change makes a v2.
- The harness also checks the corpus against the set before every run (gold chunk ids and text hashes, fact ids and values, each company's latest fiscal year), and stops on drift.

## Labeling (passage gold)

Textual gold is AI-labeled, spot-checked by a non-expert. It is not human-verified.

**Candidates.** 543 passages were pooled for the 20 textual and 10 absent questions:
- each reranker configuration's top 10 (top 5 for absent questions);
- the top 5 by the question's hint phrases;
- for textual questions, also the top 5 by vector and by full text, each over all items and over the expected items.

One chunk was added to x15's pool by phrase, after the pools missed CAT's order backlog paragraph. Gold outside the pools is unlabeled. The retrieval report's judged@10 shows how much of each top 10 carries a label.

**Labeled by Claude.** Claude, an AI model, labeled all 543 passages yes or no, each with a one-line reason. The guideline:
- A passage is gold if by itself it states all or part of the answer.
- For an absent question, a passage is gold only if it answers the question, so an absent question should end with none.

**Spot-checked by a non-expert.** The human check was a fast spot-check by a non-expert. It cannot validate the labels on its own.
- **Blind labels:** 79 passages, labeled without seeing Claude's label:
  - the 19 passages of x01 (2026-10-15);
  - then a fixed-seed sample of 60 from the other 29 questions, 23 of them Claude-gold (2026-10-16).
- **Agreement before review:** 49.4% (39 of 79), Cohen's kappa 0.10 (95% bootstrap CI -0.07 to 0.26). The interval includes 0, so the agreement is not distinguishable from chance.
  - Claude said gold on 27 of the 79, the human on 55.
  - Of the 40 disagreements, 34 had the human saying gold where Claude did not. 11 of those were on absent questions, where the human said a passage answers the question.
  - The other 6 had Claude saying gold where the human did not.
- **Per sitting:**

  | Sitting | Passages | Agreement | Kappa (95% CI) | Pace |
  | --- | --- | --- | --- | --- |
  | x01 (2026-10-15) | 19 | 79% | 0.22 (-0.18 to 0.77) | median 4.5 s per passage |
  | Sample (2026-10-16) | 60 | 40% | -0.02 (-0.16 to 0.12) | median 3 s per passage; human said gold on 53 |

  Passages run a median of 262 words.
- **Review:** the human made the final call on all 40 disagreements, seeing the passage, both labels and Claude's reason.
  - 37 settled on Claude's label and 3 on the human's (gold): one passage each in x01, x02 and x05.
  - The review took 47 seconds for 40 decisions, a median of 1 s each.
  - It showed Claude's reason, so it was not independent of Claude.
- **Corrections by the human labeler (2026-10-16):** after reading the passage text quoted back to them, the human labeler set two of those three to not gold. V1 was unfrozen and refrozen for this, before any test run used it.
  - x01 `e9a636de` (Apple, Item 1) is now not gold. The passage covers services, payments, segments and distribution, not where the outsourcing partners manufacture; "Greater China includes China mainland, Hong Kong and Taiwan" defines a sales segment.
  - x05 `de1c06bf` (Tesla, Item 8) is now not gold. It is a tax-incentive note that places Gigafactory Nevada ("In connection with the construction of Gigafactory Nevada, we entered into agreements in 2014 with the State of Nevada and Storey County in Nevada...") and names Gigafactory Texas in a heading, but never says either one builds vehicles.
  - x02 `89cfdd9a` (NVIDIA, Item 1A) stays gold, the human's call. The passage states general effects of export controls on demand and supply, though its only mentions of China are about effects outside China.
- **Final gold:**
  - The human's final label covers the 79 spot-checked passages; Claude's covers the other 464.
  - So the answer key is Claude's labels with one human override (x02 `89cfdd9a`).
  - That gives 152 gold passages over the 20 textual questions (1 to 15 each), and none for the absent questions.

**What the labels support.**
- The passage labels are AI labels, not human-verified.
- The spot-check cannot establish how accurate they are, for three reasons:
  - the blind agreement is at chance level;
  - the sample was labeled at a median of 3 s per passage;
  - the review was fast and saw Claude's reasons.
- Retrieval metrics (recall@10, MRR@10, nDCG@10) therefore measure agreement with Claude's relevance judgments.
- Numeric, comparison and refusal gold does not depend on these labels.

## Judge calibration

Citation precision and faithfulness come from an LLM judge (`LLM_JUDGE`, gpt-oss-120b on Groq). They count only if the judge agrees with the calibration labels, Cohen's kappa 0.7 or more (`make calibrate`, result in `evals/calibration/v1/result.json`, which names the labeler).

**The calibration labels are by Claude, not by a human** (user decision, 2026-10-16):
- Claude, a different and stronger model than the judge, labeled the 30 sentences in a separate chat. It worked from `evals/calibration/v1/sample_for_labeling.jsonl`: per sentence, the question, the sentence, and each cited passage in full with the quote given, with no verdict and no mark of the constructed ones.
- Its labels are in `claude_labels.jsonl`, scored with `make calibrate ARGS=import`.
- So the calibration measures agreement between two models, not agreement with people. A stronger model can still share the judge's blind spots.

**Sample (user decision, 2026-10-16):** drawn once with a fixed seed from the dev gate-off answer run of 2026-10-16 (`evals/reports/runs/20261016T062753Z-answer-dev-full`), and frozen in `evals/calibration/v1/sample.jsonl`. It holds 30 sentences from 20 questions, at most 2 per question, shuffled together. The labeler is not told which are which.
- **21 natural:**
  - 16 from final answers, which pass the validator;
  - 5 that fail it, from first drafts and regenerations. The dev run had 10 such sentences, from 3 questions, and the per-question cap left 5.
- **9 constructed negatives:** a final-answer sentence citing one passage, with that citation pointed at another passage retrieved for the same answer. The answer never cited that passage, and the quote shown is a 12-word span of it at a seeded position.
- **Left out:**
  - final answers from which validation removed a sentence (x06, x16, x17), since a sentence-splitter bug could leave an orphan fragment there (fixed later on 2026-10-16; the fix changes none of the 30 sentences and none of the judge's prompts for them);
  - sentences that follow an abbreviation such as "U.S.".

**Caveats:**
- Constructed negatives may be easier to catch than natural errors, since the swapped passage is often off topic. Agreement on them can flatter the judge, so kappa is reported overall and per stratum.
- Natural unsupported sentences are rare because Gemini's drafts mostly pass validation. That is why constructed ones were needed.
- The labeler's labels are the reference. A constructed sentence that its new passage happens to support counts as supported.
- **Labeler's note (Claude, 2026-10-16):**
  - The constructed negatives were easy to recognize, because their quotes are unrelated to the sentence. The judge's score on those 9 is likely generous.
  - So the result also reports kappa on the 21 natural sentences alone. That figure rests on few negatives: Claude marked 9 of the 30 sentences not supported, most of them constructed. Its interval is wide.

**Result (2026-10-16, `evals/calibration/v1/result.json`):**
- **Scored:** 29 of 30 sentences. The judge's reply for s30 (x08, constructed, Claude: not supported) did not parse: it judged source [2] for a sentence that cites [1]. That sentence is unscored.
- **Agreement:** 93.1% (27 of 29). Cohen's kappa 0.84 (95% bootstrap CI 0.59 to 1.00). Kappa is 0.7 or more, so citation precision and faithfulness count. The lower end of the interval is below 0.7.
- **Sensitivity, s30 counted as a disagreement** (the judge saying supported where Claude said not supported, instead of leaving s30 out):
  - 30 sentences, agreement 90.0% (27 of 30), Cohen's kappa 0.77 (95% bootstrap CI 0.47 to 1.00). Kappa is still 0.7 or more.
  - Constructed negatives caught: 8 of 9.
  - Computed from `result.json` with the same kappa and bootstrap (same seed) as `make calibrate`, which reproduce the 0.84 above. `result.json` itself keeps the scored figure.
- **Confusion:**

  | | Judge: supported | Judge: not supported |
  | --- | --- | --- |
  | Claude: supported | 19 | 2 |
  | Claude: not supported | 0 | 8 |

  Only "yes" counts as supported; the judge's "partly" counts as not supported.
- **Per stratum:** constructed 8 of 8, failing 5 of 5, passing 14 of 16.
- **The 21 natural sentences alone:** agreement 90.5% (19 of 21), kappa 0.00 (CI 0.00 to 1.00).
  - Claude labeled all 21 supported, so all 9 of its negatives are the constructed ones.
  - With no negative from the labeler, kappa on natural sentences is 0 whenever the judge says no once, so it measures nothing here.
  - The 5 sentences that fail the validator were labeled supported by both: their quotes failed, not their content.
- **Disagreements:** both are natural sentences from final answers, where the judge said "partly" and Claude "supported". The judge gives no reasons.
  - s07 (c06), "Therefore, Caterpillar's cash from operating activities was higher [1][2]." It cites the two fiscal 2025 facts, 11,739,000,000 USD (CAT) and 9,290,000,000 USD (UNP). Claude: "Passages give Caterpillar 11,739,000,000 USD versus Union Pacific 9,290,000,000 USD for the same 2025 period, so Caterpillar's was higher." The judge may treat the comparison as a conclusion the sources do not state.
    - Under the written criterion (supported only if the cited sources state everything the sentence claims), the judge's "partly" is the stricter and correct reading: the sources state both figures but not the comparison.
    - Claude's v1 label was more lenient than that criterion.
    - v1's labels stay unchanged, because relabeling after seeing the judge's verdict would bias kappa.
  - s19 (x01), "Apple's outsourcing partners that manufacture its hardware products are located primarily in China mainland, India, Japan, South Korea, Taiwan, and Vietnam, in addition to partners and facilities located in the U.S [1][2][3]." Claude: "Passage [1] says hardware is made by partners primarily in China mainland, India, Japan, South Korea, Taiwan and Vietnam, and [2] adds sourcing from partners and facilities in the U.S."
    - The judge's "partly" is defensible. Passage [2] speaks of sourcing from partners and facilities in the U.S., not of manufacturing there, while the sentence puts manufacturing partners in the U.S.
- **What it supports:**
  - The judge was tested only on constructed negatives. It caught every one it scored (8 of 8; s30 unscored).
  - v1 holds no natural unsupported sentence: Claude labeled all 21 natural sentences supported. The follow-up check below tests 4 of them: the judge caught 3.
  - It was stricter than Claude on 2 of 21 natural sentences. Both of its "partly" verdicts hold up: s19's is defensible, and s07's is the correct reading under the criterion, where Claude's label was lenient.
  - Citation precision and faithfulness count under the rule, with these caveats.
- **Follow-up check (done 2026-10-17):** about 10 natural sentences that fail the validator, taken from the fallback-model runs (decision 4 in `docs/todo.md`), labeled by Claude, then judged. It tests the judge on natural unsupported sentences, if Claude finds any among them.
  - **Sample (drawn 2026-10-16):** a second calibration sample in `evals/calibration/v1-followup/`; v1's files stay frozen, and only v1's result decides whether the judge metrics count.
  - **Sources:** nemotron-3-super's answers (4b) first, since it is another family than the judge, then gpt-oss-20b's (4a). Never gpt-oss-120b's (4c), the judge's own model. gpt-oss-20b shares the judge's family.
  - **Size:** 6 sentences, short of 10. 4b's run held 2 failing sentences and 4a's 5, and the cap of 2 per question kept 4 of those. So the sample holds 2 from nemotron and 4 from gpt-oss-20b.
  - **Content:** three of them state figures that look derived from cited ones, such as 72% of $75.0 billion given as $54.0 billion.
  - **Labels (Claude, 2026-10-16):** 2 supported (s03, s06) and 4 not supported (s01, s02, s04, s05), in `claude_labels.jsonl`. Claude labeled `sample_for_labeling.jsonl` in another chat, without seeing the source model.
  - **Criterion:** exactly the written one. A sentence is supported only if the cited sources state everything it claims, and a rounded figure counts as stated. A number the answer computed is not stated, so the sentence is not supported, even when the arithmetic is right: 72% of $75.0 billion given as $54.0 billion (s01, s05), or an increase of $55.605 billion from two stated figures (s02).
  - **Result (2026-10-17, `make calibrate ARGS="followup import"`, `result.json` in the same folder):** a spot check, not a kappa, since six sentences are too few.
    - The judge failed 3 of the 4 sentences Claude labeled not supported. It said "partly" on s01 and s02 and "no" on s05: all three computed figures.
    - It missed s04 (t07, Chevron): "yes" on risks that the passages list as risks to Chevron's climate aspirations, which the answer presents as risks to its business. A natural unsupported sentence can pass the judge, so faithfulness may be overstated somewhat.
    - It passed s06, the one supported sentence it scored. s03 is unscored: its reply judged 3 sentences for a 1-sentence answer, which `judge.parse` rejects.
    - Cost: 6 calls, 8,337 input and 1,574 output tokens of gpt-oss-120b.

## Time to first token

The target is p50 1.0 s and p95 2.0 s. On the free tiers FilingLens misses it, and the numbers below are as measured on dev (2026-10-16).

- **Gemini's own first token drifts.** On the same 46 dev questions, Gemini 3.5 Flash-Lite's own first token was p50 0.97 s at 05:56 UTC and 3.37 s at 09:00 UTC. The later runs also drew 503 errors.
- **The stages run in sequence.** Before Gemini starts, the router takes about 0.66 s (p50) and retrieval about 0.30 s. Even when Gemini was fast, the best dev run reached TTFT p50 1.8 s. So 1.0 s is not reachable on free tiers with the stages in sequence.
- **Gemini's thinking setting** makes no measurable difference (minimal against the model default, run minimal, default, minimal in one sitting).
- **Fix: the search starts while the router runs.** It searches the companies and years the question names, read in code, and is kept only when the router's plan asks for the same scope, so answers do not change.
  - The router agreed on 18 of 28 dev questions that searched.
  - On those, the time before Gemini starts fell from p50 1,060 ms to 684 ms. The median paired change was −268 ms (95% CI −490 to −128, n 16), against the run without the fix.
  - End to end, TTFT stays bound by Gemini: p50 3.7 s and p95 9.6 s at 10:00 UTC.
- **Reading a TTFT figure:** it depends on the hour it was measured, including the test run's.

## Test run (2026-10-17)

`make eval SUITE=all SPLIT=test` at 07:24 UTC, on the production path (no `--tag`). Commit `77e59a0` with no uncommitted changes, source sha256 `b238808a…`. 30 questions, no errors, 29 of 30 with every call live. Report: `evals/reports/2026-10-17.md`.

The official results are Gemini's (free tiers). The Haiku column is a comparison on the same 30 questions and the same router replies: Claude Haiku 5.5 pinned, thinking off, judge on, nothing tuned. Command: `LLM_PRIMARY=anthropic:claude-haiku-5-5 make eval SUITE=answer SPLIT=test ARGS="--router-primary=gemini:gemini-3.5-flash-lite --primary-tag=fair"`, at 08:47 UTC (report `runs/20261017T084716Z-answer-test-full.md`).
- It replaces a first Haiku run at 08:29 UTC (`runs/20261017T082950Z`), which asked the router again, because the answer path's cache key includes the primary. The router then routed x13, x14 and x18 as textual, so that run's refusals differed by the router, not the answer model.
- `--router-primary` keys router calls as Gemini's run did, so all 30 router replies came from it.
- With no question fully live, Haiku's end-to-end latency is not measured. Its latency cells pair the answer models' own calls.

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

- **Every Gemini miss:**
  - **False refusal 0.130 (3 of 23):** the router sent x13, x14 and x18 out of scope with no tickers. Retrieval ranked their gold first (MRR 1.0), so a correct route would likely have answered.
  - **Citation precision 0.944 (34 of 36 pairs):** c02's conclusion "Therefore, Alphabet's total revenue was higher in fiscal 2025 [1][2]" got "partly", with neither citation counted as support. The sources state both figures but not the comparison, the reading seen in calibration (s07).
  - **Recall@10 0.583:** it rests on 6 questions, so one question is worth about 0.17. x12 scored 0.000 and x04 0.429.
  - **TTFT p50 1.55 s:** the stages run in sequence (router p50 0.62 s, then facts or retrieval, then Gemini). Gemini's own first token drifts with the hour on the free tier (§ Time to first token). It was fast at this hour (generate p50 1.08 s), so the p95 pass is not a steady result.
  - **Not measured:** retrieval p95 at the 250k-chunk scale (336 ms at 11,263), and ingestion.
  - **Refused, but not by the expected rule:** t10 (Walmart's fiscal 2027 10-K, a time trap) and a03 (absent) were refused as "nothing relevant enough", because the router gave no ticker.
- **The Haiku comparison (same routes):**
  - **Same refusals:** the router's 3 out-of-scope calls refuse for both models, so false refusal is 0.130 for each. Correct refusal is 1.000 for both.
  - **Quality:** numeric and comparison match 1.000 for both. Citation precision 0.958 against 0.944 (paired difference +0.014, CI −0.103 to +0.147); faithfulness 0.944 against 0.970 (−0.025, CI −0.131 to +0.065). No measurable difference on 20 answers.
  - **Haiku-specific misses**, as findings:
    - n28 (Prologis' total liabilities): Haiku hedged that the fact, labeled "fiscal 2025 Q1" for a year-end balance from a 2026 10-Q, "does not directly answer" the year-end question. The value was still exact, and the judge rated the sentence "partly". This is the fact-heading weakness behind dev's n17 and n24.
    - c12 (Tesla): its conclusion "decreased in fiscal 2025 relative to fiscal 2024" got "partly", the comparison-conclusion reading behind Gemini's c02. Haiku wrote no conclusion for c02.
  - **Latency, paired on 22 answers:** Haiku's own first token p50 was 0.72 against 0.85 s (difference −0.13 s, 95% CI −0.18 to −0.07) and p95 0.94 against 1.13 s. Its own reply total p50 was 1.09 against 1.08 s.
  - **Size and cost:** Haiku's answers ran longer, 4,853 input and 278 output tokens per query, citing more passages. It was cut 0 times.
  - **Spent:** 26 Claude calls (114,659 input and 6,066 output tokens), $0.0145 in credits. Groq: 0 gpt-oss-20b and 19.2K gpt-oss-120b (14 live judge calls; 6 judged answers matched earlier ones in the cache).
- **Floors:** written from Gemini's run after the user's review (`--set-floors evals/reports/2026-10-17.json`), under `answer:test:full:gemini:gemini-3.5-flash-lite` and `retrieval:test:full`.
  - **Dev floors for CI** (2026-10-17, after the user's review of the two reports):
    - `retrieval:dev:full`, from `20261017T103956Z-retrieval-dev-full` (the restored CI corpus): recall@10 ≥ 0.542, MRR@10 ≥ 0.577, retrieval p95 ≤ 478 ms (not gated in CI).
    - `answer:dev:ci:gemini:gemini-3.5-flash-lite`, replaced on 2026-10-17 from one fresh live run of the widened ci subset (`20261017T154912Z-answer-dev-ci`: 25 questions, 10 should-refuse, no judge). The values: numeric exact match ≥ 0.676, coverage ≥ 0.950, correct refusal ≥ 0.722, false refusal ≤ 0.379, input tokens ≤ 7,393, output tokens ≤ 312, cost ≤ $0.0023, billed $0, TTFT p50 ≤ 2,990 ms, TTFT p95 ≤ 3,157 ms, answer p95 ≤ 5,831 ms (latency gated on the PC only).
    - The first floors, from `20261017T104130Z`, had collapsed ranges: 8 of 8 and 5 of 5 gave 1.0 to 1.0, so the floor equalled the target. One miss out of 5 then failed the first PR's CI (t07 answered live).
  - **Pass/fail metrics use a Wilson score interval (user decision, 2026-10-17):** numeric and comparison match, correct and false refusal, router and route accuracy. A percentile bootstrap of identical results collapses to a point; Wilson gives 5 of 5 a range of 0.566 to 1.0. The rule stays min(low, target).
  - **One rule everywhere (user decision, 2026-10-17):** the test floors were recomputed by code from this saved exam report, with no new run (`--set-floors evals/reports/2026-10-17.json --replace`):
    - numeric exact match ≥ 0.758 (12 of 12), correct refusal ≥ 0.646 (7 of 7), false refusal ≤ 0.321;
    - retrieval recall@10 ≥ 0.416 and MRR@10 ≥ 0.667, under the retrieval rule.
    - Floors are guards derived from measured results, so this is not tuning.
  - **What CI can and cannot see:** with 8 numeric questions, the CI floor of 0.676 still lets 6 of 8 pass, and the refusal floor of 0.722 lets 8 of 10 pass. CI is a tripwire for large drops. The nightly run and this exam give the precise numbers.
  - **Groq budget:** a live CI answer run uses about 28K gpt-oss-20b tokens, on the Groq account FreightAudit's CI also uses.
    - Groq's daily allowance is per model: about 200K tokens a day each (memory.md, Constraints).
    - FreightAudit uses gpt-oss-120b and qwen3.8-27b, and keeps about 25K a day of gpt-oss-120b for its CI.
    - So a PR eval (0 gpt-oss-120b) draws on FilingLens's gpt-oss-20b allowance only. The nightly's judge (18-28K gpt-oss-120b) shares FreightAudit's model.
  - **Retrieval accuracy floors use their own rule (user decision, 2026-10-17):** the measured value less one question's share, capped at the target. With 14 scored questions, that is 0.613 − 1/14 for recall and 0.649 − 1/14 for MRR.
    - Retrieval calls no model, so the same code on the same corpus gives the same numbers.
    - Its 95% interval reflects only which 14 questions the set holds. A floor at its lower bound (recall 0.402) would let a real drop from 0.613 pass.
    - One question's share still tolerates one near-tie flipping on GitHub's CPUs.
    - Answer floors keep the usual rule, since model replies vary run to run.
    - The test-split retrieval floors predate the rule and stay until `--set-floors` runs again on a test report.

### Known weaknesses and v2 ideas

Nothing is tuned on these test results; each idea needs a new dev measurement, and a new golden set version for any test claim.

- **Router out of scope** (x13, x14, x18): in code, a question that names a tracked company (`router.guess`) is never out of scope; or in-scope examples in the router prompt.
- **Router without tickers** (t10, a03): fill the single named company from `router.guess` when the router gives none, so the time-trap and other rules apply.
- **Comparison conclusions** (Gemini's c02, Haiku's c12): check "higher" or "lower" against the cited fact values in code, like the derived-number idea in `docs/todo.md`.
- **Recall on 6 questions:** a v2 set with 20 or more textual test questions and human-verified passage labels. A stronger reranker showed headroom on dev (MiniLM-L-6, recall +0.09 at about 14 times the rerank time).
- **TTFT:** skip the router call when code can route, or start the answer model on the early search. Measure over several hours.
- **Fact headings** (Haiku's n17 and n24 on dev, n28 on test): label an instant fact by its date and the period asked for, not by the period of the filing that reported it.
- **Judge:** the follow-up check passed a natural unsupported sentence (t07). Calibrate on more natural negatives, labeled by a human.
- **Scale:** retrieval latency at about 250k chunks, and ingestion of 500 filings.

## Answer length: 1,024 tokens

- **Where:** `MAX_TOKENS = 1024` in `packages/llm/src/filinglens_llm/answer.py`. The Answerer passes it to every answer call, the streamed draft and the one regeneration, in evals as in the API. Evals raise it to 4,096 only for Gemini's `--thinking=default` (decision 3).
- **Why:**
  - Latency: output tokens set most of an answer's time.
  - Cost: output is the dearest token, $0.50 per 1M on Haiku and $2.50 on Gemini's paid tier.
  - Focus: a cited answer is a few sentences plus a Sources block.
  - Runaway protection: a looping or rambling reply stops at a known size, inside the 30 s answer limit.
- **Reasoning shares it:** reasoning tokens count toward the limit, so every answer model runs its lowest reasoning setting. Gemini runs minimal thinking, gpt-oss reasoning effort low, and Claude thinking off.
  - With adaptive thinking, Claude used up the limit on 4 dev answers, and 3 of its regenerations had no text left (§ Claude Haiku 5.5 on dev).
  - With thinking off, no Claude reply was cut on dev or test; the longest was 956 tokens.
  - Gemini's replies were never cut on golden v1.

## Claude Haiku 5.5, pinned, on dev (2026-10-17)

One run to catch model-specific breakage, nothing tuned: `LLM_PRIMARY=anthropic:claude-haiku-5-5 make eval SUITE=answer SPLIT=dev ARGS=--no-judge`. It ran with adaptive thinking at effort low and the shared 1,024-token answer cap. Report: `evals/reports/runs/20261017T075734Z-answer-dev-full.md`. Its header says "thinking minimal", the Gemini flag's value; the harness now names Claude's setting.

- **Breakage: thinking uses up the 1,024-token cap.**
  - 4 answers hit the cap (x03, x07, x17, x19).
  - In x03, x17 and x19 the regeneration came back with no text at all, so validation kept no sentence. That is 3 of the 6 false refusals.
  - Fixed by user decision: Claude's thinking is off (effort low accepts that), and the 1,024-token cap stays.
- **Rerun with thinking off** (`--primary-tag=nothink`, router replies cached; report `20261017T082532Z-answer-dev-full.md`):
  - 0 truncated, 0 empty replies, 0 errors.
  - False refusal 0.058 (n17, n24 and x15).
  - Coverage 0.933 and draft citation pass rate 0.889, against 0.987 and 0.963 with thinking on.
  - Claude's own first token, paired over 54 questions: p50 0.71 against 0.78 s, p95 1.08 against 3.03 s (95% CI of the difference −3.35 to −1.46 s).
  - Its end-to-end latency rows rest on 1 question, since only x11's router call ran live.
  - Two reranks passed their 500 ms limit, so those answers used the fused order.
  - Credits $0.0381 (67 calls, 301,466 input and 15,870 output tokens).
- **Numeric:** exact match 0.929 (26 of 28) in both runs. n17 (Goldman Sachs' total assets) and n24 (Lockheed Martin's cash) were answered INSUFFICIENT_EVIDENCE although the XBRL fact was the source given.
  - Cause, a FilingLens labeling issue that Haiku exposes: both are year-end 2025 balances taken from a 2026 Q2 10-Q's comparative (the latest-filed rule), and the fact heading reads "fiscal 2025 Q2".
  - Haiku answered that "fiscal 2025 Q2" is not the end of fiscal 2025. Gemini answered from the same heading.
- **Otherwise:**
  - Comparison match 1.000 (n 10), coverage 0.987, draft citation pass rate 0.963 (16 quotes), correct refusal 1.000 (n 18).
  - False refusal 0.115: the 3 truncations, the 2 numeric refusals and x15, which the router sent out of scope.
  - The one error is x11: the Groq router answered 400.
  - No Anthropic error, rate limit or refusal.
- **Latency (69 live answers, one sitting):** TTFT p50 1.58 s and p95 4.23 s, full answer p95 9.48 s, generate p50 1.41 s. Gemini's figures drift with the hour, so this is no comparison.
- **Tokens and cost:**
  - Per query: 4,557 input and 394 output tokens; Claude's own output p50 241, max 1,024.
  - Credits: 60 calls, 243,295 input and 22,083 output tokens, $0.0354 in all, $0.0005 per query as billed.
  - Groq gpt-oss-20b: 76.3K tokens (69 router calls, new keys for the new primary). No judge.
