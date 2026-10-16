# Eval card: FilingLens golden set v1

## Golden set

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
  - Its detection of natural unsupported sentences is untested: Claude labeled all 21 natural sentences supported, so the sample holds none.
  - It was stricter than Claude on 2 of 21 natural sentences. Both of its "partly" verdicts hold up: s19's is defensible, and s07's is the correct reading under the criterion, where Claude's label was lenient.
  - Citation precision and faithfulness count under the rule, with these caveats.
- **Follow-up check (planned):** about 10 natural sentences that fail the validator, taken from the fallback-model runs (decision 4 in `docs/todo.md`), labeled by Claude, then judged. It tests the judge on natural unsupported sentences, if Claude finds any among them.
  - **Sample (drawn 2026-10-16):** a second calibration sample in `evals/calibration/v1-followup/`; v1's files stay frozen, and only v1's result decides whether the judge metrics count.
  - **Sources:** nemotron-3-super's answers (4b) first, since it is another family than the judge, then gpt-oss-20b's (4a). Never gpt-oss-120b's (4c), the judge's own model. gpt-oss-20b shares the judge's family.
  - **Size:** 6 sentences, short of 10. 4b's run held 2 failing sentences and 4a's 5, and the cap of 2 per question kept 4 of those. So the sample holds 2 from nemotron and 4 from gpt-oss-20b.
  - **Content:** three of them state figures that look derived from cited ones, such as 72% of $75.0 billion given as $54.0 billion.
  - **Labels (Claude, 2026-10-16):** 2 supported (s03, s06) and 4 not supported (s01, s02, s04, s05), in `claude_labels.jsonl`. Claude labeled `sample_for_labeling.jsonl` in another chat, without seeing the source model.
  - **Criterion:** exactly the written one. A sentence is supported only if the cited sources state everything it claims, and a rounded figure counts as stated. A number the answer computed is not stated, so the sentence is not supported, even when the arithmetic is right: 72% of $75.0 billion given as $54.0 billion (s01, s05), or an increase of $55.605 billion from two stated figures (s02).
  - **Result:** a spot check, not a kappa (six sentences are too few). It reports how many of the 4 unsupported sentences the judge also failed, and how many of the 2 supported ones it passed (`make calibrate ARGS="followup import"`, `result.json` in the same folder). It runs on 2026-10-17, when gpt-oss-120b's daily allowance has room after FreightAudit's CI.

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
