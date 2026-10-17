# Activity Log

Chronological record of significant development activity, newest first. Skip trivial changes. Do not auto-commit this file.

## Entry Format

```
### YYYY-MM-DD: <task performed>

- Changes: <important changes>
- Files: <relevant files>
- Validation: <tests or checks run and results>
- Outstanding: <open issues, or "None">
```

## Entries

### 2026-10-17: Fair Haiku comparison on Gemini's router replies; floors checked; answer limit documented

- Changes (user requests):
  - **`--router-primary`:** `evals/harness.py` gains `--router-primary=PROVIDER:MODEL`, which keys router calls as that primary's run did, so another answer model reuses its exact router replies. `answer_path` takes a `primary` override; runs without the flag keep their cache keys.
  - **Fair comparison:** the Haiku comparison was rerun on Gemini's router replies and replaces the earlier one in the README and eval card, which say why.
  - **Answer limit:** documented in context.md, the eval card and a comment on `MAX_TOKENS`: where it is set, why, and that Claude's thinking is off.
- Files: evals/harness.py, evals/tests/test_calls.py, packages/llm/src/filinglens_llm/answer.py, README.md, evals/eval-card.md, docs/*
- Validation:
  - `make test` 271 passed; ruff and pyright clean. The answer-path test now checks that a router path for another primary equals that primary's path.
  - **Fair run** (`20261017T084716Z`, `--router-primary=gemini:gemini-3.5-flash-lite --primary-tag=fair`, judge on):
    - All 30 router replies came from Gemini's run (0 gpt-oss-20b). Exit 0, 0 errors, 0 truncated.
    - Numeric 1.000, citation precision 0.958, faithfulness 0.944, false refusal 0.130 (the same 3 router calls).
    - Paired own first token p50 0.72 against 0.85 s.
    - Spent: $0.0145 in credits and 19.2K gpt-oss-120b.
    - Findings: n28 hedged over its "fiscal 2025 Q1" fact heading, and c12's comparison conclusion was rated "partly".
  - **Floors file:** `ttft_p50_ms` is 2428.95 on disk, so the reported 0 was a cut paste. Both TTFT floors follow the rule, so nothing changed.
  - **Spent today:** about 144K gpt-oss-20b and 75K gpt-oss-120b; Claude credits $0.106 across 4 runs.
- Outstanding: turning Haiku on in `.env` (user decision); the v2 ideas; step 7.

### 2026-10-17: Haiku thinking off, dev rerun, Haiku test comparison, floors written, api rebuilt

- Changes (user decisions):
  - **Claude:** thinking off at effort low (`CLAUDE_THINKING`), with the 1,024-token answer cap kept. The eval cache key and the report header carry the setting.
  - **Floors:** written from Gemini's test report (`--set-floors evals/reports/2026-10-17.json`). `evals/thresholds.json` holds `retrieval:test:full` (3 floors) and `answer:test:full:gemini:gemini-3.5-flash-lite` (13 floors).
  - **Docs:** the README and eval card carry the official Gemini table with CIs, a Haiku comparison column, every miss explained, and known weaknesses with v2 ideas.
  - **api:** rebuilt and restarted on this code.
- Files: packages/llm/src/filinglens_llm/providers.py, packages/llm/tests/test_providers.py, evals/harness.py, evals/thresholds.json (new), evals/eval-card.md, README.md, docs/*
- Validation:
  - `make test` 271 passed; ruff and pyright clean.
  - **Dev rerun** (`20261017T082532Z`, `--primary-tag=nothink`, router replies cached):
    - 0 truncated, 0 empty replies, 0 errors; false refusal 0.058 (n17, n24, x15).
    - Claude's own first token p95 1.08 s against 3.03 s with thinking on, paired.
    - Credits $0.0381; about 1K gpt-oss-20b.
    - n17 and n24 trace to fact headings that read "fiscal 2025 Q2" for year-end values from 2026 Q2 10-Qs (facts 460279, 557549).
  - **Haiku test, pinned, judge on** (`20261017T082950Z-answer-test-full`): exit 0, 0 errors.
    - Numeric 1.000, citation precision 1.000, faithfulness 0.979, false refusal 0.000, TTFT p50 1.58 s and p95 2.71 s.
    - The router routed x13, x14 and x18 as textual this time.
    - Credits $0.0177; Groq 33.2K gpt-oss-20b and 28.1K gpt-oss-120b.
  - **api:** healthy, `/readyz` ok; inside it, anthropic 1.15.0 with thinking disabled. `.env` keeps `AI_ENABLED=false` and no `LLM_ANSWER_FALLBACK`.
  - **Spent today:** about 144K gpt-oss-20b and 56K gpt-oss-120b; Claude credits $0.0912 across 3 runs.
- Outstanding: turning Haiku on in `.env` (user decision); the v2 ideas; step 7.

### 2026-10-17: Claude Haiku 5.5 as the answer's first fallback; one pinned dev run

- Changes (user request; decisions in memory.md):
  - **Provider:** `filinglens_llm.providers.Anthropic` on the official SDK (`anthropic` 1.15.0, which runs on httpx2, so it has its own client):
    - Adaptive thinking at effort low; text deltas only.
    - Credits gone (a 402, a 400 naming a spend limit or the credit balance, a 429 without Retry-After) turn it off for the rest of the credit period, with one warning line. The expiry date does too.
    - A 429 asking for 10 s or less is retried once.
    - A refusal fails the call.
    - `credits_usd` prices a call from its usage.
  - **Settings:**
    - `LLM_ANSWER_FALLBACK` (empty by default: the free-only chain), `ANTHROPIC_CREDITS_EXPIRE` (2026-11-10) and `ANTHROPIC_API_KEY`.
    - Claude cannot be `LLM_ROUTER` or `LLM_FALLBACK`, and `LLM_JUDGE` never Claude.
  - **Answers:** the answer chain is Gemini, Claude while it is on, NVIDIA; the router's chain is unchanged. `Usage.cost_usd` and the answer log carry the credits spent.
  - **Evals:**
    - Cost as billed comes from call usage, and Claude's effort joins its cache key.
    - The billed floor is $0 only on the free setup, and answer floors are keyed per primary model.
    - Report headers name each primary's real thinking setting.
    - `providers.json` has Haiku's price and limits.
  - **Config:** compose passes the three variables to the api; `.env.example` and the README are updated.
  - **Dependencies:** `anthropic` 1.15.0 (with docstring-parser and jiter), plus httpx2 and structlog declared for filinglens-llm (both already locked).
- Files: packages/llm (pyproject.toml, providers.py, tests/test_providers.py), packages/core (settings.py, tests/test_settings.py), services/api (answering.py, main.py, tests/test_answering.py), evals (harness.py, metrics.py, providers.json, tests/test_calls.py, eval-card.md), infra/docker-compose.yml, .env.example, uv.lock, README.md, docs/*
- Validation:
  - `make test` 271 passed (15 new); ruff and pyright clean; `make test-int` 28 passed (175 s).
  - `ANTHROPIC_API_KEY` is set in `.env` (checked without printing it).
  - Dev run with Haiku pinned, once, no tuning, no judge (`20261017T075734Z`, 07:44-07:57 UTC):
    - Exit 0, 1 error (x11: the Groq router answered 400).
    - Numeric 0.929, comparison 1.000, coverage 0.987, correct refusal 1.000, false refusal 0.115.
    - TTFT p50 1.58 s, p95 4.23 s.
    - Credits $0.0354 (60 calls, 243,295 in, 22,083 out); gpt-oss-20b 76.3K.
  - Breakage found: thinking uses up the 1,024-token answer cap. 4 answers were cut, and 3 regenerations came back with no text (3 false refusals). Also n17 and n24 answered INSUFFICIENT_EVIDENCE despite their fact.
- Outstanding (user review):
  - The cap fix, then a dev rerun with `--primary-tag`, then the Haiku test run.
  - Whether `.env` sets `LLM_ANSWER_FALLBACK`.
  - Rebuilding the api image with this code. It still runs `77e59a0`.

### 2026-10-17: 6b test day: follow-up spot check, rebuild, integrity checks, golden v1 test run

- Changes:
  - **Stack:** no code changes. All six of this project's containers had exited about 13 minutes before the session (exit 255, likely a Docker restart).
    - Postgres, Redis and RabbitMQ started first; every queue was empty, so the corpus freeze held.
    - api, ingest and embed were rebuilt from `77e59a0` and started; all healthy, `/readyz` ok.
  - **Follow-up import** (`make calibrate ARGS="followup import"`) wrote `evals/calibration/v1-followup/result.json`.
  - **Test run** (`make eval SUITE=all SPLIT=test`) wrote `evals/reports/2026-10-17.json` and `.md` and an `eval_runs` row.
- Files: evals/calibration/v1-followup/result.json, evals/reports/2026-10-17.json and .md, evals/eval-card.md, README.md, docs/todo.md, docs/memory.md, docs/context.md, docs/activity-log.md
- Validation:
  - **Follow-up spot check (07:17 UTC):** the judge failed 3 of the 4 sentences Claude labeled not supported and missed s04 (t07). It passed s06; s03 is unscored. 6 calls, 9.9K gpt-oss-120b.
  - **Integrity before the run:** commit `77e59a0`, `dirty` false, source sha256 `b238808a…` as expected. Calibration v1's four hashes and the golden manifest hash match. Golden v1 is frozen and the corpus check passed.
  - **Test run (07:24 UTC):** exit 0, 30 questions, 0 errors, 29 all-live.
    - Pass: numeric exact match 1.000, coverage 0.971, faithfulness 0.970, correct refusal 1.000, MRR@10 0.833, TTFT p95 1.84 s, answer p95 2.15 s, tokens and cost.
    - Fail: false refusal 0.130 (the router sent x13, x14 and x18 out of scope), citation precision 0.944 (c02's conclusion), recall@10 0.583 (n 6), TTFT p50 1.55 s.
    - Not measured: retrieval p95 at about 250k chunks.
    - Spent: 33.2K gpt-oss-20b, 17.9K gpt-oss-120b, 23 Gemini calls (one Gemini 429 waited 60 s).
  - **Floors:** the rule's values were computed without writing; `evals/thresholds.json` still does not exist. They are listed in todo.md.
- Outstanding: the user's review of the results and floors; the router's out-of-scope misses.

### 2026-10-16: gitleaks findings fixed at the source (cache digests named `key`)

- Changes:
  - **Cause:** the user's local commit was blocked by gitleaks (generic-api-key, about 1,600 findings). Every one was a JSON field named `key` holding a hex cache digest; no real key prefixes anywhere (checked by the user).
  - **Source fix:** `evals/calls.py` `Call.key` became `Call.cache_id`, so reports write `cache_id`. `evals/calibrate.py` reads `cache_id` from reports and writes it into calibration sample items.
  - **Existing files rewritten, field name only:**
    - 12 reports in `evals/reports/runs/` (1,595 fields).
    - `evals/calibration/v1/sample.jsonl` (5) and `evals/calibration/v1-followup/sample.jsonl` (6).
    - Each rewrite checked that the count matched the recorded calls or items, and that every value and every other field was unchanged.
- Files: evals/calls.py, evals/calibrate.py, evals/reports/runs/*.json (12), evals/calibration/v1/sample.jsonl, evals/calibration/v1-followup/sample.jsonl, docs/todo.md, docs/memory.md, docs/activity-log.md
- Validation:
  - `git add -A`, then the hook's scan (`python -m pre_commit run gitleaks`, gitleaks v8.30.1 on the staged changes):
    - After the report rename, 11 findings were left, all in the two calibration samples.
    - After their rename, the scan passed, with no `--no-verify` and no allowlist.
  - Both samples' failing items still find their drafts in the reply cache under `cache_id`.
  - `make test` 256 passed; ruff and pyright clean.
  - Calibration v1's `sample.jsonl` sha256 is now `aa128cde3808323d`; its other three files are unchanged.
  - New expected source sha256 after the user's commit: `b238808a9abff8a6c5273c93042127925b4f0d86268f04b93399aaa7a9f7b9f9`. The scheduled test-day prompt was re-created with it.
- Outstanding: the user's commit; the test day (2026-10-17, 15:07 Taipei).

### 2026-10-16: 6b: before the test day: router misses checked, code and prompt hashes in reports

- Changes:
  - **Router misses (user request, no quota):** compared against the rest on three dev runs. They are not clearly worse, so the deterministic fill was not built. The finding is in memory.md and context.md.
  - **`evals/harness.py`:** `code_version` and `prompt_hashes` go into every report (JSON, markdown header, `eval_runs` row). There is one unit test.
  - **Decision 4 write-up:** 4d (NVIDIA gpt-oss-120b) is noted as proposed and found retired (410), so not an option.
  - **Test run approved** with conditions (todo.md): the follow-up import first after 06:00 UTC, a rebuild of api, ingest and embed, integrity checks, the run, then the report against targets and floors.
- Files: evals/harness.py, evals/tests/test_calls.py, docs/todo.md, docs/memory.md, docs/context.md, docs/activity-log.md
- Validation:
  - `make test` 255 passed; ruff and pyright clean.
  - Golden v1 frozen and unchanged, and the corpus check passed (11:50 UTC). Calibration v1 hashes recorded in todo.md.
  - `--set-floors REPORT` (user request): it applies the floor rule to a saved report's measured values, latency included, and runs no longer write floors. A unit test covers the rule on a saved report, tightening, and a slower run that keeps the floor. `make test` 256 passed; no floors written.
  - The source hash now reads files with LF line ends, so a checkout that rewrites line ends keeps it.
  - `code_version` on the final code (about 13:00 UTC): commit 94c6ae3 with uncommitted changes, source sha256 5fb1384a86c0121f0d7849260a0c7893c295b349e2a56bf497fd2b0115413734 (119 files; data and docs left out). `dirty` checks only those files, so tomorrow's calibration import cannot mark the test run dirty. After the user's commit, the test run should record this hash with `dirty` false.
  - `evals/thresholds.json` does not exist: no floors were ever written. The test run writes none either (user decision).
  - The test day is moved to 15:07 Taipei (07:07 UTC), after Gemini's daily reset (user). A one-shot prompt is scheduled in this session; it fires only while the session stays open.
- Outstanding: the test day (2026-10-17 from 07:07 UTC); the user's commit on the evening of 2026-10-16.

### 2026-10-16: 6b: fix B (search with the router); decision 4 settled; follow-up labels; test run plan

- Changes:
  - **Fix B (user decision; fix A rejected):**
    - `router.guess` reads the tracked companies and years a question names.
    - `Answerer` starts that search before the router call and keeps it only when the plan's tickers and years match (`_Early`), so answers never change.
    - Stats and eval records carry `early_search`.
  - **Decision 4 (user decision):** NVIDIA gpt-oss-20b stays `LLM_FALLBACK`. 4c (Groq) was skipped. 4d (NVIDIA gpt-oss-120b) answered 410 to a tiny request, so it cannot run.
  - **Follow-up check:**
    - The import now reports a spot check, with no kappa (`spot_check`).
    - Claude's labels (2 y, 4 n) are in and fit the sample.
    - The eval card gives the written criterion (a computed number is not stated).
    - The s07 note is revised: the judge's reading was the correct one, Claude's v1 label was lenient, and v1 stays unchanged.
  - **TTFT miss** reported in the README and the eval card, with Gemini's drift and the 1.0 s that free tiers cannot reach with the stages in sequence.
  - **Later idea in todo.md:** a deterministic check for derived numbers.
  - **Test run plan:** Groq budget for 2026-10-17 in todo.md; it waits for the user's go.
- Files: packages/llm/src/filinglens_llm/router.py, packages/llm/tests/test_router.py, services/api/src/filinglens_api/answering.py, services/api/tests/test_answering.py, evals/harness.py, evals/calibrate.py, evals/tests/test_calls.py, evals/eval-card.md, evals/calibration/v1-followup/claude_labels.jsonl (from the user), evals/reports/runs/20261016T100134Z-answer-dev-full.json and .md, README.md, docs/todo.md, docs/memory.md, docs/context.md, docs/activity-log.md
- Validation:
  - `make test` 254 passed; ruff and pyright clean.
  - **Fix B offline:** the guess matched the router on 16 of 25 searching questions of 3a. All misses were the router leaving tickers empty.
  - **Fix B on dev, live:**
    - The router agreed on 18 of 28 searching questions.
    - On those, time before Gemini starts went from p50 1,060 to 684 ms (median paired −268 ms, 95% CI −490 to −128, n 16).
    - TTFT end to end: p50 3.72 s, p95 9.65 s, 3 errors (two Gemini 503s, one timeout). Groq: 77.5K gpt-oss-20b.
  - **Follow-up judge prompts sized offline:** 6 calls, about 8.7K input tokens.
- Outstanding:
  - The follow-up import (2026-10-17).
  - The test run (the user's go).
  - The API container still runs the code from before fix B until it is rebuilt.

### 2026-10-16: 6b: --tag and --compare timings; decision 3; decision 4a-4b; follow-up sample

- Changes:
  - **Harness (approved before the runs):**
    - `--tag=NAME` replaces `--refresh` (`answer_path`), and `Cache` lost its `refresh` flag.
    - `--compare` adds the primary call's own first-token and total times, p50 and p95, with both values printed.
    - Added for decision 3's drift control: `--primary-tag=NAME`, which gives only the primary new keys.
  - **Follow-up sample (user decision):** `make calibrate ARGS="followup export|import"` works on a second sample in `evals/calibration/v1-followup/`. It draws from 4b first, then 4a, never 4c (`draw_followup`, `latest_report`); v1 is untouched.
  - **Decision 3:** run A-B-A (minimal, default, minimal), because Gemini's latency had drifted since the morning. Thinking minimal stays.
  - **Decision 4a and 4b:** ci runs. 4a (NVIDIA gpt-oss-20b) leads 4b (nemotron). They were not too close to call, so no dev-full runs.
  - **Follow-up sample drawn:** 6 sentences (2 from nemotron, 4 from gpt-oss-20b), short of 10.
- Files: evals/calls.py, evals/harness.py, evals/calibrate.py, evals/tests/test_calls.py, evals/eval-card.md, evals/calibration/v1-followup/, evals/reports/runs/ (3 dev-full and 2 dev-ci answer reports), README.md, docs/todo.md, docs/memory.md, docs/context.md, docs/activity-log.md
- Validation:
  - `make test` 250 passed; eval tests 15 passed after `--primary-tag`; ruff and pyright clean. A test pins that an untagged answer path keeps its six fields, so earlier cache keys hold.
  - **3a** (`--tag=d3`, every call live): TTFT p50 4.24 s, p95 9.26 s; router 0.66 s, retrieval 0.30 s, Gemini first token p50 3.37 s. 2 Gemini 503s.
  - **3b against A2:** Gemini first token p50 −0.21 s (95% CI −0.86 to +0.63). The two minimal passes differed by −0.46 s. 12 and 7 errors, nearly all Gemini 503s.
  - Gemini's first token on the same 46 questions: p50 0.97 s at 05:56 UTC, 3.37 s at 09:00.
  - **4a:** 3 of 7 quotes passed; own first token p50 1.18 s; 0 errors.
  - **4b:** 1 of 1 quote passed; own first token p50 11.26 s; 3 answers past 30 s.
  - **Groq spent:** gpt-oss-20b 77.4K (3a) + 22.2K (4a) + 22.2K (4b), about 122K as planned; gpt-oss-120b 0.
- Outstanding:
  - Decision 3's fix (user decision).
  - 4c on 2026-10-17 from about 06:00 UTC, then decision 4.
  - The follow-up sample's size (6 of about 10, user decision), then Claude's labels and the import.
  - The test run.

### 2026-10-16: 6b: eval card additions; Groq budget plan for decisions 3-4

- Changes:
  - **Eval card (user request):**
    - Sensitivity with s30 counted as a disagreement: agreement 27 of 30, kappa 0.77 (95% CI 0.47 to 1.00).
    - The judge was tested only on constructed negatives. A follow-up check is planned: about 10 natural sentences that fail the validator, from decision 4's runs, labeled by Claude, then judged.
    - s19's "partly" is defensible. On s07 the judge is strict about comparisons derived from stated numbers, so faithfulness may be slightly understated.
  - **Plan in todo.md:** runs and Groq budget for decisions 3-4, the follow-up check and the test run.
    - FreightAudit's CI keeps 25K a day of gpt-oss-120b (user rule, memory.md Constraints).
    - The judge runs only in the follow-up check and the test run.
    - Nothing ran; the plan waits for the user's go.
  - **Found while planning:** `--refresh` would overwrite cached replies under the same keys (memory.md, Known Issues). The plan replaces it with `--tag`.
- Files: evals/eval-card.md, docs/todo.md, docs/memory.md, docs/context.md, docs/activity-log.md
- Validation:
  - The sensitivity figure uses `evals.metrics.cohen_kappa` and `bootstrap` (seed 20261016) on `result.json`. The same code reproduces the recorded 0.84 (0.59 to 1.00).
  - `uv run --env-file` keeps a variable already set in the shell (checked), so `LLM_PRIMARY=... make eval` picks a decision 4 candidate.
- Outstanding: the user's go on the plan, and whether FreightAudit uses gpt-oss-20b.

### 2026-10-16: 6b: judge calibrated; dev answer rerun with the splitter fix

- Changes:
  - `make calibrate ARGS=import` finished on its third try (08:18 UTC). `evals/calibration/v1/result.json` holds the result, which the eval card's new Result section reports.
  - The judge metrics now count in reports, since kappa is 0.84.
  - README, context.md and memory.md give the result with its caveat: every negative in the sample was constructed.
- Files: evals/calibration/v1/result.json, evals/reports/runs/20261016T082033Z-answer-dev-full.json and .md, evals/eval-card.md, README.md, docs/context.md, docs/memory.md, docs/todo.md, docs/activity-log.md
- Validation:
  - Calibration: 29 of 30 sentences scored (the judge's reply for s30 did not parse). Agreement 93.1%, kappa 0.84 (95% CI 0.59 to 1.00). Confusion: 19 both supported, 8 both not, 2 Claude supported and judge not, 0 the reverse. Natural sentences alone: agreement 90.5%, kappa 0.00 (Claude labeled all 21 supported).
  - Dev rerun (`make eval SUITE=answer SPLIT=dev ARGS="--min-relevance=-100"`, the router-v2 run's command): 0 errors, every answer call from the cache, one live judge call (x16).
    - False refusal 0.096 with the same five: insufficient evidence x03, x05, x15; no sentence held up x06, x17.
    - x16 keeps its whole sentence (no regeneration, judge yes).
    - Citation coverage 0.930 to 0.941.
    - Citation precision 0.981 and faithfulness 0.937 pass.
- Outstanding: decisions 3-4 and the test run.

### 2026-10-16: 6b: sentence splitter fixed for abbreviations; calibration import stopped again

- Changes:
  - `filinglens_llm.validate.split_sentences` (user request): a period after an abbreviation (initials such as U.S., e.g. or N.A., and Inc., Corp., Co., No., etc.) ends a sentence only when a common sentence starter follows (`ABBREVIATION`, `STARTER`). "the U.S. Government" stays whole, and "in the U.S. The rest" still splits. The function serves validation, the judge's sentence list, the coverage stat and the calibration draw.
  - 12 test cases in `packages/llm/tests/test_validate.py`, x16 included.
- Files: packages/llm/src/filinglens_llm/validate.py, packages/llm/tests/test_validate.py, evals/eval-card.md, docs/context.md, docs/memory.md, docs/todo.md, docs/activity-log.md
- Validation:
  - The new tests ran first against the old splitter: 8 of 12 failed (the other 4 guard real sentence ends). After the fix all passed. `make test` 248 passed; ruff and pyright clean.
  - Of the 62 cached drafts in the latest dev report, only x16 had a cut after an abbreviation. Offline (cache and database, no model calls), x16's draft now passes validation whole, with nothing removed.
  - None of the calibration sample's 30 sentences or 14 judge prompts change with the fix, so its cached judge calls still hold.
  - Groq at 07:00 UTC: one tiny request to gpt-oss-120b passed (889 of 1,000 requests left). `make calibrate ARGS=import` at 07:01 UTC then stopped on its first live call (429 with a Retry-After over 120 s, exit 2). 12 of the 14 judge calls are cached; s29 and s30 are left, about 4.5K tokens.
- Outstanding: rerun the import at 08:00 UTC or later, then the dev answer rerun with the fix, then decisions 3-4.

### 2026-10-16: 6b: calibration import attempted, stopped by Groq's daily token limit

- Changes:
  - `evals/calibrate.py`: `result.json` gains `natural`, the kappa with its CI, agreement, and the counts of not-supported labels from the labeler and the judge, over the 21 natural sentences.
  - `evals/calls.py`: the 429 rule depends on Retry-After (memory.md).
  - The eval card adds Claude's note (constructed negatives were easy, so the judge's score on them is likely generous) and the caveat that natural-only kappa rests on few negatives.
- Files: evals/calibrate.py, evals/calls.py, evals/eval-card.md, docs/memory.md, docs/todo.md, docs/activity-log.md
- Validation:
  - Eval tests: 13 passed; ruff and pyright clean.
  - `make calibrate ARGS=import` with `claude_labels.jsonl` (30 lines, 21 y, 9 n, labeler claude) stopped three times: twice on short 429s under the old rule, then on a Retry-After over 120 s. A minimal request still passed with 884 of 1,000 daily requests left, so the large prompts hit Groq's daily token limit.
- Outstanding: rerun `make calibrate ARGS=import` once the limit frees up (finished judge calls are cached), then report and fill in the eval card result.

### 2026-10-16: 6b: calibration export for Claude labels, import path

- Changes:
  - `evals/calibrate.py` gains `export` (`sample_for_labeling.jsonl`: id, question, sentence, cited passages with quotes; no verdict, no stratum) and `import` (`claude_labels.jsonl`, checked so that each id appears once with y or n and there is one labeler). `result.json` records the labeler and per-item labels and verdicts, and the harness note names the labeler.
  - `make calibrate` passes `ARGS`.
  - Constructed quotes are now a seeded span, not a passage's first words. The unlabeled sample was redrawn with the same 30 sentences and exported.
  - The eval card and README say that the judge is calibrated against labels by Claude, a different and stronger model than the judge, not by a human (user decision).
- Files: evals/calibrate.py, evals/harness.py, evals/tests/test_calls.py, evals/calibration/v1/sample.jsonl and sample_for_labeling.jsonl, evals/eval-card.md, Makefile, README.md, docs/memory.md, docs/todo.md, docs/context.md, docs/activity-log.md
- Validation: `make test` 236 passed; ruff and pyright clean. The export holds 30 rows with keys id, question, sentence and passages, and none of the words verdict, stratum, constructed or judge; 0 of 9 constructed quotes start their passage.
- Outstanding: Claude's labels (`claude_labels.jsonl`), then `make calibrate ARGS=import`.

### 2026-10-16: 6b: router v2, dev reruns, sweep, calibration sample

- Changes:
  - **Router v2 (user decision):**
    - The tracked companies (`Evidence.tracked`: those with an indexed filing) go in the prompt, with tickers as an enum in the schema and `other_companies` for untracked ones.
    - `router.problems` checks the reply, with one retry (`retry_prompt`); a ticker still unknown is refused as untracked, and a comparison needs a metric.
    - After the first rerun, `router.resolve` matches misfiled names to tracked tickers, and untracked companies are refused only when nothing tracked is named, or when their figures are needed.
    - Logged in the new `docs/prompt-log.md`, with the 2026-10-15 router change backfilled.
  - **Harness:** refusal causes (`refusal_cause`, `false_refusals`) appear in report notes and the sweep. Router scoring counts an untracked gold ticker as right in `other_companies`. The quota estimate uses the new prompt and schema.
  - **Calibration (option A, user decision):** 9 constructed negatives (a swapped citation, quoted from the swapped passage), shuffled in with the natural sentences.
    - The sample fills to 30 and dedupes sentences that a draft and its regeneration share.
    - It skips fragments after "U.S." and answers trimmed by validation.
    - The sample is drawn: 16 passing, 5 failing and 9 constructed, from 20 questions. The eval card describes it.
- Files: packages/llm/src/filinglens_llm/router.py, packages/llm/tests/test_router.py, services/api/src/filinglens_api/answering.py, services/api/tests/test_answering.py, scripts/record_llm_fixtures.py, evals/harness.py, evals/calibrate.py, evals/tests/test_calls.py, evals/eval-card.md, evals/calibration/v1/sample.jsonl, evals/reports/runs/ (4 dev answer reports), docs/prompt-log.md, docs/memory.md, docs/todo.md, docs/context.md, docs/activity-log.md
- Validation:
  - `make test` 235 passed; ruff and pyright clean; the golden manifest intact.
  - Dev reruns, gate off:
    - First router v2 run: false refusal 0.135, with 5 tracked companies misfiled as untracked.
    - After the code fixes: numeric and comparison match 1.000, correct refusal 1.000, false refusal 0.096, router accuracy 0.800, 0 errors (Gemini 503s and a timeout cleared on reruns).
  - Sweep: no feasible threshold, so -3.0 stays.
- Outstanding:
  - The user runs `make calibrate`.
  - The split_sentences "U.S." bug (decision pending).
  - Decisions 3-4 and the test run.

### 2026-10-16: 6b: label corrections and refreeze, the dev answer run, decision 2, calibration built

- Changes:
  - **Label corrections (user decision):** x01 `e9a636de` and x05 `de1c06bf` set to not gold; x02 `89cfdd9a` stays gold.
    - Recorded as `step: "correction"` rows with reasons, and logged in the eval card.
    - `blind_labels` now skips every row with a step. `audit_stats` adds `review_as_claude` (37) and `corrections` (2), and `final_as_claude` is now 39.
    - V1 was unfrozen and refrozen; only `labels.jsonl`'s hash changed.
  - **Wording (user decision):** "AI-labeled, spot-checked by a non-expert" in the README, the eval card, context.md, the manifest and the harness notes. The human check is described as a fast spot-check that cannot validate the labels on its own.
  - **Dev answer run:** `make eval SUITE=answer SPLIT=dev ARGS="--min-relevance=-100"`, the first run that spent quota. 70 questions, no errors, 12 rate-limit waits.
  - **Decision 2:** `--sweep` added (`refusal_sweep`, with a unit test). No threshold meets the rule, so `RELEVANCE_MIN` stays -3.0.
  - **Calibration:** `evals/calibrate.py` built (`make calibrate`, now with `--env-file .env`); the `label.py` stub is gone. The sample is not drawn: the dev run holds 1 failing sentence, not 10.
  - `load_sources` moved out of the answer suite for reuse.
- Files: evals/golden.py, evals/label.py, evals/harness.py, evals/calibrate.py, evals/tests/test_calls.py, evals/eval-card.md, evals/golden/v1/labels.jsonl and manifest.json, evals/reports/runs/20261016T055608Z-answer-dev-full.json and .md, Makefile, README.md, docs/context.md, docs/memory.md, docs/todo.md, docs/activity-log.md
- Validation:
  - Integrity after the refreeze: the manifest is frozen and its hashes match. An edited copy, a fake gold chunk, a changed fact and a changed fiscal year each exit 3. The final key differs from Claude's only at x02 `89cfdd9a` (152 gold passages), and `make audit` refuses.
  - `make test` 224 passed; ruff and pyright clean.
  - Dev run results:
    - Numeric exact match 0.821, comparison match 0.200, correct refusal 1.000, false refusal 0.288, router accuracy 0.671.
    - TTFT p50 1.8 s, p95 2.3 s.
    - Judge metrics shown but not counted until calibrated.
- Outstanding:
  - User decisions: router fixes (12 of 15 false refusals), and calibration negatives.
  - Then decisions 3-4 and the test run.

### 2026-10-16: 6b: golden set v1 spot-checked and frozen, eval harness, reranker decision

- Changes:
  - **Golden set v1:** 100 questions, with pools for 30 questions (543 passages; x15 got CAT's backlog chunk added). Labeled by Claude (`ai_labels.jsonl`), then spot-checked by the user, a non-expert, with `make audit`: a 60-passage blind sample plus x01's 19 passages, then a review of every disagreement.
  - **Audit results:**
    - Blind agreement 49.4% on 79 passages, Cohen's kappa 0.10 (95% CI -0.07 to 0.26).
    - 34 of the 40 disagreements had the user saying gold where Claude did not; 11 of those were on absent questions.
    - Pace: a median of 3 s per passage in the sample, and 47 s for the 40-decision review.
    - The review settled 37 on Claude's label. The 3 settled on the user's label (x01, x02, x05) are in the final key.
  - **Freeze:** `python -m evals.golden freeze` wrote the manifest (sha256 per file, the method, the audit numbers).
  - **Labeling docs:** written with the user's wording rules: AI-labeled, spot-checked by a non-expert, not human-verified, and the review not independent. They are in `evals/eval-card.md` (new), the README's new Evaluation section and memory.md.
  - **Harness:** `evals/harness.py` (rewritten from the stub), `evals/calls.py`, `evals/judge.py`, `evals/providers.json`, plus metrics in `evals/metrics.py`. It has a retrieval suite and an answer suite, a reply cache, run files, 429 handling, a quota estimate, a drift check, reports, floors, an `eval_runs` row per run and `--compare`. `make label` and `make audit` now refuse once the set is frozen.
  - **Decision 1 (dev):** three retrieval runs and a paired comparison. TinyBERT-L-2 over the top 50 stays the default; numbers are in memory.md.
- Files: evals/golden.py, evals/label.py, evals/metrics.py, evals/calls.py, evals/judge.py, evals/harness.py, evals/providers.json, evals/eval-card.md, evals/golden/v1/manifest.json, evals/reports/runs/ (3 retrieval reports), evals/tests/test_metrics.py, evals/tests/test_calls.py, README.md, docs/context.md, docs/memory.md, docs/todo.md, docs/activity-log.md
- Validation:
  - `make test` 223 passed; ruff and pyright clean.
  - Golden checks on scratch copies: an edited `questions.jsonl` exits 3. A fake gold chunk, a changed fact value and a changed latest fiscal year exit 3. The real files' hashes still match the manifest.
  - Answer suite dry run with scripted models on the dev database (7 questions): 15 live calls, then 0 on the resumed pass and 0 from the cache. The report and floors were written to a scratch folder.
  - Retrieval runs on dev: 3 reports and 3 `eval_runs` rows. Rerank latency was repeated in 3 alternating passes.
- Outstanding: the dev answer runs (decision 2 and the judge pass) spend model quota and wait for the user's go-ahead. Still to write: the threshold sweep, `make calibrate` and the test run.

### 2026-10-16: Before the 6a commit: Windows-only torch pin, gpt-oss-120b probe, first-token miss recorded

- Changes:
  - `packages/llm/pyproject.toml`: torch `>=2.12.0,<2.13` for `sys_platform == 'win32'` only, `>=2.12.0` elsewhere (user request). `uv lock --upgrade-package torch` changed only torch: Linux from 2.12.1+cpu to 2.14.1+cpu; Windows stays at 2.12.1, and uv resolved macOS to 2.12.1 too.
  - NVIDIA probe of openai/gpt-oss-120b (user request; the same answer call as the two-model test, gpt-oss-20b run again beside it): 410 Gone, end of life 2026-09-03, absent from the key's model list. gpt-oss-20b stays `LLM_FALLBACK`; its second run passed the format and the router schema, with 2 of 6 quotes passing `citation_error` (memory.md).
  - Docs: the first-token miss with its cause in context.md (Known Limitations) and as a 6b item in todo.md; a pitfall for retired NVIDIA models (a 410 ends in 502). Stale 6a lines fixed: context.md components, usage recording and status; README's 501 note and its dead-letter queues (`embed.dlq`).
- Files: packages/llm/pyproject.toml, uv.lock, README.md, docs/context.md, docs/memory.md, docs/todo.md, docs/activity-log.md
- Validation:
  - `make test`: 211 passed in 17.67 s.
  - `make dev` rebuilt the images; all six services healthy. The api and embed containers run torch 2.14.1+cpu (sentence-transformers 6.1.0). A search through the API ("supply chain risk", Apple): cold 6.03 s (model load), warm 0.19 s (embed 14 ms, SQL 10 ms, load 4 ms, rerank 161 ms), not degraded, top 3 hits from Item 1A.
  - `make test-int` not rerun: it runs on the host, where torch stays at 2.12.1.
- Outstanding: step 6b. A retired `LLM_FALLBACK` would end answers whose primary fails in 502 rather than 503 (memory.md).

### 2026-10-15: Step 6a: providers, local models, embed stage, hybrid search, answers

- Changes:
  - User decisions: Gemini `gemini-3.5-flash-lite` answers, Groq `openai/gpt-oss-20b` routes, NVIDIA NIM is the fallback (model chosen by a two-model test, pending); NVIDIA 402 is permanent (503); a failed router call routes with the fallback. Reranker: TinyBERT-L-2 over the fused top 50, whole chunks, after MiniLM-L-6 over 100 missed the target (p95 3,235 ms on this CPU); `RERANK_MODEL`, `RERANK_CANDIDATES`, `RERANK_MAX_TOKENS` are settings for 6b to tune.
  - `filinglens_llm`: `local` (pinned embedders and rerankers, bge query prefix, `make models`), `providers` (OpenAI-compatible client, Gemini adapter on google-genai with the key only in `x-goog-api-key`), `router` (strict JSON schema, metric table), `answer` (reply format with source-id markers renumbered 1, 2..., stream filter), `validate` (amount finder, per-sentence check), `budget.record_fallback`.
  - `filinglens_retrieval`: scoped vector and full-text candidates, RRF, rerank with a timeout (degraded), `facts.get_financial_fact` with the latest-filed rule.
  - Ingest: `embed` task and queue (`embed.dlq`), statuses parsed, embedded, indexed (facts indexes filings embedded before their fiscal year was known); job items succeed at embed; a separate `embed` compose service (`-Q embed,reembed -c 1`). `ingest` now consumes the other queues only.
  - API: `LiveBackend.search` (keyset over reranked hits, 409 on another index, a degraded cursor keeps the fused order), `answering.Answerer` (router, facts, retrieval, streamed draft, validation, one regeneration, refusals, fallback, in-flight cap), `AI_ENABLED` default false, contract additions (`Answer.refused`, `warnings`, search filters, 409).
  - Dependencies: sentence-transformers 6.1, torch 2.12.1 (pinned below 2.13: Smart App Control blocks `torch_python.dll` in 2.13 and 2.14; the CPU wheel index for Linux images), google-genai 2.31. Images about 2.1 GB.
  - `.env` line 46 (`SEC_USER_AGENT`) quoted; `uv run` and compose read the same 35-character value.
- Files: packages/core (settings, errors, queues, tests), packages/llm (local, providers, router, answer, validate, budget, tests), packages/retrieval (search, facts, tests), services/api (answering, backend, main, routes, schemas, graph, problems, tests, fixtures), services/ingest (pipeline, worker, tests), scripts (seed_real, record_llm_fixtures, smoke_answers), infra (compose, prod override), conftest.py, Makefile, .env.example, pyproject files, uv.lock, contracts/, clients/, docs/todo.md
- Validation so far:
  - Keys: `GEMINI_API_KEY` (AQ.) and `GROQ_API_KEY` listed models with 200 (2026-10-15 07:35 UTC); Groq headers: 1,000 requests/day, 8,000 tokens/min.
  - Embedding: `make seed-real` carried the 30 parsed filings through embed (61 SEC JSON requests, 0 documents): 11,263 chunks, 13.0 chunks/s in the embed container (8 torch threads). The first run failed every filing at the final status update (a CASE of untyped parameters for the enum column); fixed, `embed.dlq` replayed, all 30 indexed, 30 jobs succeeded.
  - Search in the API container (warm): embed 15-25 ms, SQL 5-110 ms, load 3-5 ms, rerank 128-182 ms; on-topic top scores 0.7-9.4, off-topic -10.6 and -10.9.
  - Recorded answers: numeric (fact cited, first token 1.9 s), textual (chunks quoted), out of scope and time trap refused.
  - `make contracts-breaking`: no breaking changes. A first `make test-int` had 2 failures (`test_limits.py` assumed AI on by default); fixed.
  - Three runs in a row: `make test` 211 passed in 18.1, 17.0 and 21.2 s; `make test-int` 28 passed in 171.2, 178.6 and 161.9 s. Afterwards two small changes (the smoke script's printing; facts shown in fixed point instead of 4.1616100E+11 in the prompt and the citation quote), then `make test` 211 passed again.
  - NVIDIA two-model test (user rule; numbers in memory.md): deepseek-v4.1-flash failed the format and the router schema (first token at 50.6 s); gpt-oss-20b passed both, with 2 of 5 quotes passing `citation_error`. gpt-oss-20b kept.
  - Live smoke run (`make smoke`, AI on, models loaded first; final run after the fixed-point change):
    - Numeric, "What was Apple's total revenue in fiscal 2025?": route numeric (revenue, 2025, AAPL); fact 37437, 416,161,000,000 USD, cited [1]; 963 in / 126 out tokens; route 675 ms, facts 46 ms, generate 1,405 ms, total 2,127 ms; first token 1,978 ms.
    - Textual, "What supply chain risks does Apple describe in its latest annual report?": route textual (AAPL); no warnings, so every quote passed `citation_error` (the first run printed its 6 citations with their quotes); 5,263 in / 586 out; route 531 ms, retrieve 269 ms (embed 38, SQL 17, load 13, rerank 171), generate 4,961 ms, total 5,767 ms; first token 3,831 ms (2,172 ms on the first run).
    - Unanswerable, "What was Apple's revenue in fiscal 2027?": refused, "Apple Inc. (AAPL) has filed no 10-K for fiscal 2027; its latest is fiscal 2025."; router only, 621 in / 62 out; total 727 ms.
- Outstanding: step 6b (golden set, judge, eval harness; reranker and refusal-threshold choices on the dev split). The textual first token (2.2-3.8 s) misses the p95 2.0 s target: the router (about 0.55 s) and Gemini's first token dominate.

### 2026-10-15: Step 5: tests (markers, network guard, property tests, load tests)

- Changes:
  - Setup: dev dependencies pytest-asyncio 1.4.0, respx 0.23.1 and hypothesis 6.155.7 (pinned below 6.156, whose Rust extension Application Control blocks). Markers `unit` (the root conftest adds it to every test without another marker), `integration` and `e2e`; `make test` runs `-m unit`. Integration tests keep Testcontainers (user decision).
  - `network_guard.py`: a lookup of any host but this machine raises at once, in pytest and in the worker and client processes that tests start.
  - Unit suite from 33.8 s to about 8 s, test-side only: dead dependencies at 0.0.0.0:1 (a closed 127.0.0.1 port takes 2 s to refuse on Windows), the production JSON log format in tests (rich tracebacks took 3.8 s for one 500), one uvicorn per contract-test module.
  - Pure functions for step 6: `filinglens_retrieval.reciprocal_rank_fusion` (k = 60, exact sums, ties by id) and `filinglens_llm.validate`: `citation_error` (quote and chunk normalized the same way, exact on words and digits; user decision), `parse_amount` (scale words, K/M/B/bn/T, accounting negatives, table scales; user request) and `amounts_match` (0.5%).
  - Tests: a chunker property test (hypothesis), RRF, citations, amounts, SecClient timeouts and headers (respx), the guard; integration tests for keyset pages over 100k chunks under concurrent inserts and for the embedding swap under API reads.
  - Todo: the search-cursor 409 and reranker-timeout tests, the Hugging Face offline note and the amount finder for answer text went into step 6; new items for CIK changes (after step 6) and financial-section headings (before step 9). AGENTS.md now says chunks are keyed by sha256(accession + section + offset).
- Files: AGENTS.md, Makefile, README.md, pyproject.toml, uv.lock, conftest.py, network_guard.py, packages/retrieval (src, tests), packages/llm (validate.py, tests), packages/sec_client/tests, services/api/tests (conftest.py, test_under_load.py), services/ingest/tests (run_worker.py, test_chunking.py, test_pipeline.py, test_probes.py), docs/*
- Validation:
  - `ruff check`, `ruff format --check` and pyright clean.
  - Three runs each: `make test` 127 passed in 7.86, 8.17 and 8.44 s; `make test-int` 23 passed in 105.21, 104.42 and 105.58 s (pytest's times; wall adds about 2 s). Before: 85 unit tests in 33.8 s, 21 integration tests in 82.7 s.
  - After the abbreviations: `make test` 139 passed in 8.42 s (9.9 s wall).
  - The keyset test runs at page size 100 with all 100k chunks in 24 s. With `>=` in place of `>` in `list_chunks` it fails (103,641 chunks returned, 102,605 distinct).
- Outstanding: step 6 builds the amount finder for answer text, search with the 409 cursor check, and the reranker timeout test.

### 2026-10-15: Step 4b: parse, chunk, XBRL facts and seed_real

- Changes:
  - New Celery tasks after fetch, all idempotent with the fetch task's retry, pause and dead-letter rules and their own dead-letter queues:
    - parse: inline XBRL HTML to text, item sections found by heading, the table of contents skipped by item order;
    - chunk: at most 384 bge-small tokens with 64 overlapping, using the model's vendored tokenizer through `tokenizers` (new dependency);
    - facts: whole companyfacts per company, plus each filing's fiscal year and period and their source.
  - Migration 0008 (dev now at 0008): `filings.fiscal_source` and `missing_items`, `sections.text`, `financial_facts.filed_on`, and the facts key with `cik` replacing the old one.
  - `SecClient` gained `companyfacts()`, `company_tickers()` and a per-kind request count in Redis.
  - The SEC cache is now a bind mount of the repo's `.cache/sec`, shared with host runs (`SEC_CACHE_DIR`).
  - `scripts/seed_real.py` (`make seed-real`).
  - User decisions: missing items stored and listed, with only a filing that has no required item failing; whole companyfacts; the `get_financial_fact` latest-filed rule recorded in memory.md; a company with only a 10-K/A stops the seed; XOM replaced by COP in the golden set after SEC moved the XOM ticker to a new holding company.
- Files: packages/sec_client, packages/core (queues.py), packages/db (models.py, migrations 0004 and 0008), services/ingest (pipeline.py, parsing.py, chunking.py, companyfacts.py, worker.py, tokenizer JSON, pyproject.toml, tests and fixtures), services/api/tests/test_app.py, scripts/seed_real.py, evals/golden-companies.csv, infra/docker-compose.yml, Makefile, .env.example, .gitignore, uv.lock, README.md, docs/*
- Validation:
  - Survey before the seed: the parser found every required item in the latest 10-K of each golden-set company (all 30, XOM included), in at most 2.1 s per document.
  - `make test` 85 passed. `make test-int` 21 passed, including `alembic check`, the swap from 0008, facts loaded twice (28 rows both times, fiscal year from companyfacts, fallback for a filing it lacks), and an unparseable filing failing only its own item with a rerun that downloads no document.
  - First `make seed-real` run: 30 jobs succeeded, 30 filings parsed, no required item missing. Chunks per 10-K: min 158, median 314, max 938; 11,263 in all. 856,438 facts. 91 SEC requests, 30 of them documents. 32 s.
  - Second run: 0 SEC requests, 0 documents downloaded, no rows added (6 s).
  - "supply chain risk" on Apple's chunks matched 5 chunks, all in Item 1A.
  - EXPLAIN of the latest-filed facts lookup used `uq_financial_facts_cik`.
- Outstanding: the old `filinglens_sec-cache` Docker volume is unused (not removed). Content in a separate financial section lands under the last item (known limit in memory.md).

### 2026-10-15: SEC limiter fails closed; a 403 after a cool-off fails the job

- Changes (user request):
  - Fails closed: without Redis, `SecClient` raises `LimiterUnavailableError` before any request. fetch and discover then send themselves again after a jittered 30 s pause, with the same task id and retry count, so an outage dead-letters nothing.
  - Attempts: `attempts` now counts tries that ran (a pause or a try killed mid-request does not).
  - Refusals: a 403 sets a strike beside its cool-off, and a 403 after that cool-off is a refusal. The reason goes to `sec:refused`, and every SEC call fails at once with `SecRefusedError` (not retried). The job's filings fail with the reason, which names SEC_USER_AGENT, and the job ends `failed`. A success clears the strike, a 429 always only cools off, and the worker clears the refusal on start.
- Files: packages/sec_client/src/filinglens_sec_client/__init__.py, services/ingest/src/filinglens_ingest (pipeline.py, worker.py), services/ingest/tests (test_pipeline.py, run_worker.py), README.md, docs/*
- Validation:
  - `make lint` and `make typecheck` clean. `make test`: 68 passed. `make test-int`: 19 passed.
  - Redis down: a worker on a dead Redis port paused the fetch more than 7 times, with no request to the fake SEC, no attempt, nothing dead-lettered and an empty `fetch.dlq`. Then a worker with Redis fetched it: 1 attempt, job `succeeded`.
  - Refused User-Agent: two filings answered 403 by every request. SEC saw exactly 2 requests (the 403 that cooled off and the 403 after it), and both filings failed with `SecRefusedError` naming SEC_USER_AGENT. The job was `failed` within seconds.
  - Client level: a 403, then a success, then a 403 is a throttle; a 403 after a cool-off is a refusal, and later calls fail without a request.
- Outstanding: None new.

### 2026-10-14: Step 4 workers (SEC client, discover and fetch, dead letters, backpressure, API limits)

- Changes:
  - Scope (user decisions): step 4 builds discover and fetch; parse, chunk, facts and `scripts/seed_real.py` move to a new step 4b; the job status `partially_failed` stays as the prompt's `completed_with_errors`; the 30 golden-set companies are an editable `evals/golden-companies.csv`.
  - `packages/sec_client`: the Redis token bucket (one Lua script on Redis's clock, 8 req/s, capacity 1) shared by every process; a cool-off key that pauses every process after a 403 or 429; the User-Agent from `SEC_USER_AGENT` (required, placeholder refused); 5 s connect and 30 s read timeouts; a gzipped disk cache.
  - `filinglens_ingest.pipeline`:
    - `discover` walks the submissions JSON and its older files one page at a time, skipping files older than the job's `since`.
    - `fetch` follows the prompt's settings, with retries on the unbounded `fetch.retry` queue. On final failure it writes a `dead_letters` row, marks the filing and item failed, and raises `Reject(requeue=False)`.
    - Queues come from `filinglens_core.queues`: dead-letter exchange `filinglens.dlx`, `fetch` limited to 10,000 with reject-publish. Publisher confirms are on, and discover queues itself again with backoff when a fetch publish is nacked.
  - `python -m filinglens_ingest.replay`.
  - Revision 0007 adds `ingest_job_companies`, so a job finishes once discovery and all its filings are done. 0007 slots in between 0003 and 0004, so the swap stays last and dev moves to `REV=0007`.
  - `LiveBackend` creates ingest jobs (idempotent; it queues discover with confirms) and reports them (counts plus a keyset page of failures).
  - API limits:
    - Redis token buckets per key: 60/min everywhere (GraphQL included), plus 10/min shared by both answers routes.
    - The AI switch and daily token budget (`filinglens_llm.budget`), which answer 503 `ai_unavailable`.
    - 413 over 64 KB, chunked bodies included.
    - A 30 s answer limit (502).
  - `TransientError` is the new base of the retryable errors.
  - Compose passes `SEC_USER_AGENT` and mounts a `sec-cache` volume for the worker, and passes `AI_ENABLED` and `DAILY_AI_TOKEN_BUDGET` to the API.
- Files: packages/core (errors.py, settings.py, queues.py, ratelimit.py, tests), packages/sec_client, packages/llm (budget.py, pyproject), packages/db (models.py, versions/0007_ingest_job_companies.py, 0004 parent), services/ingest (pipeline.py, topology.py, replay.py, worker.py, tests/test_pipeline.py, tests/run_worker.py, test_probes.py, test_embedding_swap.py), services/api (limits.py, backend.py, routes.py, main.py, problems.py, tests), contracts/openapi.json, clients/python, clients/ts, infra (docker-compose.yml, Dockerfile), .env.example, Makefile, evals/golden-companies.csv, pyproject files, uv.lock, README.md, docs/*
- Validation:
  - `make lint` and `make typecheck` clean. `make test`: 68 passed. `make test-int`: 17 passed.
  - The four done checks:
    1. 20 processes x 4 requests through the shared bucket. Over three measuring runs, the 9th request after any request arrived at least 0.983 s later at the fake server: ~16 ms of arrival jitter, against a 50 ms allowance in the test. Throughput was 7.9 req/s.
    2. A filing answering 503 every time was requested 7 times (first attempt plus `max_retries=6`), then landed in `fetch.dlq` (`x-death` reason rejected) and `dead_letters`, with the item failed after 7 attempts and the job `failed`. Replay then fetched it, and the job turned `succeeded`.
    3. With `fetch` at 10,000 messages, discover logged its back-off and left 30 items pending while the queue stayed at the limit. After a purge it queued all 50 filings of both pages exactly once. It never requested the older file that predates `since`.
    4. A worker killed mid-download had its message requeued and finished by a second worker: one row per filing, item and company, no dead letter, attempts 2.
  - Also covered: the cool-off pauses a second client; the cache serves repeat reads; the API's ingest jobs are idempotent, 422 on a reused key, and page their failures; 429 headers and per-key buckets; 503 at the budget and with `AI_ENABLED=false`; 413 with and without a length; the 502 timeout for answers and their stream.
  - `make codegen` regenerated `contracts/` and the clients (413 and 503 docs). `make contracts-breaking`: no breaking changes.
  - The api and ingest images build. A one-off ingest container (uid 10001) wrote to the new `sec-cache` volume and loaded the queues, confirms and routes. Compose refuses to start without `SEC_USER_AGENT`.
- Outstanding: the user's `.env` needs `SEC_USER_AGENT` before `make dev` (compose stops without it). Step 4b: parse, chunk, facts and `seed_real.py`. Nothing records LLM usage until step 6.

### 2026-10-14: Shared memory for parallel HNSW builds

- Changes: Postgres gets `shm_size: 256mb` in `infra/docker-compose.yml` and `infra/docker-compose.prod.yml`, and its prod memory limit rises from 1G to 1.5G (user decision). Compose also sets `PGUSER` and `PGDATABASE` for psql inside the container. New `make check-parallel-hnsw` runs `infra/check-parallel-hnsw.sql` on the dev stack: a throwaway database, 10k random 768-dimension vectors, and an HNSW build with two parallel workers and a 200 MB `maintenance_work_mem`. Runbook step 3 and the live-swap todo now cover choosing between a parallel build within the 256 MB and a serial one, and setting the values with `ALTER DATABASE` before 0005.
- Files: infra/docker-compose.yml, infra/docker-compose.prod.yml, infra/check-parallel-hnsw.sql, Makefile, scripts/seed_fake.py (comment), README.md, docs/migrations.md, docs/todo.md, docs/context.md, docs/memory.md
- Validation: `docker compose config` resolves `shm_size` to 268435456 bytes in dev and prod, and the prod memory limit to 1610612736 bytes, with the prod Postgres ports still unpublished. Control run of the same SQL in throwaway containers: Docker's default 64 MB failed ("could not resize shared memory segment ... to 206605824 bytes: No space left on device"), which shows the build ran in parallel; 256 MB passed in 2.5 s. Recreated the dev `postgres` service only (volume kept; api and ingest stayed up): `/dev/shm` is 256M, and `make check-parallel-hnsw` passed from Git Bash and from PowerShell.
- Outstanding: the live swap still has to choose the 0005 build settings once the corpus is measured.

### 2026-10-14: Dev path on model A until the live swap; COPY seed

- Changes: `make migrate REV=<revision>` (default head). `docs/migrations.md` documents the dev path (user decision): dev stays at 0003 on model A through steps 4-6, and after the step 6 evals the swap runs for real with recall@10 before and after. A todo item holds the live swap. Safety for that path: 0006 refuses to run while any chunk lacks `embedding_v2`; each revision commits in its own transaction; the ORM defers the `embedding_v2` columns; `.env.example` sets `RETRIEVAL_EMBEDDING_COLUMN=embedding`. `EMBEDDING_DIMENSIONS` joins `EMBEDDING_MODELS` in core. `scripts/seed_fake.py` now loads with psycopg COPY (psycopg 3.3.6 added to the dev group, user request), seeds each company separately, skips companies already loaded, fills every embedding column the schema has, and drops and rebuilds the HNSW indexes once inside its transaction.
- Files: Makefile, .env.example, README.md, packages/core/src/filinglens_core/settings.py, packages/db (models.py, migrations/env.py, versions/0006_drop_embedding_v1.py), scripts/seed_fake.py, services/api/tests/test_app.py, services/ingest/tests/test_embedding_swap.py, pyproject.toml, uv.lock, docs/*
- Validation: make lint and make typecheck clean; make test: 64 passed; make test-int: 7 passed. The swap test now checks that a stray `upgrade head` from 0004 commits 0005 and stops at 0006 with model A intact. The live paging test runs at 0003 and at head, seeds twice, and checks every chunk has a vector and the HNSW index was rebuilt. In a throwaway container with Docker's default 64 MB `/dev/shm`: the seed took 148 s at 0003 (384 dimensions) and 233 s at head (768), down from 779 s at head; a rerun took 0.8 s (was 124 s); counts matched; the planner chose the HNSW index unaided at both revisions (about 10 ms). A parallel HNSW build with 512 MB `maintenance_work_mem` failed at once ("could not resize shared memory segment ... No space left on device"), and the same build serially took 140 s.
- Outstanding: the live swap's 0005 build needs a larger postgres `shm_size` or a serial build (runbook step 3). The user's `.env` still lacks `RETRIEVAL_EMBEDDING_COLUMN=embedding` (manual todo).

### 2026-10-14: Step 3 data (schema, migrations, embedding swap, fake seed, live catalog reads)

- Changes: SQLAlchemy models and Alembic revisions 0002-0006. `companies` gains `sector`; new `filings` (status enum), `sections`, `chunks` (generated English tsvector, pgvector embedding), `financial_facts`, `ingest_jobs`, `ingest_job_items`, `dead_letters` and `eval_runs`; concurrent indexes (HNSW cosine, GIN, `(created_at, id)` keysets, chunk reading order, newest-first filings). `env.py` sets `lock_timeout` 5 s for every migration and gives migrations a 1 hour statement limit. Embedding swap from BAAI/bge-small-en-v1.5 (384) to BAAI/bge-base-en-v1.5 (768): expand 0004, Celery `reembed` task (batches of 256, keyset over chunk id, queues its own next batch, at most 60 a minute), concurrent HNSW 0005, `RETRIEVAL_EMBEDDING_COLUMN` (validated API setting) passed into `filinglens_retrieval.nearest_chunks`, contract 0006; runbook in `docs/migrations.md`. `filinglens_llm.embed` is a stub until step 6. `scripts/seed_fake.py` and `make seed-fake` (Faker 40.43 added to the dev group). `LiveBackend` now reads filings, sections, chunks and facts. User decisions: `seed_real.py` and the SEC client moved to step 4; models A and B as above; stub embedder.
- Files: packages/core (settings.py, tests), packages/db (models.py, __init__.py, migrations/env.py, versions/0002-0006), packages/retrieval, packages/llm, services/ingest (reembed.py, worker.py, tests/test_embedding_swap.py), services/api (backend.py, tests/test_app.py), scripts/seed_fake.py, conftest.py, pyproject.toml files, uv.lock, Makefile, .env.example, infra/docker-compose.yml, README.md, docs/*
- Validation: make lint and make typecheck clean. make test: 64 passed. make test-int: 6 passed. They cover the migration round trip from empty with `alembic check`, and the swap: model A data at 0003, expand, downgrade to 0003 with the data intact, reembed, 0005, EXPLAIN showing `Index Scan using ix_chunks_embedding` or `ix_chunks_embedding_v2` for each flag value with the exact nearest chunk, contract 0006, EXPLAIN again. Reembed ran batches of 256, 256 and 88, resumed from the cursor through the eager Celery task, and caught up one new chunk. `LiveBackend` paged seeded filings (with filters), sections, chunks (reading order, section filter, 400 for an unknown cursor chunk) and facts after seeding twice. Mutation check: an ORDER BY the index cannot serve made the EXPLAIN test fail. In a throwaway container: `alembic upgrade head` through the CLI from empty (1.2 s) and `alembic check` passed; `scripts/seed_fake.py` took 779 s for 200 companies, 2,000 filings, 10,000 sections, 100k chunks and 6,000 facts; the rerun took 124 s and left the counts unchanged; at 100k chunks the planner chose the HNSW index unaided (7 ms for 10 neighbours, index 391 MB); a vector read back through the ORM had 768 values and norm 1.0. Celery registers `filinglens_ingest.reembed.reembed` (60/m, late acks). The exported OpenAPI contract is unchanged, and `docker compose config` passes.
- Outstanding: `seed_real.py` and the SEC client (step 4). The embedding provider (step 6): until then `reembed` fails outside tests. `LiveBackend.search` reads the flag in step 6. The dev compose Postgres was not touched: `make migrate` still waits on the `.env` `API_KEY` line (manual item), and the running api and ingest containers keep the old image until `make dev`.

### 2026-10-14: Step 2 contracts (REST v1, GraphQL, generated clients, drift and breaking-change checks)

- Changes: REST v1 with pydantic models and explicit response models: ingest jobs (admin key, required Idempotency-Key, 202 with Location), companies, filings, search, answers and a Server-Sent Events answer stream; keyset pagination with opaque cursors. Errors are RFC 9457 problems with taxonomy codes; 429 and 503 headers are documented and emitted. Two keys (`API_KEY`, `ADMIN_API_KEY`: 401 missing or wrong, 403 normal key on admin routes) declared as security schemes (user decision). Routes call a `Backend` protocol: companies come from Postgres, the rest answer 501 until their step (user decision). Strawberry types with Relay connections, exported with `strawberry export-schema`. Codegen now builds four clients: openapi-python-client, ariadne-codegen (isolated env), openapi-typescript with openapi-fetch, and the graphql-codegen client preset. New `make contracts-check` and `make contracts-breaking` (oasdiff in Docker). Unexpected errors are answered in the request-id middleware, so a 500 no longer drops the keep-alive connection. `.gitattributes` keeps generated files LF. `ADMIN_API_KEY` added to settings, compose and `.env.example`; a random value was appended to the local `.env`.
- Files: packages/core (errors.py, settings.py, tests), services/api/src/filinglens_api (main.py, __main__.py, contracts.py, schemas.py, problems.py, backend.py, routes.py, graph.py), services/api/tests (conftest.py, test_app.py, test_contract.py), contracts/*, clients/* (openapi-python-client.yaml, operations.graphql, python, python-graphql, ts), Makefile, pyproject.toml, uv.lock, .gitattributes, .env.example, infra/docker-compose.yml, README.md, docs/context.md, docs/memory.md, docs/todo.md
- Validation: `make codegen` ran with no generator warnings, and `tsc` passed on clients/ts. make lint and make typecheck clean. make test: 64 passed, 39 of them contract tests through the generated clients against the app served by uvicorn. make test-int: 3 passed, including companies paged from a real Postgres through the generated client. oasdiff against main: no breaking changes (14 info). In a scratch copy committed to git, `make contracts-check` passed; after renaming a response field and lowering a page limit there, `make contracts-breaking` failed with 3 errors. In this tree `make contracts-check` fails as expected while the new files are uncommitted. `make dev`: stack healthy on the new image; through the generated client every route answered as designed (probes 200, stubs 501, 401 without a key, 403 for `API_KEY` on admin routes, 422 for limit=101). No key values in the API logs.
- Outstanding: line 34 of `.env` sets `API_KEY` to the generator command instead of its output, so `uv run --env-file .env` (make migrate, make seed) cannot parse the file. The compose Postgres has no tables, so the live `/v1/companies` returns 500 until `make migrate` and `make seed` run. CI wiring of both checks is part of step 7.

### 2026-10-14: Checked that the API key is header-only

- Changes: None in code; the API already read the key only from `X-API-Key` (`APIKeyHeader`). Added a test case proving a valid key in the URL (`/graphql?api_key=...`) gets 401.
- Files: services/api/tests/test_app.py, docs/context.md, docs/memory.md
- Validation: Against the running API, `/graphql?api_key=<key>` and `?X-API-Key=<key>` returned 401 for POST and GET, the header returned 200, and `/healthz` and `/readyz` returned 200 without a key. make test: 13 passed; make lint and make typecheck clean.
- Outstanding: None.

### 2026-10-14: Step 1 completed against the full prompt (readiness, structlog, prod override)

- Changes: The rest of the step 1 prompt arrived (it had been cut off after "Add a gitleaks pre-commit"); only the missing parts were added. API `/readyz` now also checks RabbitMQ. Logging moved to structlog: JSON lines with `request_id` (a validated `X-Request-ID` or a new uuid4, echoed in the response), level from `LOG_LEVEL`, and redaction of credential-named fields and the API key value; uvicorn, Celery and Alembic records included. Bad settings now exit with `Invalid configuration: <VAR>: <reason>`. Added `infra/docker-compose.prod.yml` (no published Postgres, RabbitMQ or Redis ports; `restart: unless-stopped`; memory limits), and dev containers no longer restart. `.env.example` gained `COMPOSE_FILE` so plain `docker compose` works from the root, and dropped `HEALTH_PORT` (the worker probe stays inside its container). Confirmed that `httpx2` is the client Starlette's docs recommend.
- Files: packages/core (settings.py, tests), packages/telemetry (__init__.py, tests), packages/db/src/filinglens_db/seed.py, services/api (main.py, __main__.py, tests), services/ingest/src/filinglens_ingest/worker.py, conftest.py, infra/docker-compose.yml, infra/docker-compose.prod.yml, .env.example, pyproject.toml files and uv.lock (structlog, kombu), README.md, docs/context.md, docs/memory.md, docs/todo.md
- Validation: `uv sync` ok. make lint and make typecheck clean. make test: 12 passed. make test-int: 2 passed (now with a RabbitMQ container). `make dev` and plain `docker compose up -d`: all services healthy. `/readyz` reported Postgres, RabbitMQ and Redis ok. The worker logged "Connected to amqp://filinglens:**@rabbitmq:5672//". An access log line carried `request_id` and showed the API key as `[REDACTED]`. Without `API_KEY`, compose refused ("required variable API_KEY is missing a value") and the api container exited 1 with "Invalid configuration: API_KEY: Field required". With no settings, the worker exited 1 naming DATABASE_URL, REDIS_URL and BROKER_URL. The prod override ran healthy with no host ports on the data stores, restart policies and memory limits set. `docker compose ps` showed every host port on 127.0.0.1, matching the Local ports table.
- Outstanding: None new. The Ryuk note in `docs/memory.md` still applies.

### 2026-10-14: Step 1 scaffolding (uv workspace, compose stack, health probes, production foundations)

- Changes: uv workspace on Python 3.12. `services/api` (FastAPI + Strawberry, API key on `/graphql`) and `services/ingest` (Celery on RabbitMQ). `packages/core` (pydantic-settings validated at startup, error taxonomy), `packages/db` (async SQLAlchemy, Alembic revision 0001, idempotent seed) and `packages/telemetry` (JSON logs). `retrieval`, `llm` and `sec_client` are skeleton packages. Compose project `filinglens` with pinned images, ports on 127.0.0.1 from `.env`, and `observability` and `test` profiles. One Dockerfile builds a non-root image per service. Makefile targets dev, down, test, test-int, lint, typecheck, migrate, seed, codegen and eval. Contracts are exported to `contracts/` and clients generated into `clients/`. Minimal Next.js `web/`. gitleaks pre-commit hook.
- Files: pyproject.toml, uv.lock, .python-version, Makefile, .env.example, .gitignore, .dockerignore, .pre-commit-config.yaml, conftest.py, packages/*, services/*, infra/*, contracts/*, clients/*, web/*, evals/harness.py, README.md, docs/migrations.md
- Validation: make lint and make typecheck clean (pyright strict on `packages/*/src`). make test: 11 passed. make test-int: 2 passed. make dev: all services healthy. make migrate, then make seed twice: 6 rows. make codegen ran. curl checks: api `/healthz`, `/readyz`, `/graphql` (401 without key, 200 with key); ingest probes; web `/healthz` and `/readyz`. Observability profile end to end: a test span reached Jaeger, Prometheus scrapes the collector, Grafana has both datasources. gitleaks blocked a staged fake token and found no leaks in the files to commit. Make recipes work from both cmd.exe and Git Bash.
- Outstanding: the step 1 prompt was cut off after "Add a gitleaks pre-commit"; the remaining foundations follow AGENTS.md. Domain models move to step 3, the eval harness to step 6. Testcontainers' Ryuk reaper publishes a random port on 0.0.0.0 during `make test-int`.

### 2026-10-14: Plan updated for free-tier models, production readiness, and deployment

- Changes: Switched to free-tier LLMs and local embeddings behind a provider switch, added production-readiness requirements, added steps 9 (review UI) and 10 (deploy).
- Files: AGENTS.md, docs/context.md, docs/memory.md, docs/todo.md
- Validation: Documentation only. No code changed.
- Outstanding: See docs/todo.md.

### 2026-10-13: Project created from template

- Changes: Copied `_project-template`, filled project-specific rules in `AGENTS.md`, added `CLAUDE.md` importing `AGENTS.md`, recorded design in `docs/context.md`, decisions in `docs/memory.md`, build plan in `docs/todo.md`.
- Files: AGENTS.md, CLAUDE.md, README.md, docs/*
- Validation: Documentation only. No code to test.
- Outstanding: None.
