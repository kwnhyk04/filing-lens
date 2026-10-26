# Prompt Log

Every change to a model prompt or response schema, newest first. Each entry gives what changed, why, the evidence and the result. Prompts are tuned on the golden set's dev split only, and the test split is never read for tuning. The judge prompt (`evals/judge.py`) is frozen with its calibration, so a change to it needs a new calibration.

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
