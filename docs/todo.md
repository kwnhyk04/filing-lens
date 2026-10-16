# To-Do

Concise, verifiable tasks. Move items between sections as status changes. Trim old completed items when the list grows large; the activity log keeps the history.

Each step maps to a Claude Code prompt in the design doc. Done when the check after the colon passes.

## Pending

- [ ] (manual, before step 7) GitHub repo created; provider keys added as Actions secrets.
- [ ] (manual, before step 10) Vercel and Tailscale accounts created.
- [ ] (manual, before step 10) Replace the example passwords in `.env`, and set both `API_KEY` and `ADMIN_API_KEY` (step 2 appended a random `ADMIN_API_KEY`).
- [ ] (manual, optional) Remove the unused Docker volume `filinglens_sec-cache` (`docker volume rm filinglens_sec-cache`); the SEC cache now lives in `.cache/sec`.
- [ ] Live embedding swap (after step 6; user decision): with dev on the last revision before 0004 (now 0008), record the model A baseline (`make eval`, recall@10 and MRR@10, golden set version); run 0004, the reembed backfill, 0005 (run `make check-parallel-hnsw` first, then pick a parallel build within the 256 MB `shm_size` or a serial one with more `maintenance_work_mem`, by corpus size; runbook step 3), the catch-up run and the flip to `embedding_v2`; run `make eval` again on the same golden set; record both runs in `eval_runs` and the activity log; then run 0006 in the next release and set `.env.example` to `embedding_v2`. Done when both recall@10 values are recorded and dev is at head. Runbook: `docs/migrations.md`.
- [ ] (later idea, user, 2026-10-16) A deterministic check for derived numbers: recompute a percent of a stated total, or the difference of two cited figures, from the cited figures themselves, so correct arithmetic can pass validation and wrong arithmetic gets caught. Today validation rejects every derived figure (memory.md, step 6a), and the judge criterion counts a computed number as not stated.
- [ ] (after step 6) Decide how a company that changes CIK in a restructure is handled (for example a `cik_aliases` table), since `get_financial_fact` looks facts up by CIK. Known case: XOM (Exxon Mobil Corp, CIK 34088, filed the latest 10-K; SEC now lists the ticker under ExxonMobil Holdings Corp, CIK 2115436).
- [ ] 7. CI/CD: GitHub Actions for test, build, docker push; actionlint passes; test PR green. CI also runs `make contracts-check` and `make contracts-breaking BASE=origin/main` (fetch main first).
- [ ] 8. Instrumentation: OpenTelemetry traces span services end to end; dashboard and alerts committed; screenshots saved
- [ ] (before step 9) Chunks from a separate financial section (JPM, CVX, NVDA, PLD, XOM) are labeled with the last item (15 or 16). Detect the MD&A and financial-statement headings inside that section and label those chunks Items 7, 7A and 8, so citations show the right section.
- [ ] 9. Review UI and demo mode: resolvers, login, backend-for-frontend, demo snapshot shown when the backend is offline; Playwright tests pass. The BFF uses `clients/ts` (`createApiClient`, `executeGraphql`) with `API_KEY` only.
- [ ] 10. Deploy: UI on Vercel, backend on the PC via Tailscale Funnel; phone test passes; 401 without API key; demo mode when the PC is off

## In Progress

- [ ] 6b. Golden set v1, judge calibration, eval harness and the full eval (plan approved 2026-10-16). Done when labeling and calibration are complete, the full eval runs on the test split, the report lists every target in `docs/context.md` with pass, fail or not measured, and `make test` and `make test-int` stay green.
  - **Corpus freeze (user request, 2026-10-16):** run no `make seed-real` and queue no ingest jobs until golden v1's test run is done. Apple's FY2026 10-K lands around 2026-10-30, and the harness's drift check (gold chunk ids, fact ids and values, each company's latest fiscal year) would then stop every run.
  - [x] Phase 1: 410 treated like 402 (permanent, 503); `Answerer(min_relevance=)` and `Gemini(minimal_thinking=)` keyword arguments; answer stats `sources` and `top_score`; `make eval` with `--env-file .env`, `make label`, `make calibrate`; `LLM_JUDGE=groq:openai/gpt-oss-120b` (user decision) for evals only.
  - [x] Golden set v1 draft (`python -m evals.golden build`, 2026-10-16): 40 numeric, 20 textual, 15 comparison, 15 unanswerable (10 absent from the filings, 3 out of scope, 2 untracked companies), 10 time traps; 70 dev and 30 test, a 20-question ci subset; 542 candidates in the pools (30 questions); labeler `make label`.
  - [x] Labeling method changed (user decision, 2026-10-16): AI-labeled (Claude, all 543 pooled passages in `ai_labels.jsonl`), spot-checked by a non-expert. The user labeled x01's 19 passages by hand. x15 kept, with CAT's "Order Backlog" chunk added to its pool (the pool had missed it; Claude labeled it gold). `make audit` built; its 60-passage blind sample is drawn (`audit.jsonl`: 23 Claude-gold, 29 questions).
  - [x] Spot-check (`make audit`, user, 2026-10-16): 79 blind passages, agreement 49.4%, kappa 0.10 (95% CI -0.07 to 0.26); 40 disagreements reviewed, 37 settled on Claude's label. Written into `evals/eval-card.md`, the README and memory.md as "AI-labeled, spot-checked by a non-expert": a fast spot-check that cannot validate the labels on its own, not human-verified.
  - [x] Golden v1 frozen (`python -m evals.golden freeze`, 2026-10-16): the manifest holds the sha256 of each file, the method and the spot-check numbers.
  - [x] Two label corrections by the user (2026-10-16): x01 `e9a636de` and x05 `de1c06bf` set to not gold after reading the passage text; x02 `89cfdd9a` stays gold. Recorded as `step: "correction"` rows with reasons and logged in the eval card. V1 was unfrozen and refrozen before any test run. The integrity checks rerun: an edited copy and each drift case exit 3, and the real files match the manifest.
  - [x] Harness (`make eval`, 2026-10-16):
    - Retrieval and answer suites, a call cache and run files, the judge, bootstrap intervals, reports, floors and a quota estimate.
    - Exit codes 1 (floor), 2 (quota or refused key) and 3 (golden set or corpus changed).
    - Checked without quota:
      - `make test` 223 passed, with lint and pyright clean.
      - An edited copy of `questions.jsonl` exits 3.
      - A fake gold chunk, a changed fact value and a changed latest fiscal year each exit 3.
      - A dry run of the answer suite with scripted models on the dev database made 7 router, 4 primary and 4 judge calls live; the resumed pass and the cache-only pass then made none.
  - [x] Decision 1, reranker (dev, 2026-10-16): TinyBERT-L-2 top 50 stays.
    - The quality tie with MiniLM-L-2 top 24 (MRR +0.071, CI -0.060 to +0.208) goes to the faster one, which is TinyBERT: rerank p95 162 against 184 ms over three passes.
    - MiniLM-L-6 is ineligible at a rerank p95 of 3,065 ms.
    - Numbers in memory.md.
  - [x] Decision 2, refusal threshold (dev, 2026-10-16):
    - The gate-off run with its judge pass: 70 questions, no errors, no quota stop.
    - `--sweep` result: no threshold meets the rule, because false refusal is 0.288 with the gate off (router and model refusals) while correct refusal is already 1.000. `RELEVANCE_MIN` stays -3.0, which adds no false refusal on dev. Numbers in memory.md.
  - [x] Router v2 (user decision, 2026-10-16; `docs/prompt-log.md`):
    - The tracked companies go in the prompt, as a ticker enum, with `other_companies` for untracked ones.
    - One retry and code validation; a comparison needs a metric; names are matched in code.
    - Dev rerun, gate off: false refusal 0.096 (model 3, validation 2), numeric and comparison match 1.000.
    - The sweep again finds no feasible threshold, so `RELEVANCE_MIN` stays -3.0.
  - [x] Calibration sample drawn (option A, user decision): 21 natural (16 pass, 5 fail the validator) and 9 constructed negatives, frozen in `evals/calibration/v1/sample.jsonl`. The eval card describes it.
  - [x] Calibration export (user decision, 2026-10-16: Claude labels in another chat): `evals/calibration/v1/sample_for_labeling.jsonl` (30 sentences, no verdicts or strata). The import is built (`make calibrate ARGS=import`).
  - [x] `make calibrate ARGS=import` (2026-10-16, third try at 08:18 UTC; Groq's daily token limit had stopped the first two):
    - 29 of 30 sentences scored; the judge's reply for s30 (x08) did not parse.
    - Agreement 93.1%, kappa 0.84 (95% CI 0.59 to 1.00), so citation precision and faithfulness count.
    - Natural sentences alone: agreement 90.5%, kappa 0.00, since Claude labeled all 21 supported.
    - 2 disagreements (s07 c06, s19 x01), both judge "partly" against Claude "supported".
    - Result in the eval card.
  - [x] `split_sentences` fixed (user request, 2026-10-16): a period after an abbreviation (initials such as U.S. or e.g., and Inc., Corp., Co., No., etc.) ends a sentence only before a sentence starter such as The or It. 12 unit tests, x16 included. x16's cached draft now passes validation whole. None of the calibration sample's 30 sentences or 14 judge prompts change.
  - [x] Dev answer rerun with the splitter fix and the calibrated judge (gate off, 2026-10-16, report `20261016T082033Z-answer-dev-full`): all answer calls from the cache, one live judge call (x16).
    - False refusal 0.096, the same five: insufficient evidence x03, x05, x15; no sentence held up x06, x17.
    - x16 keeps its whole sentence. Citation coverage 0.930 to 0.941.
    - Citation precision 0.981 and faithfulness 0.937 now count and pass.
  - [x] Eval card additions (user request, 2026-10-16):
    - The s30 sensitivity: counted as a disagreement, kappa 0.77 (95% CI 0.47 to 1.00).
    - The judge was tested only on constructed negatives, and a follow-up check is planned.
    - s19's "partly" is defensible. On s07 the judge's reading is the correct one under the written criterion, and Claude's v1 label was lenient (revised the same day; v1's labels stay unchanged).
  - **Plan for decisions 3-4, the follow-up check and the test run (2026-10-16): approved by the user the same day, without extra dev-full runs unless 4a and 4b are too close to call.**
    - **Groq budget (user rule; memory.md, Constraints):**
      - FreightAudit's CI keeps about 25K tokens a day of gpt-oss-120b, so FilingLens spends at most 175K of it in any 24 hours.
      - The judge runs only where a decision depends on it: the follow-up check and the test run. Decisions 3 and 4 run with `--no-judge`.
      - Estimates come from report `20261016T082033Z-answer-dev-full`. Router: 1,106 tokens a call. Judge: 643 (numeric), 1,139 (comparison) or 2,222 (textual) a call.
      - The gpt-oss-120b primary estimate uses Gemini's prompt sizes on ci, plus up to 1,024 output tokens a call. The high end assumes every draft with chunk quotes is regenerated.

      | Run | gpt-oss-20b | gpt-oss-120b | Judge | When (UTC) |
      | --- | --- | --- | --- | --- |
      | 3a | 77K (spent 77.4K) | 0 | no | 2026-10-16 |
      | 3b | 0 | 0 | no | 2026-10-16 |
      | 4a | 22K (spent 22.2K) | 0 | no | 2026-10-16 |
      | 4b | 22K (spent 22.2K) | 0 | no | 2026-10-16 |
      | 4c | skipped (user decision) | - | - | - |
      | Follow-up check | 0 | now about 11K (6 sentences) | yes | 2026-10-17 |
      | Test run | 33K | about 22-33K | yes | 2026-10-17, after the user's go |

      Added later the same day: A2 (decision 3's drift control, 0 Groq) and fix B's dev run (spent 77.5K gpt-oss-20b).

      - Times come from refill arithmetic, because Groq shows no daily token level. gpt-oss-120b was nearly empty at 08:21 UTC on 2026-10-16. A run that hits a long Retry-After exits 2 and resumes on a rerun.
      - FreightAudit uses gpt-oss-120b and qwen3.8-27b on Groq, not gpt-oss-20b, and Groq limits are per model (user, 2026-10-16). FreightAudit's CI runs about 10:30-11:00 UTC on 2026-10-16 (20-25K of gpt-oss-120b), so 4c waits for 2026-10-17 from about 06:00 UTC.
    - [x] **Before the runs (no quota, 2026-10-16):**
      - `--tag=NAME` replaces `--refresh`. NAME joins the answer path (`answer_path`), so the run's router and primary calls get their own cache keys and run live once. A rerun with the same NAME resumes and reuses them. `Cache` lost its `refresh` flag. Why: memory.md, Known Issues (the `--refresh` overwrite).
      - `--compare` adds paired timings of the primary call itself: first token and total, p50 and p95. It also prints both values.
      - Added for decision 3's drift control: `--primary-tag=NAME` gives only the primary new keys, so router replies come from the cache (0 Groq tokens).
      - `make test` 250 passed; ruff and pyright clean.
    - [x] **Decision 3, time to first token (dev full, 2026-10-16, 09:00-09:25 UTC):** thinking minimal stays; numbers in memory.md.
      - Ran A-B-A because Gemini drifted: 3a `--tag=d3` (minimal, every call live), 3b `--tag=d3 --thinking=default`, A2 `--tag=d3 --primary-tag=r2` (minimal). Groq: 77K gpt-oss-20b (3a only).
      - 3a end to end: TTFT p50 4.24 s, p95 9.26 s. Stage p50: router 0.66 s, retrieval 0.30 s, Gemini's own first token 3.37 s.
      - Default against minimal (A2): Gemini first token p50 −0.21 s (CI −0.86 to +0.63). The two minimal passes differed by −0.46 s. Default added no output tokens.
      - Gemini 503s: 2, 12 and 7 errors in the three passes.
    - [x] **Decision 3 fix (user decision, 2026-10-16): fix B, the search starts while the router runs;** fix A (hedging with the fallback) rejected. Numbers in memory.md.
      - `router.guess` plus `_Early` in `answering.py`: the early search is kept only when the router's tickers and years match the guess, so answers never change. Tests: the guess, a kept early search, and a router that disagrees getting its own search. `make test` 254 passed.
      - Dev, live (`--tag=fixb`, report `20261016T100134Z`): the router agreed on 18 of 28 searching questions. On those, time before Gemini starts went from p50 1,060 to 684 ms (median paired −268 ms, 95% CI −490 to −128, n 16). TTFT end to end: p50 3.72 s, p95 9.65 s.
      - README and eval card report the TTFT miss: Gemini's drift and 1.0 s out of reach on free tiers with the stages in sequence.
    - [x] **Decision 4, fallback (user decision, 2026-10-16): NVIDIA gpt-oss-20b (4a) stays `LLM_FALLBACK`.** No change.
      - Runs: `LLM_PRIMARY=<candidate> make eval SUITE=answer SUBSET=ci ARGS=--no-judge`. Rule: draft citation pass rate (checked in code), then latency (primary-call timings, paired with `--compare`).
      - 4a and 4b (reports `20261016T092724Z` and `093202Z`): not too close to call, so no dev-full runs.
        - The pass rates rest on 7 quotes from 3 questions (4a, 3 passed) and 1 quote (4b), sharing one question, so the rule's first step cannot separate them.
        - Latency decides: nemotron's own first token is +10.1 s slower at p50 (95% CI +3.5 to +14.0, n 13), likely from its default reasoning (not tested switched off). It also hit the 30 s answer limit on 3 of 4 textual questions.
      - 4c (Groq gpt-oss-120b) skipped: a Groq-hosted fallback shares outages with the Groq router and spends the gpt-oss-120b allowance shared with FreightAudit and the judge.
      - 4d (NVIDIA gpt-oss-120b) was proposed and found retired, so it was not an option: a tiny request got 410 ("retired this model"). Two tiny requests went out, because the first one's output was lost.
    - [ ] **Follow-up judge check (eval card), 2026-10-17:** `make calibrate ARGS="followup import"`, a spot check with no kappa.
      - Built (2026-10-16): a second sample in `evals/calibration/v1-followup/`, from 4b first, topped up from 4a, never from 4c; v1 stays frozen. `spot_check` reports how many of the sentences labeled not supported the judge failed too. Unit tests for the draw and the spot check.
      - 6 sentences (2 from nemotron, 4 from gpt-oss-20b), short of about 10. Claude's labels: 2 y, 4 n, under the written criterion (a computed number is not stated). They check out against the sample (`imported`).
      - Cost: 6 judge calls, about 8.7K input tokens, so about 11K gpt-oss-120b. Not on 2026-10-16: FreightAudit's CI needs gpt-oss-120b that evening.
  - [x] **Router misses checked (user request, no quota, 2026-10-16):** not clearly worse than the rest on recall or answers, so no deterministic fill. Numbers in memory.md.
  - [x] **Reports record the code and prompts (user request, 2026-10-16):** `code_version` (commit, uncommitted changes, source sha256) and `prompt_hashes` (system prompts and schemas). `make test` 255 passed; ruff and pyright clean.
  - [ ] **Test run (golden v1 test split), 2026-10-17: approved by the user on 2026-10-16, with conditions.** `make eval SUITE=all SPLIT=test`, judge on; no `--tag`, the production path. The 30 questions are 12 numeric, 6 textual, 5 comparison, 4 unanswerable and 3 time traps.
    - Start: 15:07 Taipei (07:07 UTC), after Gemini's daily reset at midnight Pacific, 15:00 Taipei (user, 2026-10-16): the dev runs of 2026-10-16 may have used most of this project's Gemini allowance. A one-shot prompt is scheduled in the session for that time.
    - Order:
      1. Run the follow-up import (spot check).
      2. Rebuild and restart this project's api, ingest and embed services from the current code (`docker compose build api ingest embed`, then `docker compose up -d api ingest embed`), and check readiness.
      3. Confirm that golden v1 is frozen and unchanged, the corpus check passes, and calibration v1 matches its hashes below.
      4. Run the test.
      5. Report the full results table against targets and floors, misses included, and stop.
    - Floors: `evals/thresholds.json` does not exist yet.
      - The test run writes none (user decision): its report shows the floors the rule would set, unwritten.
      - The user reviews the results. Then `uv run python -m evals.harness --set-floors evals/reports/2026-10-17.json` writes every floor from the test run's own measured values, latency included (built 2026-10-16, with a test).
    - Code: the user commits locally on the evening of 2026-10-16. So the report must show no uncommitted changes to the code (`dirty` false) on the new commit, with source sha256 `b238808a9abff8a6c5273c93042127925b4f0d86268f04b93399aaa7a9f7b9f9` (after the gitleaks field rename).
    - Calibration v1 sha256 (2026-10-16, 11:50 UTC):
      - claude_labels.jsonl `b50fbc6b10e9fb4c`
      - result.json `cc03426a17edece2`
      - sample.jsonl `aa128cde3808323d` (since the gitleaks field rename on 2026-10-16: `"key"` became `"cache_id"`, values unchanged; before, `2c65f1cbe85b3fed`)
      - sample_for_labeling.jsonl `82efec0fbbb70767`
      - Golden v1 manifest.json `e3ecaba53c6b9595`
    - Checked the same day: golden v1 frozen and unchanged; corpus check passed.

    | Run | gpt-oss-20b | gpt-oss-120b | Judge | Other |
    | --- | --- | --- | --- | --- |
    | Follow-up import | 0 | about 11K (6 calls) | yes, it is the check | none |
    | Test run | about 33K (30 router calls) | 22-27K, up to 33K if absent questions get answered (judge on about 21 answers) | yes: citation precision and faithfulness are targets | Gemini about 25 requests; retrieval suite local |
    | Total | about 33K | about 33-44K | | |

    - Estimates use dev's measured averages: router 1,106 tokens a call; judge 643 (numeric), 1,139 (comparison), 2,222 (textual) a call.
    - gpt-oss-120b on 2026-10-17: FreightAudit's CI ran on the evening of 2026-10-16 (20-25K). By 06:00 UTC the allowance has refilled well past 44K plus FreightAudit's 25K, so both runs can start any time after 06:00 UTC.
    - gpt-oss-20b: 2026-10-16 spent about 200K (3a, 4a, 4b and fix B); by 2026-10-17 it has refilled.
    - After the run: report and markdown summary, the README eval table, docs.

## Completed

- [x] 6a (2026-10-15). Provider layer, local embeddings, hybrid retrieval, answers with verified citations. Done when `make test` and `make test-int` are green three runs in a row, then a live smoke run with `AI_ENABLED=true` answers a numeric question (fact id and value), a textual one (citations and quotes) and an unanswerable one (refusal), each with tokens, latency per stage and time to first token.
  - [x] Models (user decision, 2026-10-15): `LLM_PRIMARY=gemini:gemini-3.5-flash-lite`, `LLM_ROUTER=groq:openai/gpt-oss-20b`, `LLM_FALLBACK` on NVIDIA NIM. `AI_ENABLED` now defaults to false (it defaulted to true).
  - [x] Providers (`filinglens_llm.providers`): OpenAI-compatible client and Gemini adapter, fallback for the primary and the router (recorded in logs, answer stats and the Redis field `fallbacks`), 402 permanent (503).
  - [x] Local models (`filinglens_llm.local`, `make models`): bge-small/bge-base embedders with the bge query prefix, TinyBERT/MiniLM rerankers, pinned commits in `HF_HOME`, offline in tests and containers. torch pinned below 2.13 (Smart App Control blocks its `torch_python.dll` from 2.13).
  - [x] Embed stage and `embed` worker service: the 30 filings are indexed, 11,263 chunks with bge-small vectors in about 14 min (13.0 chunks/s in the embed container).
  - [x] Retrieval (`filinglens_retrieval.search`, `/v1/search` with `cik` and `fiscal_year`, 409, degraded): warm in the API container embed 15-25 ms, SQL 5-110 ms, rerank 128-182 ms (TinyBERT, 50 candidates).
  - [x] Answers (`filinglens_api.answering`, `filinglens_llm.router`/`answer`/`validate`): routing, facts, retrieval, cited draft streamed, validation, one regeneration, refusals (out of scope, unknown company, time trap, low relevance at a provisional -3.0), in-flight cap. Contract: `Answer.refused` and `warnings`, search filters and 409 (`make contracts-breaking`: none breaking).
  - [x] Tests: unit 211; answering on recorded fixtures (`scripts/record_llm_fixtures.py`, `services/api/tests/fixtures/answers`); integration for search paging, 409 and degraded, `get_financial_fact`, and the pipeline through embed.
  - [x] User decision (2026-10-15): test `deepseek-ai/deepseek-v4.1-flash` and `openai/gpt-oss-20b` on NVIDIA with one real answering call each (same question, 12 retrieved chunks, our schema): schema, every citation through `citation_error`, latency and tokens. Pick the one that passes; if both, deepseek-v4.1-flash. Record the results and date in `docs/memory.md`. Done: neither passed in full; gpt-oss-20b kept (memory.md).
  - [x] Three runs in a row: `make test` 211 passed (18.1, 17.0, 21.2 s), `make test-int` 28 passed (171.2, 178.6, 161.9 s). An earlier run had 2 failures in `test_limits.py`, which assumed AI on by default; fixed.
  - [x] Live smoke run (`make smoke`, 2026-10-15): numeric (fact 37437, 416,161,000,000 USD), textual (quoted citations, all passing validation), fiscal 2027 refused as a time trap; tokens, stage latencies and time to first token in the activity log. Docs updated.
  - [x] Before the commit (user requests, 2026-10-16): torch pinned below 2.13 on Windows only (`sys_platform == 'win32'`), so the Linux images run 2.14.1+cpu (checked in the api and embed containers, search warm 0.19 s); `make test` 211 passed in 17.7 s. gpt-oss-120b probed on NVIDIA: 410, retired on 2026-09-03; gpt-oss-20b stays `LLM_FALLBACK` (memory.md). The first-token miss is a 6b item (context.md, Known Limitations).

- [x] `.env` `SEC_USER_AGENT` names the tool and a contact; its value is now quoted, so `uv run --env-file .env` parses the file again (2026-10-15). `uv run` and the ingest container read the same 35-character value without quote characters.

- [x] 5. Tests (2026-10-15):
  - Three runs each, all green: `make test` 127 passed in 7.9, 8.2 and 8.4 s; `make test-int` 23 passed in 105.2, 104.4 and 105.6 s (pytest's times; wall adds about 2 s). After `parse_amount` gained abbreviations: `make test` 139 passed in 8.4 s (9.9 s wall).
  - Unit: chunker properties (hypothesis), RRF, citation validation, amounts, SecClient timeouts (respx), the network guard. Integration: keyset pages over 100k chunks under concurrent inserts (page size 100, 24 s); the embedding swap 0004-0006 with the API reading in a loop, zero failed reads.
  - User decisions: keep Testcontainers; citations normalized (NFKC, straight quotes, collapsed whitespace) but exact on words and digits; page size 100 with all 100k chunks; `parse_amount` reads K, M, B or bn, and T.

- [x] 4b. Parse, chunk, facts and `scripts/seed_real.py` (2026-10-15):
  - One live `make seed-real` run left the 30 golden-set 10-Ks parsed and chunked with facts loaded: 11,263 chunks (158 to 938 per 10-K, median 314), 856,438 facts, no required item missing, fiscal year and period from companyfacts for all 30. 91 SEC requests (30 documents) in 32 s.
  - A second run made 0 SEC requests and downloaded 0 documents.
  - "supply chain risk" on Apple's chunks returned only Item 1A chunks.
  - `make test` 85 passed, `make test-int` 21 passed.
  - User decisions: missing items stored and listed; whole companyfacts with the facts key including `cik`; the latest-filed rule for `get_financial_fact`; only a 10-K/A stops the seed; ConocoPhillips replaced ExxonMobil in the golden set (SEC moved XOM to a new holding company that has no 10-K yet).

- [x] Manual setup checked (2026-10-15): `.env` parses with `uv run --env-file .env`; `API_KEY` (43 characters) holds a value, not a command, and differs from `ADMIN_API_KEY`; `RETRIEVAL_EMBEDDING_COLUMN=embedding`; `SEC_USER_AGENT` set with an email; dev database at 0007 with the 6 seeded companies (now at 0008).

- [x] Step 4 fixes (2026-10-15):
  - The SEC limiter fails closed: without Redis, tasks pause and keep their retries. Tested with a worker on a dead Redis.
  - A 403 after one cool-off fails the job with a reason that names SEC_USER_AGENT. Tested with a refused User-Agent: 2 requests, job `failed`.
  - `make test` 68, `make test-int` 19.
- [x] 4. Workers (2026-10-14): integration tests show:
  - 20 worker processes stay at 8 SEC requests a second: the 9th request after any request arrived at least 0.983 s later at the fake server, within a 50 ms jitter allowance.
  - A filing that fails every attempt (1 + 6 retries) lands in `fetch.dlq` and `dead_letters`, then replays.
  - A full fetch queue makes discover back off without losing filings.
  - A killed worker's message is redelivered without duplicate rows.
  
  Ingest jobs are live in `LiveBackend`. Tests cover the API rate limits, the AI budget guard and the 64 KB and 30 s limits. `make test` (68) and `make test-int` (17) are green.
  
  User decisions: discover and fetch only, with parse, chunk, facts and seed_real in 4b; `partially_failed` kept; the 30 companies in `evals/golden-companies.csv`.
- [x] 3. Data (2026-10-14): `alembic upgrade head` works from an empty database (tests and the CLI); downgrading the expand step (0004 to 0003) keeps model A data; EXPLAIN shows the HNSW index serving the search query for both embedding columns and after the contract; the reembed task runs in batches of 256, resumes from its cursor and catches up new chunks; `make seed-fake` loads 100k chunks and a rerun inserts nothing; `LiveBackend` pages filings, sections, chunks and facts from Postgres; `make test` green. User decisions: `seed_real.py` and the SEC client moved to step 4; models A and B are bge-small-en-v1.5 (384) and bge-base-en-v1.5 (768); the embedder is a stub until step 6.
- [x] 2. Contracts (2026-10-14): REST v1 and GraphQL contracts exported to `contracts/`; four clients generated cleanly (`make codegen`); `make contracts-check` fails on stale output and passes on a committed tree; `make contracts-breaking` passes against main and fails on a breaking change; the contract test calls every route through the generated Python client against the app served by uvicorn.
- [x] 1. Scaffolding: monorepo layout, docker-compose infra healthy, every service answers /healthz (2026-10-14). The prompt's done-checks all pass: uv sync, lint, typecheck, compose healthy, api /healthz and /readyz, worker connected to RabbitMQ, a missing env var stops startup. Domain models move to step 3 with the schema; the eval harness to step 6.
- [x] Project created from template (2026-10-13).

## Blocked

None.
