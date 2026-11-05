# Prompt Log

Every change to a model prompt or response schema, newest first. Each entry gives what changed, why, the evidence and the result. Prompts are tuned on the golden set's dev split only, and the test split is never read for tuning. The judge prompt (`evals/judge.py`) is frozen with its calibration, so a change to it needs a new calibration.

## 2026-11-05: Answer rule 4's floor, measured on the test split

- No prompt change. `evals/reports/2026-11-05-claude-first`, hash `25e4578a6d3b`: numeric exact match 1.000 (n 12), every rounded figure at four significant digits or more, no quality metric worse beyond its interval. Side effect: per-share facts copied as "51.32 USD" (`evals/README.md`, `docs/memory.md`).

## 2026-11-04: Answer rule 4 asks rounded figures for at least four significant digits (after the Sonnet comparison)

- **Answer prompt** (`filinglens_llm.answer.SYSTEM`, rule 4): "Give figures as the sources state them, or rounded to at least four significant digits, such as $416.2 billion or $4.121 billion." It said "…or rounded, such as $416.2 billion." Only the answer prompt's hash changes (`a4da1c402e0a` to `25e4578a6d3b`); the router's and the judge's do not. Validation's rounding rule (`validate.rounded`) stays, so a figure rounded further still passes instead of being refused.
  - Why: Haiku's two numeric misses on dev in the Sonnet comparison (`evals/README.md`), n24 and n39, were one decimal in billions: $4.1 billion for 4,121,000,000 (0.51% off) and $6.7 billion for 6,747,000,000 (0.70%), outside numeric exact match's 0.5%. One decimal is four significant digits for $416.2 billion but two for $4.1 billion. Sonnet kept four.
  - Result (Claude Haiku, dev, fully live: `runs/20261104T091822Z`, judged `runs/20261104T092734Z`; before: `20261103T162805Z`, `175043Z`):
    - Numeric exact match 1.000 (0.950). Of the 40 figures, 17 as the source states them, 23 rounded within 0.5%, none outside (before 7, 31 and 2). n24 "$4.121 billion", n39 "$6.747 billion".
    - Paired against the earlier run: citation precision 0.995 (0.985; +0.016, CI +0.000 to +0.032), faithfulness 0.986 (0.993; −0.007, CI −0.033 to +0.015), coverage 0.962 (0.987; −0.026, CI −0.077 to +0.013), draft citation pass rate 0.869 (0.914; −0.045, CI −0.113 to +0.015). Refusals unchanged.
    - TTFT p50 2.49 s (2.31), full answer p95 6.76 s (6.90). The router stage, unchanged, was slower at this hour (p50 1,470 against 1,385 ms); Haiku's own first token is the same (p50 0.74 against 0.72 s, CI of the difference −0.02 to +0.07).
  - Open: coverage's drop is three textual answers losing sentences to quotes not copied word for word (x03, x13, x19; x19 split a table row into two quoted pieces), not to amounts. Two drafts' layouts got past the reply parser, so the judge could score neither: n40 ended its answer line with "Sources:", and the block stayed in the answer as shown; c07 put its markers after the periods, so three sentences were validated as one. Both for their own PRs (todo.md).

## 2026-10-27: Answer rule 5, a calculation (K1) holds a comparison's arithmetic (answer-quality round, PR 4)

- **Answer prompt** (`filinglens_llm.answer.SYSTEM`, new rule 5; old 5 and 6 are now 6 and 7): "A calculation (K1), when given, states two facts' difference, change in percent and which is higher. Cite it for any of these, together with both of its facts, such as [F1][F2][K1], and quote the figure you used; compute nothing yourself." Only the answer prompt's hash changes (`a4ee7c5d3686` to `a4da1c402e0a`); the router's and the judge's do not (E5's report).
  - Why: Haiku computed correct differences ("an increase of about $25.1 billion", c09) that no source held, so validation sent them back. Code now computes them as K1 for a comparison of two facts of one unit, and validation checks K1's figures and, for one company's two years, the direction word.
  - Result (E5, Claude Haiku, dev): citation precision 1.000 (E2 0.991), coverage 1.000 (0.989), faithfulness 0.989 (0.988), false refusal 0.019 (0.038); 6 of 10 comparison answers cite K1, all judged "yes".
  - Open: 8 of 10 comparison drafts were sent back (E2: 2). The model wrote the difference in a second sentence citing [F1][F2][K1] without the two figures, which rule 4's check refuses (c06 cited [K1] alone). Each regeneration held. A wording such as "state the difference in the same sentence as both figures" would likely cut these; it changes this hash again and needs a measured run (the user's decision, todo.md).

## 2026-10-26: Answer rule 4 states compared figures; the router's second look (answer-quality round)

- **Answer prompt** (`filinglens_llm.answer.SYSTEM`, rule 4): "A sentence that compares figures states each of them." The answer prompt's hash changes; the router's and the judge's do not.
  - Why: the only citation-precision misses on the official test run were c02's bare conclusion ("Therefore, Alphabet's total revenue was higher in fiscal 2025 [1][2]"), whose two citations the judge did not count; dev's c01, c03 and c06 have the same shape. With the figures in the sentence, the judge counted both citations (c08, dev).
  - Validation enforces it: a sentence with a comparison or direction word that cites facts must state each fact's figure, or it is sent back.
  - Result (E2, Claude Haiku, dev): citation precision 0.991 (E1 0.976), faithfulness 0.988 (0.938), comparison match 1.000. Only `answer_system`'s hash changed (`a72e8ef8b102` to `a4ee7c5d3686`). The free models' result comes from the official v2 run (PR 7).
- **Router, a second look** (a user prompt, `router.second_look_prompt`; the system prompt and schema are unchanged): an out-of-scope reply for a question that names a tracked company, with no forecast or advice wording, is asked once more with the scope rule, and the second reply stands.
  - Why: x13, x14 and x18 (test, 2026-10-17) went out of scope and were routed textual when asked again in another run.
  - Result (E1b, live, three tries each): 7 of 21 first replies for seven answerable questions were out of scope, 1 after the second look; 5 of 11 out-of-scope replies for absent questions moved to an answering route.

## 2026-10-16: Router v2: tracked companies, ticker enum, a metric for comparisons (user decision)

- **Changes** (`filinglens_llm.router`, `filinglens_api.answering`):
  - **Tracked companies:** the system prompt lists them (ticker and name), read on each answer from companies with an indexed filing (`Evidence.tracked`).
  - **Tickers:** must come from that list. The response schema holds them as an enum, which Groq's strict JSON schema enforces.
  - **`other_companies`:** a new field for companies the question names that FilingLens does not track, by the question's name. A non-empty one is refused as untracked: "FilingLens has no filings for Netflix."
  - **Comparisons:** "comparison" now means a reported figure compared across companies or periods. Comparisons of anything else are textual. A comparison always carries its metric ("total revenue" is revenue).
  - **Code checks:** each reply is checked in code too (`router.problems`), for providers that do not enforce the enum. On an untracked ticker or a comparison without a metric, the router is asked once more, with the problems listed (`router.retry_prompt`). A ticker still unknown after that is refused as untracked.
- **Why:** in the dev gate-off run of 2026-10-16 (report `20261016T055608Z-answer-dev-full`), the router caused 12 of the 15 false refusals:
  - 6 wrong tickers guessed from company names, each refused as untracked: n04 GOOG for GOOGL, n09 HST for HD, n13 CONP for COP, n20 UHG for UNH, n27 FMS for FCX, and x17 NSC with UPU for UNP.
  - 6 comparisons without a metric, so no facts were read and the model replied INSUFFICIENT: c01, c03, c07, c08, c09, c10.
  - Router accuracy (route, tickers, years, metric) was 0.671, and route accuracy 1.000.
- **Eval scoring:** a gold ticker FilingLens does not track (u01 NFLX, u02 COST) now counts as right when the router names the company in `other_companies`, since the enum cannot hold it.
- **First dev rerun** (report `20261016T062057Z-answer-dev-full`, gate off):
  - Improved: numeric exact match 0.821 to 1.000, comparison match 0.200 to 0.900, false refusal 0.288 to 0.135.
  - No retry was needed: all 70 router calls were first calls.
  - New regression: gpt-oss-20b put tracked companies in `other_companies` (x05 Tesla, x07 Coca-Cola, x19 Prologis, x17 Union Pacific, t05 NextEra Energy). It also listed companies a question only mentions there (x09 Hess, x17 Norfolk Southern). All were refused as untracked, 5 of them false refusals.
- **Follow-up, code only** (the prompt and the cached router replies unchanged):
  - **Name matching:** `router.resolve` moves an `other_companies` name that matches exactly one tracked company into `tickers`. It matches the ticker, or the leading words of the name with legal suffixes dropped, so "Coca-Cola" matches "COCA COLA CO".
  - **Refusal rule:** an untracked company is refused only when the question names no tracked one, or when the route is numeric or comparison (its figures are needed). A textual question about a tracked company may mention others: x09 Chevron's acquisition of Hess is answered.
- **Result** (dev, gate off, report `20261016T062753Z-answer-dev-full`; two Gemini 503s and a timeout cleared on reruns; 0 errors):

  | Metric | Before | After |
  | --- | --- | --- |
  | Numeric exact match | 0.821 | 1.000 |
  | Comparison match | 0.200 | 1.000 |
  | False refusal | 0.288 | 0.096 |
  | Correct refusal | 1.000 | 1.000 |
  | Router accuracy | 0.671 | 0.800 |

  - The 5 false refusals left come from the model or validation, none from the router:
    - insufficient evidence in the retrieved passages: x03, x05, x15;
    - no sentence held up after the regeneration: x06, x17.
  - Router misses with no refusal remain: no tickers for x06, x08 and x11 (an unscoped search), and absent questions routed out_of_scope.

## 2026-10-15: Router: out_of_scope decided by topic only

- **Change:** the prompt now says that only the topic decides out_of_scope, with the example "What was Apple's revenue in fiscal 2031?" (numeric, fiscal_years [2031]).
- **Why:** gpt-oss-20b routed "revenue in fiscal 2027" as out_of_scope. The time-trap check now refuses such a question by name instead (docs/memory.md).
