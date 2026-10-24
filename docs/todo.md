# To-Do

Concise, verifiable tasks. Move items between sections as status changes. Trim old completed items when the list grows large; the activity log keeps the history.

Each step maps to a Claude Code prompt in the design doc. Done when the check after the colon passes.

## Pending

- [ ] (user, 2026-10-24) **next-security** (branch `next-security` from main at fe90d5f). CI's vuln-scan: next 16.3.8 (GHSA-2464-fhr4-w9xw and GHSA-673q-mjm6-r5xr CRITICAL, CVE-2026-94482 HIGH), filelock 4.1.1 and virtualenv 21.14.7 (HIGH, dev-only). Fixed by upgrading, no ignore entries.
  - [x] next 16.4.1; `uv lock --upgrade-package filelock --upgrade-package virtualenv`, header back to `revision = 3`.
  - [x] Checks: the three Trivy scans 0; `make lint` clean; `make test` 418; web typecheck, `npm test` 84, build, Playwright 72.
  - [ ] (user) ship. Then Dependabot's next PR, if any, is obsolete.
- [ ] (user, 2026-10-21) **certifi bump** (branch `certifi-bump` from main at aca22a6). CI's vuln-scan failed on PR #22 with one CRITICAL in `uv.lock`: certifi 2026.7.22, GHSA-6q48-6c7w-9gw2, fixed in 2026.10.19. Fixed at the source, with no ignore file or allowlist (memory.md, Preferences).
  - [x] `uv lock --upgrade-package certifi`: only certifi's three lines change, and the header stays at `revision = 3`. `uv sync` changed only certifi.
  - [x] Checks: `make vuln-scan` 0 on all three lockfiles; `make image-scan` 0 CRITICAL on api and ingest rebuilt from this branch (the old `filinglens-api:ci` showed the CRITICAL); `make lint` clean; `make test` 418.
  - [ ] (user) confirm that Actions → Caches lists an `eval-calls-*` entry, then ship. Then `claude-first` takes main so PR #22's vuln-scan passes; activity-log.md's top conflicts there: keep both entries.
- [ ] (later) Lift Dependabot's typescript-major ignore once an openapi-typescript release accepts typescript 7, and its `@types/node` rule when the runtime moves past Node 24 (both comments in `.github/dependabot.yml`).
- [ ] (manual, user; the fix merged as #7) Nightly eval: start one run by hand (Actions, Nightly eval, Run workflow), then check that the next scheduled run happens (19:17 UTC, 03:17 Taipei). Expected: PASS, and the artifact holds the report JSON under `reports/`.
  - The first manual run (39068994474, 2026-10-18, main at febbe5f) proved the workflow runs. All 30 test questions ran, then it exited 4 on x18's judge error: a dangling `[12]` the validator let through. c15 was refused after validation dropped every sentence twice, which is answer-model variation, not a regression. Its artifact held only the verdict (activity-log.md, memory.md).
  - Before #7, a scheduled run would replay the x18 judge error from the reply cache and exit 4. An exit-4 run is not complete, so the gate measures again.
  - The user reports what the runs showed. Claude Code reads no Actions page and runs no gh (AGENTS.md, Git).
  - A manual run always runs the eval, because the unchanged-inputs gate skips scheduled runs only. The reply cache carries over, so after the fix only x18's regeneration and judge call go live. A cold cache spends about 33K gpt-oss-20b, 18-28K gpt-oss-120b (the judge, shared with FreightAudit's Groq account) and about 25 Gemini requests.
  - After a complete manual run, a scheduled run with unchanged inputs shows SKIPPED and spends nothing. It still proves that the schedule fires.
- [ ] (manual, optional) pre-commit keeps its cache on C: (`C:\Users\kwonhyuk\.cache\pre-commit`, gitleaks build included), because `PRE_COMMIT_HOME` is unset. AGENTS.md wants caches on H:: set `PRE_COMMIT_HOME=H:\.cache\pre-commit` for the user, then remove the old folder (found 2026-10-17).
- [ ] (manual, optional) Remove the unused Docker volume `filinglens_sec-cache` (`docker volume rm filinglens_sec-cache`); the SEC cache now lives in `.cache/sec`.
- [ ] Live embedding swap (after step 6; user decision): with dev on the last revision before 0004 (now 0008), record the model A baseline (`make eval`, recall@10 and MRR@10, golden set version); run 0004, the reembed backfill, 0005 (run `make check-parallel-hnsw` first, then pick a parallel build within the 256 MB `shm_size` or a serial one with more `maintenance_work_mem`, by corpus size; runbook step 3), the catch-up run and the flip to `embedding_v2`; run `make eval` again on the same golden set; record both runs in `eval_runs` and the activity log; then run 0006 in the next release and set `.env.example` to `embedding_v2`. Done when both recall@10 values are recorded and dev is at head. Runbook: `docs/migrations.md`.
- [ ] (later idea, user, 2026-10-16) A deterministic check for derived numbers: recompute a percent of a stated total, or the difference of two cited figures, from the cited figures themselves, so correct arithmetic can pass validation and wrong arithmetic gets caught. Today validation rejects every derived figure (memory.md, step 6a), and the judge criterion counts a computed number as not stated.
- [ ] (after step 6) Decide how a company that changes CIK in a restructure is handled (for example a `cik_aliases` table), since `get_financial_fact` looks facts up by CIK. Known case: XOM (Exxon Mobil Corp, CIK 34088, filed the latest 10-K; SEC now lists the ticker under ExxonMobil Holdings Corp, CIK 2115436).
- [ ] Claude Haiku 5.5 as the answer fallback, in dev only: `LLM_ANSWER_FALLBACK=anthropic:claude-haiku-5-5` is set in `.env` (user, 2026-10-17).
  - `.env` has no `AI_ENABLED` line, so the default (false) applies and no answer calls run.
  - Its credits expire 2026-11-10.
  - CI never calls Claude (step 7). Neither will production: the public deployment runs free providers only, with no Anthropic key (the user's standing rule, 2026-10-21; memory.md).
- [ ] (v2, with golden set v2) The known weaknesses from the test run (README, "Known weaknesses"):
  - router fixes: an out-of-scope guard, and a ticker fill;
  - a time-trap check in code for a fiscal year the question names but the router leaves out (t07, "fiscal 2026"), instead of relying on the model to refuse (user, 2026-10-17). Not built now: the exam results stay tied to the exam's code;
  - a comparison check;
  - more textual test questions with human labels;
  - TTFT;
  - fact headings for year-end values from 10-Qs;
  - natural judge negatives;
  - latency at scale.

  Nothing is tuned on golden v1's test results.
- [ ] (with golden v2, or before step 10 if production is a fresh ingest; deferred by the user on 2026-10-18, formerly "before step 9") Label the separate financial sections' chunks as Items 7, 7A and 8, so citations show the right item.
  - **Today:** four 10-Ks keep MD&A or the statements in a separate financial section that Items 7, 7A or 8 only point to, and the parser labels that content with the item heading before it:
    - JPM `0001628280-26-008131`, Item 15: 813 chunks;
    - CVX `0000093410-26-000078`, Item 14: 275 chunks;
    - NVDA `0001045810-26-000021`, Item 15: 84 chunks, its Item 8 content;
    - PLD `0001193125-26-051453`, Item 16: 201 chunks, its Item 8 content.

    XOM is not in the corpus.
  - **Needs:**
    - detection of headings that do not start with "Item", robust to the section's own table of contents and to titles repeated as page headers;
    - a data-model decision: a section is one range, unique per (filing, item); pointer sections 7, 7A and 8 already exist; and JPM's 7A sits inside its 7;
    - a re-parse path, since none exists;
    - fixtures;
    - golden v2, since re-parsing dev removes 14 of golden v1's gold chunk ids and voids the reply cache.
  - Findings: memory.md, 2026-10-18.
- [ ] (watch, found 2026-10-19 on B2's branch) One Playwright run got "Internal Server Error" right after sign-in, in the setup project, so 48 specs did not run. Cause not confirmed; it has not come back since.
  - That run's log held the web servers' stderr (Playwright pipes it by default), but only its summary lines were read, and a later run overwrote the log (memory.md). Their stdout was not piped then.
  - If it comes back, the run's output holds every line both web servers print, each prefixed `[WebServer]`:
    - stdout (piped since that run): `signed_in` when the sign-in action finishes, or `sign_in_failed` or `sign_in_locked` when it does not. Then `api_call` with `route: "ping"`, the Ask page's first API call, with `status`, `ms` and `request_id`; when that call fails, it comes at warn with `failure` and the exception's name (`error`).
    - stderr: Next's own `⨯ Error: ...` line with its stack and `digest`, and `api_key_rejected` on a 401 or 403.
  - So the output shows which side failed: sign-in, the Ask page's API call, or Next itself. Read the whole log then, not only its summary lines.
- [ ] (flaky test, found 2026-10-18; user decides) `test_twenty_workers_never_exceed_eight_sec_requests_a_second` fails now and then on this PC.
  - The misses: its tightest 9-request span came in 60 and 75 ms under 1 s, against `JITTER_S = 0.05` (`services/ingest/tests/test_pipeline.py:80`). It failed 2 of 4 full `make test-int` runs, and 1 of 5 runs alone.
  - Not B1: the code it runs is identical to main.
  - 2026-10-19, on B2's branch (its code still identical to main): it failed in the full `make test-int` (tightest span 0.919 s against the 0.95 s floor) and passed when run alone right after.
  - Options: widen `JITTER_S` (the calibration knob) in its own small PR, or leave it, since CI runs it on Linux.
- [ ] (B1 review minors, 2026-10-18; deferred, user decides) Found by B1's final review, not fixed:
  - **Combined filings:** facts listed under a filing take the filing's CIK (`Filing.facts`). So a combined filing's facts of another registrant would show the wrong company. Latent: none of the 30 companies share a filing.
  - **Comment:** the `ponytail:` comment on `Chunk._source` says one lookup per chunk. But `section` and `filing` resolve at once and make two; step 10's DataLoader fixes it.
  - **Test strength:**
    - The FakeBackend maps every chunk to `FILINGS[0]` and every fact to AAPL, so the link tests cannot tell a link that follows its row from a constant.
    - "No lookup on an empty list" has no test.
    - Nothing pins that facts of a non-indexed filing stay found.
  - **Empty IN:** non-numeric fact ids still run an empty IN query.
  - **`@types/node`:** it comes in at 26 (through `@types/ws`), while CI runs Node 24. Dependabot's `@types/node` rule (2026-10-19) does not cover it: with no `allow` option, version updates touch only direct dependencies, here web's.
- [ ] 10. Deploy: UI on Vercel, backend on the PC via Tailscale Funnel; phone test passes; 401 without API key; demo mode when the PC is off
  - **Plan:** made 2026-10-20, approved 2026-10-21 with three changes (memory.md, step 10). Plan file: `C:\Users\kwonhyuk\.claude\plans\pasted-content-id-ee81-source-fiscal-validated-dolphin.md`.
    - **Backend:**
      - a compose project `filinglens-prod` (`infra/docker-compose.prod.yml` + `.env.prod`);
      - GHCR images by `sha-` tag, and no host port;
      - Funnel in FilingLens's own `tailscale` sidecar (`tag:filinglens`, port 443), as FreightAudit runs it;
      - free providers only, with no Anthropic key.
    - **Web:** Vercel, with Root Directory `web` and files outside it included, region `hkg1`, and only main deploying.
    - **Database:** `corpus-v1`, restored once (0 SEC requests, 0 model calls).
  - [x] **0. Docs:** todo, activity log, memory, context (2026-10-21). Uncommitted; they ride with 10a.
  - [ ] **10a. API hardening** (branch `step-10-api-hardening`), each change test first (activity-log.md, 2026-10-21):
    - [x] a browser `Origin` gets 403 (an app-wide dependency, before the key check);
    - [x] `/readyz` is cached for 5 s (its state created in `lifespan`, the stamp taken when a round ends);
    - [x] `/docs`, `/redoc` and `/openapi.json` are off;
    - [x] introspection is off (`DisableIntrospection`), and `__typename` still works;
    - [x] a NUL is refused in `q`, `question`, `concept` and cursors;
    - [x] coercion errors answer `invalid_input` without the value, and GraphQL errors are logged with code and path only;
    - [x] SQL parameters are hidden from logged errors (`hide_parameters`);
    - [x] the final review's fixes:
      - the readyz stamp at a round's end;
      - keyless Origin rows;
      - a NUL test for every cursor key field;
      - argument errors at execution as `invalid_input`;
      - a bounded `CompanyKey.cik`;
      - GraphQL `fiscalYear` held to 1993-2100;
    - [x] checks:
      - `make lint` and `make typecheck` (0 errors) clean;
      - `make test` 416, `make test-int` 31, `npm --prefix clients/ts test` 18;
      - `make contracts-breaking`: nothing breaking;
      - gitleaks on 16 files: clean;
      - the eval check: no model call.
    - [x] (user) ship: merged as #19 (1f15729, git log).
  - [ ] **10b. GraphQL DataLoader** (branch `step-10-dataloader`):
    - per-request loaders for chunk sources and companies (`Backend.get_companies`);
    - call-count tests;
    - (user) ship.
  - [ ] **10c. Deploy config and runbook** (branch `step-10-deploy-config`):
    - the prod override: project name, GHCR images, the `data` network, the `ingest` profile, the tailscale service, free providers forced;
    - `infra/tailscale/serve.json`, `web/vercel.json`, `engines.node` `^24.7.0`, and `docs/deploy.md`;
    - the `docker compose config` checks;
    - (user) ship.
  - [ ] **Manual (user), anytime:**
    - B1: make the GHCR packages public (irreversible);
    - B2: add `tag:filinglens` to `tagOwners` and to the funnel `nodeAttrs`;
    - B3: create a Vercel account;
    - B4 (optional): set the power and Docker Desktop start settings.
  - [ ] **Manual (user), after 10c merges:**
    - B5-B17, the backend: the auth key, `.env.prod`, the external volume, pull, Postgres, the restore and its check, up, the search check, Funnel status, the public checks;
    - B18-B23, Vercel: the import, the settings, the four variables, the firewall rule.
  - [ ] **Phone test with AI off (user):** B24-B27: sign-in, the pages, 401, the PC off, the API down.
  - [ ] **B28 (user):** create a Gemini key in a new FilingLens Google project with billing off, and put it in `.env.prod`. Until then AI stays off.
  - [ ] **B29 (on the user's go):** set `AI_ENABLED=true`, then ask exactly two questions (n01, x04). Expected: about 7,900 tokens, $0 billed; worst case about 13K tokens.
  - [ ] **10d. Docs after go-live:** the deploy record (the image tag, the times, the two answers' usage).
  - **Kept from the step 9 notes:** the sign-in limiter lives in each Vercel instance; the firewall rule on `POST /login` (10 a minute per IP) covers the rest.
    - On Vercel (`VERCEL=1`), its key is `x-real-ip`, which Vercel sets and no client can override (Vercel's request-headers doc, updated 2025-12-13).
    - Locally, all clients share one bucket.
  - **Superseded:** "Replace the example passwords in `.env`". The dev Postgres and RabbitMQ volumes keep the passwords they were created with, so `.env` stays as is, and production gets new values in `.env.prod`.
- [ ] (from 10b's CI eval, 2026-10-21; user) **Rerank deadline** (branch `rerank-deadline`), each fix test first (memory.md, Solved Problems):
  - [x] the answer eval's searches wait up to 60 s for the reranker, as the retrieval eval's do (`harness.eval_settings`);
  - [x] a guessed search the plan does not use is cancelled at once, in production too, and a rerank it still has queued skips the model;
  - [x] no cache key changes for a search that met 500 ms: a pin row for the deadline;
  - [x] checks:
    - `make lint` and `make typecheck` (0 errors) clean;
    - `make test` 418, `make test-int` 31;
    - `make contracts-breaking`: no changes;
    - gitleaks on the changed files: clean.
  - [x] (user) ship: merged as aca22a6.
- [ ] (user, 2026-10-21; before 10c) **Claude first** (branch `claude-first`), each part test first, with deliberate breaks:
  - [x] **Chain:**
    - production sets `LLM_PRIMARY=anthropic:claude-haiku-5-5`, `LLM_ANSWER_FALLBACK=gemini:gemini-3.5-flash-lite` and `LLM_FALLBACK` NVIDIA, so answers go Claude, then Gemini, then NVIDIA;
    - **off for good, stored in Redis (`ai:claude:off`) so it outlives a restart:** credits gone (402, or a 400 naming a spend limit or the credit balance), and from `ANTHROPIC_CREDITS_EXPIRE` (2026-11-10);
    - **off for good with an alert:** a rejected key or model (401, 403, 404);
    - **free chain for that answer only:** a 429, with or without `Retry-After`;
    - **free models used up too:** the existing 503 "try again shortly".
  - [x] **Limits:**
    - Claude's output cap per call: 1,052;
    - no Claude prompt that could pass 100,000 tokens;
    - Claude's own daily budget: 1,500,000 tokens, at most $0.75 a day, in `ai:claude:<date>` on the API's Redis database, shared by the api and the evals;
    - Claude's tokens leave the free budget's counter; the free budgets keep their sizes.
  - [x] **Plan:** the prod override that forced `LLM_ANSWER_FALLBACK` and `ANTHROPIC_API_KEY` empty goes; the variable table, point 6's live test and its stop rule follow Claude first. Point 6 now: about 10,700 tokens and $0.001 of credits; at worst about $0.0037.
  - [x] **Evals:** the official answer eval stays on the free models. A labelled local `--claude-primary` configuration is reported side by side with the official run, never sets floors, and is refused in CI.
  - [x] **Deliberate breaks:** 9 scratch mutants, each failing its own tests.
  - [x] **Checks:**
    - `make lint` and `make typecheck` (0 errors) clean;
    - `make test` 438, `make test-int` 32;
    - `make monitoring-check`: 14 rules, tests passed;
    - `make contracts-breaking`: no changes;
    - gitleaks: clean, apart from a CRLF artifact in `.env.example` that main's file shows too;
    - the eval check: no cache key changes for the free models.
  - [x] (user, 2026-10-21) **Budgets apart:** prod and the local `--claude-primary` evals keep separate Claude budgets, and prod's Redis gets no host port. Why: prod's worst case is $0.75 a day (about $15 to 2026-11-10, FilingLens's share), local Claude evals are rare and started by the user, and Anthropic's $50 monthly limit is the hard stop (memory.md). Docs only.
  - [x] (user, 2026-10-21) **The docs pass's two findings, fixed before shipping** (memory.md, Solved Problems):
    - `--claude-primary` always takes the official free run's routes, those of the default `LLM_PRIMARY`, whatever `.env` says. Test first: a `LLM_PRIMARY=anthropic:claude-haiku-5-5` row failed, then passed, and the bug put back fails it again.
    - The comment on `Anthropic._gone` now says the switch-off is stored in Redis and survives restarts.
    - Checks: `make lint` and `make typecheck` (0 errors) clean; `make test` 440, `make test-int` 32.
  - [ ] (user) confirm that Actions → Caches lists an `eval-calls-*` entry, then ship.
- [ ] (first after go-live; user, 2026-10-21) **Egress proxy**, as FreightAudit runs it.
  - The internet-facing api and tailscale containers would reach the internet only through an allowlist proxy, so they could no longer reach services on the PC's own ports through `host.docker.internal` (context.md, Known Limitations).
  - It needs FilingLens's own CI-built proxy image and an allowlist of the model providers' and Tailscale's hosts.
- [ ] (after go-live; user, 2026-10-20) **Alertmanager:** delivery for the 13 alert rules (step 8), once a channel (email, ntfy, Discord...) and its secret are chosen. Prod then runs the `observability` profile, on ports apart from dev's.
- [ ] (candidates from the mockup, 2026-10-19; user decides; five built in mockup features 1, merged as #17, and the source cards' fiscal year end, merged as #18) What the mockup shows and the app does not have. The mockup style round restyled the existing screens only. Sizes are rough: small is a short web-only change, medium a PR that touches the API or its contracts, large several PRs or new storage. API facts were checked in `contracts/schema.graphql`, `clients/ts/openapi.d.ts` and `packages/db` on 2026-10-19.
  - **History** (every question, how it was read, answered or refused, tabs by kind, search, answer time): large; needs API work. No table holds questions or answers today, so it needs one (expand, migrate, contract), a write per answer, a keyset list route, and a privacy decision, since questions are user text and no log keeps them now.
  - **Company and fiscal-year pickers on Ask** (company chips with "+ Add company", a fiscal-year select): medium; needs API work. The answer request takes only `question` and the router finds companies and years itself, so the pickers need request fields that narrow the router. The company list already comes from GraphQL `companies`.
  - **"Read as" chips** (how the router read the question: kind, company, years, the figures asked for): small to medium; needs API work. The answer carries no router output; it would need a new `Answer` field (a contract change).
  - **Number-check table** ("Numbers checked against XBRL data": each figure, the reported fact, matches or not): medium; needs API work. The validator's per-figure matches are not in the answer; they would be a new `Answer` field.
  - **Filings totals** (companies, sections, searchable passages, reported numbers): small; needs API work, since no count is exposed (no `totalCount`, no stats route). The demo could take them from `make demo-export`.
  - **Filings detail panel** (a company's sections, fiscal year end, indexed date, "Ask about" it, its filings link) with a selected row: medium; little API work. `Filing.sections` and `Filing.periodEnd` already exist in GraphQL; the indexed date does not.
  - **Filings status pills** ("Indexed", or "Needs a look" with a reason, such as XOM's CIK change): small to medium; needs API work, since no per-filing ingest status is exposed. "Indexed" is built in mockup features 1, since the API lists indexed filings only. Still open: "Needs a look" and its reason.
  - **Filings search** ("Find a company or ticker"): small to medium; needs API work for a search across pages, since a filter over the 20 companies shown would mislead. Not taken in mockup features 1 for that reason: it needs a name or ticker filter on `companies`, which takes only `first` and `after` today.
  - **Ingest jobs** (admin): large; needs API work. `POST /v1/ingest-jobs` and `GET /v1/ingest-jobs/{job_id}` exist for `ADMIN_API_KEY`, but there is no list route, and the web has no admin role and holds only the normal key. Giving the web the admin key is a security decision.
  - **Source panel pager** ("Source 1 of 2", previous, next and close; one source at a time): small; no API work. It would replace the scrolling list of every source. Not taken in mockup features 1: one source at a time takes the others out of the reading and keyboard order, which that PR kept unchanged.
  - **"Copy answer with sources" and "New question" buttons** under the answer: small; no API work. Built in mockup features 1.
  - **Timings in the answer's header** (first words, complete, sources, "every number checked"): small; some API work. The browser can time the stream; "every number checked" needs the number check. First words, complete and the source count are built in mockup features 1, timed in the browser. Still open: "every number checked"; and the demo shows no timings, since the snapshot records none (the eval report has the run's times, so `make demo-export` could carry them).
  - **Source panel details** (the filing's fiscal year end; "How it was found", the search and the passage's rank; a passage's table drawn as a table with its numbers highlighted): medium; some API work. `Filing.periodEnd` exists; the rank and the search used are not in the answer. Not taken in mockup features 1. The fiscal year end for passages is merged as #18: `periodEnd` selected in `Sources`, a new snapshot. Still open: "How it was found", tables drawn as tables, and a fact card's filing period, which needs the API to link a fact to its filing.
  - **Header coverage line** ("30 companies · latest 10-Ks"): small; needs API work for a live count, or the snapshot's count on the demo. The demo's line ("30 companies · 30 filings", from the snapshot) is built in mockup features 1. Still open: the live header's line, which needs a count from the API; "latest" is recorded nowhere.
  - **Landing sections** (a hero with call-to-action buttons and a sample answer, "How an answer is made", "Evaluation results" from the eval report, "Architecture" with its stack, nav links including GitHub): medium; no API work. Static text plus the eval report at build time, like the demo snapshot.

## In Progress

- [ ] Claude first, on branch `claude-first` from main at aca22a6, uncommitted: built and checked, and the user ships it. Then step 10's 10c. 10a merged as #19 (1f15729); 10b was not on main at aca22a6 (git log). The checklists are under Pending.

## Completed

- [x] Source fiscal year (user, 2026-10-20), merged as #18 (86718cd, git log): the fiscal year end on the source cards, as in the mockup ("Fiscal year ended September 27, 2025"), from a new snapshot. Built on branch `source-fiscal-year` from main at e1059d7 (mockup features 1 merged as #17). The user's go: start `filinglens-postgres-1` by exact name, run `make demo-export`, stop it by exact name (Triage Copilot's exam is over). No live model or SEC call; the export only reads the dev Postgres.
  - [x] Test first: a unit test for the line's wording and date, Playwright for a chunk card on Ask (and a fact card without the line) and on the demo. Red: no export, no line.
  - [x] `Sources` selects the chunk's `filing { periodEnd }` (`clients/operations.graphql`, no API change), then `make codegen`: 5 files with content changes; 60 that differed in line endings only went back to HEAD's bytes (memory.md).
  - [x] Port 5433 checked free, `filinglens-postgres-1` started, `make demo-export`, the container stopped (exited 0, port free).
  - [x] What else changed in `web/demo/snapshot.json`: only `commit` and `recorded_at`. Answers, citations and companies are identical (activity-log.md, memory.md).
  - [x] The line on chunk cards; fact cards keep their Period row, since a fact has no link to its filing.
  - [x] Retook only the screenshots that change: 12 (ask-comparison, ask-textual, ask-warnings and the demo, in light, dark and phone).
  - [x] Checks: activity-log.md (2026-10-20, the source cards' fiscal year end).
  - [x] Docs: design, context, memory, todo, activity log. README unchanged: its usage did not change.
  - [x] (user) Reviewed the snapshot's changes and shipped it as #18.

- [x] Mockup features 1 (user, 2026-10-20), merged as #17 (e1059d7, git log): the mockup's small features that need no API change, on branch `mockup-features-1` from main at a14a019 (the mockup style merged as #16). Each shows only what the app knows: a detail that needs data the API does not give is left out and noted under Pending. The mockup is read only, nothing copied. No live model or SEC call, and no container (Triage Copilot's exam runs today from 15:00 Taipei).
  - [x] Taken, 5 of the 15 candidates: "Copy answer with sources" and "New question" under Ask's answer; the answer's timings (first words, complete, the source count); the demo header's coverage line, counted from the snapshot; an "Indexed" pill beside each listed filing.
  - [x] Not taken: the Filings search (a search across pages needs an API filter, and a filter over one page would mislead); the source details (the fiscal year end needs `periodEnd` in `Sources` and a new snapshot from the dev Postgres, which is stopped while the exam runs; the rest needs API work or is medium); the source pager (small, but one source at a time takes the others out of the reading and keyboard order, which this PR keeps). Each is noted under Pending, with the details left out of the five.
  - [x] Each feature test first: 4 unit tests (the timing line, the copied text) and 8 Playwright specs (the timings, copy, a refusal's buttons, New question, New question while the sources load, the keyboard order after an answer, the pills, the demo header's line). Red first, for the missing feature; the busy reset had its own red (memory.md).
  - [x] Built to the mockup in light, dark and phone width; axe passes on every screen (`npm run screens`, 54 screens).
  - [x] Retook only the screenshots that change: 30 (the six Ask answers, coverage, demo coverage, the demo and offline, each in light, dark and phone).
  - [x] Checks: activity-log.md (2026-10-20, mockup features 1).
  - [x] Docs: design, context, memory, todo, the activity log, and README (Ask's usage).
  - [x] (user) Shipped as #17.

- [x] Mockup style (user, 2026-10-19), merged as #16 (a14a019, git log): the user compared the design round with the separately made mockup and chose the mockup's style, with one change: a bigger sources panel. Built on branch `step-9-mockup-style` from main at 73bb1c0 (the design round merged as #15). The mockup was read only, from `_design-reference/filinglens/mockup` (12 screenshots and a README), and nothing was copied into the repo.
  - [x] Restyled every screen in the mockup's look (`web/app/globals.css`): Ask from the mockup's Ask, Coverage from its Filings look, the demo from its landing look (`docs/design.md`).
  - [x] The change: from 64rem the sources panel takes half the width, runs the full height of the window and scrolls on its own; a citation's jump brings its highlighted words into view in the panel (`components/quote-in-view.tsx`). Test first: red twice (the panel did not fill the window, then the quote stayed out of view), then green.
  - [x] Figures in the answer under the highlighter (`splitFigures`, its unit test first).
  - [x] The mockup's features the app does not have, listed under Pending as candidates.
  - [x] Screenshots retaken: 18 screens in light, dark and phone width in `docs/screenshots/ui/`, each after an axe check.
  - [x] Checks: listed in activity-log.md (2026-10-19, mockup style).
  - [x] Fix before shipping (user): at the top of Ask the panel's last 100 px or so sat below the window. It now sticks where it starts, below the header and the title, and ends 16 px above the window's bottom edge (`--panel-top` in `globals.css`). Test first: the panel test, now in a 1024 by 360 window, checks the gap below the panel on the first screen (red: -95.5 px, then 16). Retaken: the 10 screenshots that changed, the five Ask answers with sources in light and dark. Checks: activity-log.md (2026-10-19, the panel fix).
  - [x] (user) Shipped as #16.

- [x] Design round (user, 2026-10-19): the web app's own visual design, "paper and ink", built on `step-9-design` from main at 9b829a6, merged as #15 (73bb1c0, git log). `_design-reference` was not opened until the user had compared the two designs. The user then chose the separately made mockup's style, with one change (the mockup style, above); `docs/design.md` keeps paper and ink as a dated section.

- [x] 9. Review UI and demo mode: resolvers, login, backend-for-frontend, the demo snapshot when the backend is offline, Playwright passing (done 2026-10-19). Four PRs: A (#8), B1 (#9), B2 (#10) and B3 (below, merged as 9b829a6). Nothing else in step 9 remains: the plan's by-hand steps are done, since `LOGIN_PASSWORD_HASH`, `SESSION_SECRET` and `API_URL` are in `.env`. Every open item left belongs to step 10, a later corpus or a watch.
- [x] 9, PR B3: B2's three deferred review minors (2026-10-19), built on branch `step-9-web-b3` from main at e2b581d, merged on 2026-10-19 (9b829a6, git log; its subject names no PR number). Each test first (memory.md):
  - **Leaving Ask:** one AbortController per question. Leaving Ask, or a new question, aborts the stream and the sources lookup, and an aborted request shows nothing. Test: leaving through the Coverage link makes the mock API see its stream cut short (`GET /e2e/cut`; red: never cut). The abort before a new question has no test of its own (memory.md, ruling).
  - **Sources failure:** an error reply or a network error from `/api/sources` keeps the answer, and adds "Sources could not be loaded." under Sources and to the status line. "The web server could not be reached." now covers only the stream. Tests: both failures through `page.route` (red: no note), and a guard that the stream's own network error still shows the catch-all.
  - **Log label:** `failureLabel` in `lib/errors.ts` logs `AbortError` and `ResponseAborted` as `client_aborted` at info; other failures keep their class at warn. Test: one row each (red: `offline` at warn).
  - Checks: `make lint` and `make typecheck` clean, `make test` 370, web typecheck clean, `npm test` 78, build with no warning, `npx playwright test` 61 three runs in a row, gitleaks on the changed files clean, the eval skipped (no `EVAL_INPUTS` change).
- [x] 9, PR B2: web, BFF, sign-in, demo, Playwright, CI web job, merged as #10 (ab325a2, git log). Built on `step-9-web-b2` from main at a2037af (2026-10-19); the full record is in activity-log.md and memory.md.
  - Decisions that held: `/demo` is public; the demo answers are the exam records n01, c02, c12, x02, x04, x12, o02 and t01 (no model call); the e2e suite runs against `web/e2e/mock-api.ts`; axe plus keyboard and phone specs.
  - Before shipping: `make lint` and `make typecheck` clean, `make test` 370, web typecheck clean, `npm test` 77, build with no warning, `npx playwright test` 57 (three runs in a row after the review fixes), gitleaks on the changed files clean, the eval skipped.
  - Final review (fresh subagent): no Critical; 3 Important and 2 re-graded Minors fixed test first. Two more minors were fixed before shipping (the proxy secret, the snapshot's line endings), and three went to B3.
  - The user's steps: the snapshot review, then `hash-password`, `session-secret` and `API_URL` in `.env`.
- [x] Dependabot follow-ups, merged as #12 (e2b581d, git log): the python image's minor and major updates and `@types/node` 25+ ignored, graphql 17.0.2 taken in `clients/ts` (memory.md). The user checked that #2 (the Python 3.14 image) and #11 closed or were replaced (2026-10-19).
- [x] Dependabot's python group, merged as #4 (93f464d, git log): hypothesis 6.155.7 to 6.169.0, and uv_build's upper bound from `<0.13.0` to `<0.14.0`.
- [x] Dependabot's npm group pull request #3's CI failure (typescript 7.0.2 against openapi-typescript's `typescript ^5.x`): obsolete (user, 2026-10-19). The typescript-major ignore merged with B2 (#10).

- [x] 9, PR B1, the API lookups, merged as #9 (a2037af, git log). Its record follows. **Handed off mid-way on 2026-10-18, then finished by a fresh session the same day.**
  - **Where:** branch `step-9-api-lookups`, made from main at 35902f3 (PR A merged as #8). Everything below is uncommitted.
  - **Plan:** the approved plan file, section "PR B1".
  - **Spec, with one change from the plan:** a lookup takes **0 to 20** ids, not 1 to 20.
    - Why: one `Sources` query asks for chunks and facts together, and an answer may cite only one kind.
    - An empty list returns an empty list with no lookup.
    - Each id is 1 to 64 characters; otherwise the error is `invalid_input`.
    - Results keep the order given and hold each id once. Unknown ids, and chunks of filings that are not indexed, are left out.
  - **Built by the first session (at the handoff only `make codegen` had run):**
    - `backend.py`:
      - `ChunkSource`, `FactSource` and `_fact` (now also used by `list_facts`);
      - `Backend.get_chunks`, `get_facts` and `get_company`;
      - LiveBackend SQL with inner joins, chunks only from indexed filings, and `dict.fromkeys` to keep the order and drop repeats.
    - `services/api/tests/conftest.py`: the FakeBackend versions.
    - `graph.py`:
      - `MAX_IDS`, `IDS`, `_ids` and `_company`;
      - `Chunk.source` (private), with the `section` and `filing` resolvers. They make one lookup per chunk off the citation path, marked with a `ponytail:` comment;
      - `Filing.known_company` and `company`;
      - `FinancialFact.cik`, `known_company` and `company`;
      - `Query.chunks` and `Query.facts`.
    - `clients/operations.graphql`: `Coverage` and `Sources`; `Answer` also selects `refused` and `warnings`. Codegen added `coverage.py` and `sources.py` to `clients/python-graphql`.
    - `main.py`: the description's broker phrase now reads "refused a job or could not be reached" (user question, 2026-10-18). The test row is renamed "broker refused or unreachable".
    - `services/api/tests/test_app.py`: integration assertions for the three lookups in `_page_through_live_backend`, including a filing set to `embedded`, which drops out.
  - **The handoff's next steps (all done on 2026-10-18; results under "Done and checked"):**
    1. **Contract unit tests** in `services/api/tests/test_contract.py`, through the `graphql` fixture:
       - `sources(chunk_ids=["c-2","unknown","c-1","c-2"], fact_ids=["f-1"])` gives chunks c-2 and c-1 (section 7, filing 0000320193-25-000079, company AAPL) and fact f-1 (AAPL).
       - A bounds table: `[]` gives 0; 20 times "c-1" gives 1, the edge row it must accept; 21 ids, a 65-character id and `""` each give `invalid_input`; a 64-character id gives 0.
       - Links on other paths, through a raw POST: `filings(first: 1)` resolves `company`, chunks resolve `section` (1A) and `filing.company`, and facts resolve `company`, all AAPL.
    2. **Run** `make lint`, `make typecheck`, `make test` and `make test-int`. Testcontainers have the user's go.
    3. **`clients/ts/index.ts`:**
       - `ApiError` with status, code, `retryAfterS` and `requestId`. Use no parameter properties, so Node's type stripping can load it.
       - `readApiError(response)` for problem+json and non-JSON bodies, and GraphQL errors' `extensions.code`.
       - `AbortSignal.any([caller, AbortSignal.timeout(ms)])`.
       - A per-call `X-Request-ID`, generated when absent.
       - The base URL's trailing slash stripped.
       - `.ts` extensions on value imports (`./graphql/graphql.ts`), with `allowImportingTsExtensions` in its tsconfig.
       - `@graphql-typed-document-node/core` moved to dependencies.
       - Then `clients/ts/index.test.ts` (`node --test`, with a stubbed `globalThis.fetch` and no server), a `test` script, and the CI contracts job step `- run: npm --prefix clients/ts test`.
    4. **Contract checks:** `make codegen`, then `make contracts-check` (only the unstaged generated files may be listed), `make contracts-breaking` (nothing breaking) and `make actionlint`.
    5. **The eval check:**
       - `git diff --name-only main -- <EVAL_INPUTS>` may list only `services/api/src/filinglens_api/{backend,graph,main}.py`. The harness runs none of the changed code: it imports only `answering`, `limits.ANSWER_TIMEOUT_S` and `schemas`.
       - Then the user confirms that the `eval-calls-*` Actions cache exists, and ships.
    6. **Docs:** context.md (the API section on the lookups), the activity log, memory.md and this item.
  - [x] **Done and checked on 2026-10-18** (fresh session; activity-log.md):
    - **Tree:** it matched the handoff, and `make codegen` changed nothing.
    - **Contract tests:** added as in step 1. The bounds table runs each row against both lookups, and its 20-id row is `["c-1", "f-1"] * 10`. The generated-client test also runs `Coverage`. A `ponytail:` comment went on `_company`.
    - **`clients/ts`:** built test first as in step 3.
    - **Red checks:** the contract and integration tests came after the code, so red checks stand in. 6 mutations of `graph.py`, 9 of `clients/ts/index.ts` and 4 of the LiveBackend SQL each failed a test.
    - **Checks:**
      - `make lint` and `make typecheck` (0 errors) clean;
      - `make test` 359 passed and `make test-int` 31 passed;
      - `npm --prefix clients/ts test` 14 passed, with `tsc --noEmit`;
      - `make contracts-check` lists only B1's 15 files (6 hand-edited, 9 generated), unstaged until ship commits them;
      - `make contracts-breaking` reports nothing breaking, and `make actionlint` is clean.
    - **Eval check:**
      - Of the eval inputs, only `backend.py`, `graph.py` and `main.py` differ from main.
      - The harness never loads `graph` or `main`. It loads `backend` through `limits` and calls none of its changed code (memory.md).
      - So CI's eval computes main's keys.
    - **Final review:** a fresh subagent; verdict "with fixes", no Critical (activity-log.md, memory.md).
      - Fixed, test first: the REST client now throws an error reply as `ApiError`.
      - Ruled: 20 ids per call stays, and the BFF batches fact ids (B2 block). The query fan-out goes to step 10 (its notes).
      - Deferred minors: Pending, "B1 review minors".
      - All checks above passed again on the final tree.
  - [x] (user, 2026-10-18) `main.py`'s description phrase stays in B1.
  - [x] **The user's additions to B1, done on 2026-10-18** (memory.md, activity-log.md):
    - **Limits:** GraphQL refuses a query deeper than 6 levels or with an alias (`QueryDepthLimiter(max_depth=6)`, `MaxAliasesLimiter(max_alias_count=0)`), before any resolver runs.
    - **NUL:** an id with a NUL is refused as `invalid_input`.
    - **Tests first:**
      - a depth-7 query and a query with one alias are refused, with the backend set to fail if touched;
      - Coverage, the web's deepest query (depth 6), still passes;
      - rows for a NUL (refused) and another control character (looked up), against both lookups.
    - **Red checks:** depth 5, depth 7 and one allowed alias each failed a test.
    - **Links test:** reshaped to stay within depth 6.
    - **Checks:**
      - `make lint` and `make typecheck` (0 errors) clean;
      - `make test` 366 passed;
      - `npm --prefix clients/ts test` 15 passed, with `tsc`;
      - `make contracts-check` lists the same 15 files;
      - `make contracts-breaking` reports nothing breaking, and `make actionlint` is clean;
      - `make test-int`: 30 passed, and `test_twenty_workers_never_exceed_eight_sec_requests_a_second` failed by 10 ms. That test is flaky on this PC today: alone it passed 4 of 5. It is unrelated to B1 (memory.md, Pending).
    - **Eval check:** of the eval inputs, still only `backend.py`, `graph.py` and `main.py` differ from main, with no change the eval runs.
  - [x] (user) Confirm that Actions → Caches lists an `eval-calls-*` entry, then ship with ship. Merged as #9 (a2037af).
  - **Done when:** every make check passes, the eval check shows no model call (memory.md, Preferences), and the user ships it.

- [x] 9, PR A: GraphQL GET and WebSocket off, Retry-After fixed, merged as #8 (35902f3, git log, 2026-10-18). It was the step 9 plan's first PR (approved 2026-10-18), on branch `fix/graphql-get-ws-retry-after` from main.
  - **GET is off entirely**, since nothing sends GraphQL over GET:
    - both generated clients POST;
    - there is no GraphiQL page;
    - web, evals, scripts and tests send no GET.
  - **The change:** `main.py` keeps only the GraphQL router's POST route, which also drops the unused WebSocket route.
  - **Done when:**
    - a GET of `answer` gets 405 and spends nothing: `FakeBackend.answered` stays 0 and no answer token is taken;
    - a POST of `answer` works;
    - the app has no WebSocket route, and `/graphql` only POST;
    - a parametrized test pins which 503s carry Retry-After (none when AI is switched off), and the API description and context.md say the same;
    - `make codegen`, lint, typecheck, test, test-int, contracts-check, contracts-breaking and actionlint pass;
    - the eval check shows no model call (memory.md, Preferences);
    - the user ships it.
  - [x] Built and checked on 2026-10-18 (uncommitted on the branch, with section 0's docs):
    - tests first: the GET and route-table tests failed before the change;
    - `make lint` and `make typecheck` (0 errors) clean;
    - `make test` 345 passed and `make test-int` 31 passed;
    - `make contracts-breaking` reports nothing breaking, and `make actionlint` is clean;
    - `make contracts-check` lists only the two regenerated files (`contracts/openapi.json`, `clients/ts/openapi.d.ts`), unstaged until ship commits them;
    - eval check: of the eval inputs, only `main.py` (router setup, description) and `problems.py` (the 503 doc text) differ from main. The harness imports neither `main` nor that code, so CI's eval replays main's keys.
  - [x] (user) Shipped with ship, and it merged as #8 (35902f3, git log).

- [x] 8. Instrumentation, merged as pull request #6 (febbe5f, git log, 2026-10-18). Its record follows (branch `step-8-monitoring`, created 2026-10-18 from main at 5af8fcd when the user said to start Part B; the user committed it as 5c8cb70 and opened a pull request). Done when OpenTelemetry traces span services end to end, the dashboards and alerts are committed with promtool tests, and the screenshots are saved. Plan approved 2026-10-18 with the user's changes, then the design critique's revisions with three user conditions. Paused on 2026-10-18 at the user's request (context at 75%); a fresh session resumes from this checklist.
  - **Plan file:** `C:\Users\kwonhyuk\.claude\plans\start-step-8-monitoring-iridescent-sedgewick.md`. It holds the approved Part B plan and, at its end, "Revisions from the design critique".
  - **The approved Part B plan, with the critique's revisions folded in:**
    - **What runs where:**
      - `api`, `ingest` and `embed` export OTLP/HTTP only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (empty means off).
        - `.env` holds the host URL `http://127.0.0.1:${OTEL_HTTP_PORT}`.
        - Compose gives the containers `${OTEL_EXPORTER_OTLP_ENDPOINT:+http://otel-collector:4318}`.
        - `OTEL_SERVICE_NAME` is filinglens-api, filinglens-ingest or filinglens-embed.
      - The `observability` profile holds:
        - **otel-collector:** `memory_limiter`; `httpcheck` on `api:/readyz` every 15 s with a timeout; the Prometheus exporter on :8889 with `enable_open_metrics` and `metric_expiration: 1m`; its own metrics on 0.0.0.0:8888.
        - **jaeger:** in memory, `--set` lowering `max_traces` from 100,000 to fit 512 MB; its metrics on :8888.
        - **prometheus:**
          - scrapes the collector :8889 (`honor_labels: true`) and :8888, RabbitMQ `:15692/metrics/detailed?family=queue_coarse_metrics&family=queue_consumer_count` (`celeryev.*` and `*.pidbox` dropped) and Jaeger;
          - 15 s evaluation, `infra/prometheus-alerts.yml`, a named volume, 15 d or 1 GB retention, exemplar storage.
        - **grafana:** datasource uids `prometheus` and `jaeger` with exemplar links; 3 provisioned dashboards; anonymous Viewer in dev only, off in the prod override; analytics off.
      - No new host ports. The monitoring UIs stay on 127.0.0.1.
    - **Traces:**
      - **The ingest job is one trace,** carried by our own Celery signal hooks (no contrib package): `before_task_publish` injects `traceparent` into the headers with no producer span; `task_prerun` and `task_postrun` open and close a CONSUMER span `run/<task>`; `task_failure` sets `error.type` with no message.
      - **The answer** puts stage spans under the request's span, built after each stage from `_Run.lap`, so no span is current across a `yield`. The outcome, refusal code, route and tokens go on the server span. No question text, quotes or prompts are recorded.
      - **Model calls:** `traced_complete` and `traced_stream` give each one a `chat <model>` span with `gen_ai.*` attributes and a `first_token` event, never made current. The Anthropic SDK's own tracing is off.
      - **Search:** a `search` span with one child per phase (embed, sql, load, rerank), built from its laps.
      - **SEC:** one span per request, with kind, status and limiter wait, never the User-Agent.
      - **Request id:** `request_id` goes on the server span.
      - **FastAPI:** `FastAPI(telemetry={"logs": False, "auto_configure": False, "exclude": <probes>})`.
      - **Query strings:** `url.query` keeps parameter names only.
    - **Metrics:**
      - One registry, `filinglens_telemetry/metrics.py` (SPECS). Units are only `s`, `{...}` or none. Labels come from fixed sets only.
      - The alerting counters start at 0 (`start_answer_series`, `start_ingest_series`).
      - The gauges `tokens_today`, `token_budget` and `inflight_limit` are created once in `__main__`. `tokens_today` reads `ai:usage:<UTC date>` through a sync Redis client with 2 s timeouts, and reports nothing on `RedisError`.
      - Cut as duplicates: `answer.duration`, `answer.tokens`, `ai.enabled`, `llm.fallbacks`, `ingest.filings`, `ingest.backpressure` and the Flower runtime.
    - **Dashboards** (`infra/dashboards/*.json`):
      - Service health: is it up, fast and error-free?
      - Answers and LLM: are answers good, fast and affordable?
      - Ingest pipeline: is ingestion moving, against 500 filings in 2 h?
    - **Alerts** (13, no delivery yet):
      - ApiNotReady: `min by (http_url) (httpcheck_status{http_status_class="2xx"}) < 1` for 2 m, label names checked live.
      - WorkerNotConsuming: 0 consumers on a work queue for 5 m.
      - SecRefused.
      - AnswersFailing: 2 or more failed answers in 30 m. A cancellation counts as a timeout at 30 s or more, otherwise as `cancelled`.
      - AiBudgetExhausted: tokens reach the budget and the budget is above 0.
      - AiBudgetNearlyUsed: a ratio of at least 0.8 and below 1.
      - LlmProviderErrors: error ratio per provider above 25% over 30 m, with at least 4 calls.
      - CitationValidationDegraded: 6 h window, at least 8 answered.
      - SearchDegraded: rerank timeouts against reranks, over 1 h.
      - DeadLetters.
      - IngestStalled: ready messages but no succeeded or dead-lettered task in 15 m (`or vector(0)`).
      - MonitoringTargetDown.
      - TelemetryMissing: `absent(target_info{job=...})` for api, ingest and embed, for 10 m.
    - **Robustness:**
      - `worker_process_init` sets telemetry up and `worker_process_shutdown` flushes it, because children exit through `os._exit`.
      - Exporter URLs end in `/v1/traces` and `/v1/metrics`, with 10 s timeouts.
    - **Tests:**
      - In-memory exporters are installed once per session in the root conftest; `configure_telemetry` never runs with an endpoint inside pytest.
      - The secrets scan covers span attributes, events, status and resource.
      - Metric labels are checked against an allowlist.
      - A drift test checks the dashboards and alerts against SPECS, plus a `/metrics` capture saved during the live check.
      - Every alert has promtool tests (`make monitoring-check`, run in the CI lint job), alongside `promtool check config` and `otelcol-contrib validate`.
      - The e2e trace test uses an in-test OTLP sink, `OTEL_BSP_SCHEDULE_DELAY=200`, and a fixed `traceparent` on the POST.
  - **User decisions:**
    - No alert delivery yet; step 10 adds Alertmanager.
    - The live check runs on a throwaway compose project `filinglens-demo`, only after the user's go, never during Triage Copilot's exam (2026-10-18 to 20, after 15:00 Taipei).
    - It touches nothing outside `filinglens-demo`.
    - Exactly 10 answers with Claude off, stopping at the first quota error.
    - Uvicorn's access log drops query values.
    - Dependencies `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` 1.45.1 approved (the Celery instrumentation package is dropped).
  - **User conditions on the revisions (2026-10-18):**
    - **Celery tracing tests:** the own Celery tracing gets tests. The integration test shows one trace id from `POST /v1/ingest-jobs` through discover, fetch, parse, chunk, embed and facts. A failed publish, such as discover's nack on a full fetch queue, leaves no span open or current.
    - **LlmProviderErrors** keeps a minimum call count in its window, like the other ratio alerts, so a single error cannot fire it.
    - **Every alert,** TelemetryMissing included, keeps a firing and a quiet promtool case.
  - **Live-check conditions (user, 2026-10-18):**
    - Ask the user before starting the throwaway stack (`docker compose -p filinglens-demo --profile observability`), and never start it during Triage Copilot's exam (2026-10-18 to 20, after 15:00 Taipei).
    - FreightAudit's prod stack (`freightaudit-prod`) runs on this PC. Touch no container, network or volume outside `filinglens-demo`, the dev `filinglens` stack included. The alert drills stop only `filinglens-demo` containers.
    - Exactly the planned 10 answers, with Claude off (`LLM_ANSWER_FALLBACK` blank, demo only): no retry loops, and stop at the first quota or rate-limit error.
    - Teardown:
      - List the volumes filtered by `com.docker.compose.project=filinglens-demo` before and after.
      - Remove only that project's volumes, by name. Never prune.
      - If the safety check blocks it, hand the user the command.
    - Ports come from 15433-15499 and are checked free first. `corpus-v1.dump` is restored into the demo Postgres, and 3 companies outside the golden set are ingested live (about 10 SEC requests).
    - Screenshots are taken with headless Chrome, its profile under `H:\.cache`, and checked for keys, the contact email and personal data.
  - **AGENTS.md log rule (user, 2026-10-18), for the step-8 branch, not Part A's:**
    - Every entry in `docs/activity-log.md`, and in `docs/memory.md` when it records a problem or decision, includes small events too: a failed command, a skipped check, a tool that behaved unexpectedly, a setting changed.
    - Each entry states what happened, why it happened ("not confirmed" when it's a guess), and what we did, with the exact steps in order and why that was the best option.
    - Mistakes are logged the same way and never edited out. Past entries are not rewritten.
    - **Status:** already added to AGENTS.md's Documentation Rules on `step-8-monitoring` (uncommitted).
  - **Done on `step-8-monitoring` (uncommitted; ruff and pyright clean; tests not run yet):**
    - [x] Dependencies:
      - `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` 1.45.1 and `celery` in packages/telemetry; `filinglens-telemetry` in llm, retrieval and sec_client.
      - Everything locked was released at least 7 days before (newest 2026-10-06).
      - protobuf 7.36.2 loads its native `upb` here, so no fallback is needed.
    - [x] `filinglens_telemetry`:
      - `metrics.py` (registry, SPECS, start series, gauges);
      - `otel.py` (providers, `install`, `configure_telemetry`, `shutdown`, `QueryNames`, `trace_celery`);
      - `__init__.py`: `query_names`, the `uvicorn.access` filter, trace ids on log lines.
    - [x] Settings: `TelemetrySettings` (`OTEL_EXPORTER_OTLP_ENDPOINT`, empty means off; `OTEL_SERVICE_NAME`), defaults filinglens-api and filinglens-ingest.
    - [x] Answers (`answering.py`):
      - refusal codes (`_plan` returns code and text; `_refusal(code, text, ...)`);
      - stage spans from `_Run.lap`;
      - `_record` and `_outcome` in the `events` finally block;
      - INFLIGHT and the overloaded rejection in `admit`.
    - [x] Rejections: `rate_limited` in `limits.answer_limits`; `ai_disabled`, `budget_unavailable` and `budget_exhausted` in `budget.check`.
    - [x] Providers:
      - `traced_complete` and `traced_stream` on all three classes;
      - `Provider.complete` is now `def ... -> Awaitable[Completion]`, because the decorated methods' `Awaitable` return did not match the protocol's `async def` (CoroutineType);
      - the Anthropic client gets `open_telemetry=False`.
  - **Small events so far (for the activity log, under the new rule):**
    - The Part B branch was made when the user said to start Part B. The pause answer later said not to create it; it already existed, so it was left as it was and this was reported.
    - `uv add` wrote a `[tool.uv.sources]` block into the llm, retrieval and sec_client pyprojects. No other member has one, because the root's sources cover it, so they were removed; `uv lock --check` passed.
    - pyright strict (packages) found no stubs for `celery` in `otel.py`. Fixed with targeted `pyright: ignore` comments on the import and on `signal.connect`.
    - ruff flagged 2 long lines in `metrics.py`, which `ruff format` wrapped, and an unsorted import in `providers.py`, which `ruff check --fix` fixed.
    - The edit-gate hook refuses each file's first edit until its callers and the instruction are restated; the same edit then passes. That is expected hook behavior.
  - **Session 2 (2026-10-18, from 02:07 Taipei):** the uncommitted work above passed `make lint`, `make typecheck`, `make test` (289) and `make test-int` (29) before anything new was added.
  - [x] Wiring:
    - **API `__main__`:** `configure_telemetry`, `observe_answer_limits` (`budget.tokens_today` on a sync Redis client with 2 s timeouts), `start_answer_series` with the configured models.
    - **API `main.py`:** `FastAPI(telemetry={"logs": False, "auto_configure": False, "operation_spans": False, "exclude": <probes>})` and `request_id` on the server span. Operation spans are off so the server span stays current in routes and carries the answer (ruling, memory.md).
  - [x] Retrieval: a `search` span with one child per phase, built from its laps; `filinglens.search.duration` by phase and total; `RERANK_TIMEOUTS` where `_rerank` times out. Neither the query nor exception messages go on the span.
  - [x] Ingest: `worker_process_init` (telemetry and zero series per process) and `worker_process_shutdown` (flush), `_attempt` outcomes and duration plus `filinglens.ingest.outcome` on the run span, a `fetch queue full` event, embed chunks, SEC client spans (`SEC GET <kind>`) and counters (requests, cool-offs, refusals).
  - [x] Infra:
    - collector (`memory_limiter`, `httpcheck` with a 10 s timeout, `enable_open_metrics`, `metric_expiration: 1m`, its own metrics on 0.0.0.0:8888);
    - Prometheus (scrapes with `honor_labels`, RabbitMQ's detailed endpoint, rules, 15 s evaluation, volume `prometheus-data`, 15 d or 1 GB, exemplar storage);
    - Grafana (uids, exemplar links, 3 dashboards in a FilingLens folder, anonymous Viewer in dev only, analytics off);
    - compose (`${OTEL_EXPORTER_OTLP_ENDPOINT:+http://otel-collector:4318}`, `OTEL_SERVICE_NAME=filinglens-embed`) and prod override; Jaeger `max_traces` 20,000; `.env.example`.
  - [x] Alerts (13) and promtool tests (a firing case each, one quiet group for all 13); `make monitoring-check`; CI lint step.
  - [x] Tests: unit (setup, query names, access log, trace ids in logs, answers for every outcome, providers, SEC, `_attempt`, Celery propagation with a failed publish, secrets in spans, label allowlist, drift), integration (end-to-end trace from the API through every task to an OTLP sink, search spans and metrics, rejection counters). Red checks: each new group fails when its code is broken.
  - [x] Checks (2026-10-18): lint, typecheck (0 errors), test (323 passed, 1 skipped until the live capture), test-int (31 passed), actionlint, monitoring-check, contracts-check (no drift), secrets-scan (no leaks; the new files too).
  - [x] Final review (fresh subagent): approved; 4 findings fixed test-first (query names, session-wide label check, promtool cases, the citation alert's denominator) and the plan's `run/<task>` names and fallback events added. One minor deferred: the e2e secrets scan checks whole connection URLs, since their bare password `test` occurs legitimately.
  - [x] Live check on `filinglens-demo` (2026-10-18, 19:41-19:58 UTC; results in the activity log): corpus restored, 3 companies ingested live (9 SEC requests, job succeeded), exactly 10 answers (6 answered, 4 refused, 0 errors, no quota stop), both drills fired and cleared, every assumed label name confirmed (none corrected), 5 screenshots in `docs/screenshots/`, the capture in `packages/telemetry/tests/fixtures/metrics-capture.txt`, teardown by label and name (no volume left). The images `filinglens-demo-{api,ingest,embed}` remain (outside the teardown rules; the user decides).
    - **User go: 2026-10-18 03:35 Taipei, with these additions:**
      - If the conversation is summarized during the run, re-read these live-check rules (above and here) before continuing, the teardown rules above all.
      - If Claude Code's safety check refuses a delete, stop and give the user the exact commands; never work around it. Leaving the stack up until the user is back is fine.
      - If any step would touch anything outside `filinglens-demo`, stop and ask first.
      - The final report gives: the 10 answers (provider, tokens, any refusal or error), both drills (alert fired and cleared, with times), the screenshots and the `/metrics` capture saved, any label names corrected, and the volume lists before and after teardown.
      - Docs as AGENTS.md describes; no commit. It also saves `packages/telemetry/tests/fixtures/metrics-capture.txt` (names and label names only) for the drift test's third-party check, and confirms the httpcheck label names.
  - [x] Docs: `docs/monitoring.md`, README, context, memory, activity log (2026-10-18). After the live check: the screenshots, the capture, and any label name it corrects.
  - [x] CI fix (2026-10-18, uncommitted): the PR's eval job stopped at startup, because `ApiSettings` had lost the empty-means-off rule for `OTEL_EXPORTER_OTLP_ENDPOINT` (validator name clash; memory.md). Validators renamed and a test added; `make lint`, `make typecheck` and `make test` (326) pass.
  - [x] Added to this change set (user, 2026-10-18, uncommitted): the docs say CI runs on GitHub and step 7 is merged, with its steps 3 and 4 confirmed, and the nightly cron moved to 19:17 UTC (`make actionlint` passes).
  - [x] The user committed and pushed the fix and these additions, and the pull request merged as #6 (febbe5f, git log).

- [x] The x18 fix, merged as #7 (f58524b, git log, 2026-10-18):
  - validation fails a bracketed marker that names no source (x18's `[12]`);
  - the eval refuses to judge a sentence that cites a number with no source, before any call;
  - the nightly's artifact keeps a report that replaced a committed one (`--modified`).

  `make test` (331 passed), `make lint`, `make typecheck` and `make actionlint` passed locally (activity-log.md, 2026-10-18).
- [x] GraphQL answer guards and the SSE in-flight cap (2026-10-18, merged as #5): GraphQL answers take REST's 10-a-minute bucket, budget and 30 s limit through the same code, and an answer counts in flight from admission. `make test` 289 passed, `make test-int` 29 passed.
- [x] 7. CI/CD (design doc prompt 7). **Merged as pull request #1 (2026-10-18): CI #1 failed on the floor problem fixed with Wilson intervals; CI #2 on its next push and CI #3 on the push to main passed (public Actions page, read 2026-10-18 03:07 Taipei).** **Plan approved 2026-10-17 with all 8 recommendations and five user additions; built and checked locally the same day.** Done when actionlint passes and a test PR shows every job green, with `make contracts-check` and `make contracts-breaking` (against main) among the jobs.
  - **Manual (user, on GitHub):**
    1. [x] The public repo `kwnhyk04/filing-lens` exists, empty (user, 2026-10-17). It requires actions pinned to full-length commit SHAs. All 32 remote `uses:` in `.github/` are pinned that way, checked the same day.
    2. [x] Actions secrets `GEMINI_API_KEY` and `GROQ_API_KEY`, both CI-only keys (user, 2026-10-17). Never `ANTHROPIC_API_KEY`. No `NVIDIA_API_KEY` (evals never call a fallback) and no Dependabot secrets.
    3. [x] Once main is pushed: a release tagged `corpus-v1` with `.cache/corpus/corpus-v1.dump` attached. It was made on 2026-10-17: 46.5 MB, sha256 `50faa04aa39bc16b622235ebc33f223d86a9dba870d38365870bf057bc6a52c0`, pinned in `evals/corpus.py`. Its table list is in the activity log, for the user's review before the public upload. Confirmed (user, GitHub's API, 2026-10-18): published 2026-10-17 at 15:28 UTC with `corpus-v1.dump` (46.5 MB, 16 downloads).
    4. [x] After the first CI run: a ruleset on main that requires a pull request and the `ci-ok` check and blocks force pushes. Done (user, GitHub's API, 2026-10-18): ruleset 25308468 is active on main, with a pull request required (0 approvals), `ci-ok` required (not strict), and force pushes and deletion blocked.
    5. Optional, before step 10: make the GHCR packages `filinglens-api` and `filinglens-ingest` public, or log the PC in to ghcr.io.
  - **Before the first push:** full-history gitleaks scan on 2026-10-17: 12 commits (about 7.9 MB), no leaks. Commit authors use the GitHub noreply address, and no personal email is in a tracked file. `make secrets-scan` runs again right before the push.
  - [x] **Built (2026-10-17):**
    - `.github/workflows/ci.yml`, `.github/workflows/nightly-eval.yml`, `.github/actions/setup/action.yml` and `.github/dependabot.yml` (details in context.md).
    - `infra/Dockerfile`: base images pinned by digest, and a `HEALTHCHECK` on `/healthz`.
    - Makefile: `corpus-dump`, `corpus-restore`, `actionlint`, `secrets-scan`, `vuln-scan` and `image-scan`.
    - `evals/harness.py --ci` and the new exit codes (2 quota or rate limit only, 4 every other failure).
    - `evals/corpus.py`, with tests in `evals/tests/test_ci.py` and `test_corpus.py`.
    - The codegen bump for CVE-2026-104852 (memory.md).
  - [x] **Checked locally (2026-10-17):**
    - `make lint`, `make typecheck` (0 errors), `make test` (283 passed), `make test-int` (28 passed) and `make actionlint` (with shellcheck).
    - `make secrets-scan`: 12 commits, no leaks; the new files are clean too. `make vuln-scan`: 0 findings.
    - `make image-scan` on both images: 0 critical, and 44 HIGH Debian packages without a fix (not gated).
    - The image healthcheck command passed in the running api, ingest and embed containers. `make codegen` leaves the clients unchanged.
    - On the restored corpus (throwaway compose project `filinglens-corpus-check`, port 15433):
      - `--ci` without floors exits 4 before any call.
      - `--ci` on the test split's retrieval passes, 2 gated floors, with latency "not gated". It reproduced the official recall@10 0.583 and MRR@10 0.833. Its report was deleted afterwards.
      - The CI migration steps: 0008, down to 0007, up to 0008.
      - Two restores gave identical top 10s on all 70 dev questions.
  - [x] **Dev reports for the floors (2026-10-17, shown to the user; no floors written):**
    - `20261017T103956Z-retrieval-dev-full` (restored corpus): recall@10 0.613, MRR@10 0.649, nDCG@10 0.585, retrieval p95 289 ms.
    - `20261017T104130Z-answer-dev-ci` (restored corpus, `--no-judge`, every call from the cache, 0 tokens): numeric 1.000, comparison 1.000, coverage 1.000, correct refusal 1.000, false refusal 0.133, 0 errors.
    - `20261017T104033Z` is the same retrieval eval on the dev database, as a comparison.
  - [x] **Dev floors written (2026-10-17, after the user's review):**
    - `retrieval:dev:full`: recall@10 ≥ 0.542, MRR@10 ≥ 0.577, retrieval p95 ≤ 478 ms.
    - `answer:dev:ci:gemini:gemini-3.5-flash-lite`: numeric ≥ 0.920, coverage ≥ 0.950, correct refusal ≥ 0.900, false refusal ≤ 0.333, input tokens ≤ 8,000, output tokens ≤ 474, cost ≤ $0.0029, billed $0.
    - Retrieval accuracy uses the measured value less 1/14 (user rule; memory.md, eval card). Both reports pass their floors, with and without latency gated.
  - [x] Throwaway volume `filinglens-corpus-check_postgres-data` removed (user request, 2026-10-17).
  - [x] **First PR's CI eval failure (correct refusal 0.800 against 0.900), handled 2026-10-17; nothing committed:**
    - The miss: t07, answered live from the FY2025 10-K. The router gave no fiscal year in both runs, so the result rested on Gemini, which refused in the cached run. Model variation; not answerable. Labels unchanged.
    - The answer path is unchanged since 10:41:30: prompt hashes, models, settings, index and manifest are identical.
    - Pass/fail metrics now use Wilson intervals, and `--set-floors --replace` exists. Tests: 5 of 5, 0 of 5, 3 of 5, the replace path, and the ci subset (eval tests 36 passed).
    - The ci subset gained a04, a07, a09, t04 and t08: 25 questions, 10 should-refuse.
    - Dev ci floors were replaced from a fresh live run (`20261017T154912Z`, 27.7K gpt-oss-20b, 20 Gemini calls, no judge).
  - [x] Test floors replaced by code from the saved exam report (user decision, 2026-10-17, no new run; `--set-floors evals/reports/2026-10-17.json --replace`):
    - numeric 0.92 to 0.758, correct refusal 0.90 to 0.646, false refusal 0.261 to 0.321;
    - retrieval recall@10 0.314 to 0.416, MRR@10 0.500 to 0.667.
    - `retrieval:dev:full` re-derived from its own report the same way, unchanged. There are no other floor keys, and no Haiku key.
    - Each report passes its floors.
  - [x] **The test PR (2026-10-18):** CI #2 on pull request #1's next push and CI #3 on the push to main passed. Step 4 is done (above); step 5 stays in Pending. Whether `make secrets-scan` ran right before the push is not recorded.
  - **Eval in CI:**
    - Runs only when an eval input changed: `packages/{core,db,llm,retrieval,telemetry}/src`, `services/api/src`, `evals` (reports, tests and Markdown left out) or `uv.lock`, or on a manual run.
    - Pull requests: the retrieval suite on dev full (local models, no LLM call), then the answer suite on dev ci with `--no-judge`. The reports go to the PR comment, the job summary and an artifact.
    - Nightly (19:00 UTC, only when the eval inputs changed since the last complete nightly run): the test split with the judge. It uploads the report and opens an issue when a floor breaks.
    - The model reply cache carries over between runs, so a rerun spends only on calls not yet made.
    - CI pins `LLM_PRIMARY`, `LLM_ROUTER` and `LLM_JUDGE` to the free models, sets `LLM_ANSWER_FALLBACK` empty, and sets `LLM_FALLBACK` to the router's Groq model only so startup validation passes.
  - **Stops (user addition):** only a quota or rate limit stop (exit 2) is INCOMPLETE and says to rerun after the quota resets. Every other failure fails plainly with its reason (exit 4 under `--ci`), and each one writes a verdict and an error annotation. No workflow step can fail without failing its job.
  - **Tokens per run** (from measured runs; cached replies cost nothing):

    | Run | gpt-oss-20b (router) | gpt-oss-120b (judge, shared with FreightAudit) | Gemini |
    | --- | --- | --- | --- |
    | PR answer eval, dev ci, first run | about 22K (20 calls; 22.2K measured on 2026-10-16) | 0 | about 16 requests |
    | PR answer eval, later pushes with unchanged prompts | 0 | 0 | 0 |
    | PR retrieval eval | 0 | 0 | 0 |
    | Nightly, test split, judge on | about 33K (33.2K measured) | about 18-28K (17.9K and 28.1K measured) | about 25 requests |

  - **Decisions (approved 2026-10-17, all 8 recommendations):** retrieval on dev full; quality floors only in CI; NOT RUN for Dependabot and fork PRs, with the nightly as backstop; no second answer eval on main; Trivy rather than pip-audit, ignoring findings with no fix; one ci.yml; the nightly with the judge at 19:00 UTC; the corpus as a public release asset.
  - **User additions (2026-10-17):**
    - Only a quota stop says to rerun after the quota resets.
    - NOT RUN is shown at the top of the PR comment and the job summary.
    - The corpus's table list is reviewed before the upload, and it holds only public SEC data.
    - Trivy runs only from a digest-pinned image, never a hijacked version or its actions, with no secrets in the scan jobs.
    - Latency is reported, marked "not gated".
  - **Risk:** git inside the oasdiff and gitleaks containers may refuse the runner-owned checkout ("dubious ownership"). The `safe.directory` setting should cover it; the test PR shows whether it does. It does: CI passes on GitHub (user, 2026-10-18).
- [x] 6b (2026-10-17). Golden set v1, judge calibration, eval harness and the full eval (plan approved 2026-10-16).
  - Done 2026-10-17:
    - Labeling and calibration are complete. The full eval ran on the test split, its report lists every target with pass, fail or not measured, and the floors are written.
    - `make test` and `make test-int` are green.
    - Results and every miss, with v2 ideas: README and eval card. Done when labeling and calibration are complete, the full eval runs on the test split, the report lists every target in `docs/context.md` with pass, fail or not measured, and `make test` and `make test-int` stay green.
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
    - [x] **Follow-up judge check (eval card), 2026-10-17:** `make calibrate ARGS="followup import"`, a spot check with no kappa.
      - Done 2026-10-17 at 07:17 UTC. The judge failed 3 of the 4 sentences Claude labeled not supported (s01, s02, s05) and missed s04 (t07). It passed s06; s03 is unscored (its reply judged 3 sentences for 1). Spent 6 calls, 9.9K gpt-oss-120b. Eval card updated.
      - Built (2026-10-16): a second sample in `evals/calibration/v1-followup/`, from 4b first, topped up from 4a, never from 4c; v1 stays frozen. `spot_check` reports how many of the sentences labeled not supported the judge failed too. Unit tests for the draw and the spot check.
      - 6 sentences (2 from nemotron, 4 from gpt-oss-20b), short of about 10. Claude's labels: 2 y, 4 n, under the written criterion (a computed number is not stated). They check out against the sample (`imported`).
      - Cost: 6 judge calls, about 8.7K input tokens, so about 11K gpt-oss-120b. Not on 2026-10-16: FreightAudit's CI needs gpt-oss-120b that evening.
  - [x] **Router misses checked (user request, no quota, 2026-10-16):** not clearly worse than the rest on recall or answers, so no deterministic fill. Numbers in memory.md.
  - [x] **Reports record the code and prompts (user request, 2026-10-16):** `code_version` (commit, uncommitted changes, source sha256) and `prompt_hashes` (system prompts and schemas). `make test` 255 passed; ruff and pyright clean.
  - [x] **Test run (golden v1 test split), 2026-10-17: approved by the user on 2026-10-16, with conditions.** `make eval SUITE=all SPLIT=test`, judge on; no `--tag`, the production path. The 30 questions are 12 numeric, 6 textual, 5 comparison, 4 unanswerable and 3 time traps.
    - **Done 2026-10-17 at 07:24 UTC:** exit 0, report `evals/reports/2026-10-17.md`, the `eval_runs` row saved. 30 questions, 0 errors, 29 all-live.
      - Before it: the stack had exited (exit 255, likely a Docker restart) and every RabbitMQ queue was empty. api, ingest and embed were rebuilt and are healthy.
      - Integrity: commit `77e59a0`, `dirty` false, source sha256 `b238808a…`. Calibration v1 and manifest hashes match. Golden v1 is frozen and the corpus is unchanged.
      - Pass: numeric exact match 1.000, coverage 0.971, faithfulness 0.970, correct refusal 1.000, MRR@10 0.833, TTFT p95 1.84 s, answer p95 2.15 s, tokens, cost.
      - Fail: false refusal 0.130 (the router sent x13, x14 and x18 out of scope), citation precision 0.944 (c02's conclusion), recall@10 0.583 (n 6), TTFT p50 1.55 s.
      - Not measured: retrieval p95 at about 250k chunks.
      - Spent: gpt-oss-20b 33.2K, gpt-oss-120b 17.9K (judge), Gemini 23 calls.
    - [x] **Floors (written 2026-10-17 after the user's review, `--set-floors evals/reports/2026-10-17.json`):** `evals/thresholds.json` holds:
      - `retrieval:test:full`: recall@10 ≥ 0.314, MRR@10 ≥ 0.500, retrieval p95 ≤ 545 ms.
      - `answer:test:full:gemini:gemini-3.5-flash-lite` (answer floors are now per primary model): numeric exact match ≥ 0.920, citation precision ≥ 0.833, coverage ≥ 0.914, faithfulness ≥ 0.906, correct refusal ≥ 0.900, false refusal ≤ 0.261, TTFT p50 ≤ 2,429 ms, TTFT p95 ≤ 2,000 ms, answer p95 ≤ 6,000 ms, input tokens ≤ 6,354, output tokens ≤ 332, cost ≤ $0.0021 paid-equivalent, billed $0.
      - Later test runs of the same setup exit 1 past any of them.
  - [ ] **Claude Haiku 5.5 as the answer's first fallback (user request, 2026-10-17; Anthropic credits that expire 2026-11-10).** Decisions in memory.md.
    - [x] Built:
      - The `Anthropic` provider on the official SDK (`anthropic` 1.15.0) and `LLM_ANSWER_FALLBACK` (empty by default, so the chain stays free-only).
      - The answer chain Gemini, Claude while it is on, NVIDIA. The router's chain is unchanged.
      - Claude's credits-gone rules, the expiry date, and a single retry of a short 429.
      - Cost from usage (`credits_usd`, `Usage.cost_usd`, cost as billed in evals).
      - The judge can never be Claude, and neither can the router or `LLM_FALLBACK`.
      - Evals pin one model; credits gone exit 2.
      - The $0 billed floor applies to the free setup only, and answer floors are keyed per primary model.
      - `.env.example`, compose and the README are updated.
    - [x] Tests (all on mock transports): 402, a 400 naming a spend limit, a 429 without Retry-After, a short 429 retried and a long one not, the expiry date, a refusal, stream usage and cost, the chain order, Claude skipped after credits are gone, the settings defaults and guards, the judge guard, billed floors, and exit 2 in an eval. `make test` 271 passed, `make test-int` 28 passed; ruff and pyright clean.
    - [x] Dev run with Haiku pinned, once, no tuning, no judge (report `20261017T075734Z`): credits $0.0354, gpt-oss-20b 76.3K. Breakage found: adaptive thinking uses up the shared 1,024-token answer cap. 4 answers were cut; 3 regenerations had no text, so 3 false refusals. n17 and n24 answered INSUFFICIENT_EVIDENCE despite their fact. Details in the eval card.
    - [x] User decisions (2026-10-17): Claude's thinking off with the 1,024-token cap kept; a dev rerun with `--primary-tag`; then the Haiku test split pinned, with the judge, as a comparison and with no tuning; then an api rebuild.
    - [x] Dev rerun, thinking off (`20261017T082532Z`, `--primary-tag=nothink`, router replies cached): 0 truncated, 0 empty replies, 0 errors; false refusal 0.058 (n17, n24, x15). Claude's own first token p95 1.08 s against 3.03 s, paired. Credits $0.0381; gpt-oss-20b about 1K.
    - n17 and n24 still answered INSUFFICIENT_EVIDENCE. Cause: the fact heading reads "fiscal 2025 Q2" for a year-end value taken from a 2026 Q2 10-Q (memory.md, Known Issues). Not fixed.
    - [x] Haiku test split, pinned, judge on, a comparison with nothing tuned (`20261017T082950Z-answer-test-full`):
      - Numeric 1.000, citation precision 1.000, coverage 1.000, faithfulness 0.979, correct refusal 1.000, false refusal 0.000, TTFT p50 1.58 s and p95 2.71 s.
      - The router ran afresh and routed x13, x14 and x18 as textual this time, so the refusal gap is router variance.
      - No Haiku-specific misses on test.
      - Spent: credits $0.0177; gpt-oss-20b 33.2K; gpt-oss-120b 28.1K.
    - [x] Fair comparison (user request): the Haiku test split rerun on Gemini's exact router replies (`--router-primary=gemini:gemini-3.5-flash-lite --primary-tag=fair`, `20261017T084716Z`). It replaces the run above in the README and eval card.
      - Results: citation precision 0.958, faithfulness 0.944, false refusal 0.130 (the same router calls), own first token −0.13 s at p50, paired.
      - Spent: $0.0145 in credits, 19.2K gpt-oss-120b, 0 gpt-oss-20b.
    - [x] Floors checked (2026-10-17): `ttft_p50_ms` is 2428.95 on disk (the 0 was a cut paste); it follows the rule, as does `ttft_p95_ms` 2000.0 (target met, so capped at the target). No change.
    - [x] Floors written from Gemini's test report; README and eval card carry the official table, a Haiku column, every miss explained, and v2 ideas.
    - [x] api rebuilt and restarted on the Part 2 code (anthropic 1.15.0, thinking disabled; healthy). `.env` still has `AI_ENABLED=false` and no `LLM_ANSWER_FALLBACK`, so answers stay off and the chain stays free-only. Later the same day the user set `LLM_ANSWER_FALLBACK=anthropic:claude-haiku-5-5` in `.env`; `AI_ENABLED` stays false until step 10.
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
