# To-Do

Concise, verifiable tasks. Move items between sections as status changes. Trim old completed items when the list grows large; the activity log keeps the history.

Each step maps to a Claude Code prompt in the design doc. Done when the check after the colon passes.

## Pending

- [ ] (manual, step 7, optional before step 10) GitHub step 5 under Completed, step 7: make the GHCR packages `filinglens-api` and `filinglens-ingest` public, or log the PC in to ghcr.io.
- [ ] Dependabot's npm group pull request #3 failed CI (public Actions page, 2026-10-18 03:07 Taipei). Not looked into yet.
- [ ] (manual, user; the fix merged as #7) Nightly eval: start one run by hand (Actions, Nightly eval, Run workflow), then check that the next scheduled run happens (19:17 UTC, 03:17 Taipei). Expected: PASS, and the artifact holds the report JSON under `reports/`.
  - The first manual run (39068994474, 2026-10-18, main at febbe5f) proved the workflow runs. All 30 test questions ran, then it exited 4 on x18's judge error: a dangling `[12]` the validator let through. c15 was refused after validation dropped every sentence twice, which is answer-model variation, not a regression. Its artifact held only the verdict (activity-log.md, memory.md).
  - Before #7, a scheduled run would replay the x18 judge error from the reply cache and exit 4. An exit-4 run is not complete, so the gate measures again.
  - The user reports what the runs showed. Claude Code reads no Actions page and runs no gh (AGENTS.md, Git).
  - A manual run always runs the eval, because the unchanged-inputs gate skips scheduled runs only. The reply cache carries over, so after the fix only x18's regeneration and judge call go live. A cold cache spends about 33K gpt-oss-20b, 18-28K gpt-oss-120b (the judge, shared with FreightAudit's Groq account) and about 25 Gemini requests.
  - After a complete manual run, a scheduled run with unchanged inputs shows SKIPPED and spends nothing. It still proves that the schedule fires.
- [ ] (manual, optional) pre-commit keeps its cache on C: (`C:\Users\kwonhyuk\.cache\pre-commit`, gitleaks build included), because `PRE_COMMIT_HOME` is unset. AGENTS.md wants caches on H:: set `PRE_COMMIT_HOME=H:\.cache\pre-commit` for the user, then remove the old folder (found 2026-10-17).
- [ ] (manual, before step 10) Vercel and Tailscale accounts created.
- [ ] (manual, before step 10) Replace the example passwords in `.env`, and set both `API_KEY` and `ADMIN_API_KEY` (step 2 appended a random `ADMIN_API_KEY`).
- [ ] (manual, optional) Remove the unused Docker volume `filinglens_sec-cache` (`docker volume rm filinglens_sec-cache`); the SEC cache now lives in `.cache/sec`.
- [ ] Live embedding swap (after step 6; user decision): with dev on the last revision before 0004 (now 0008), record the model A baseline (`make eval`, recall@10 and MRR@10, golden set version); run 0004, the reembed backfill, 0005 (run `make check-parallel-hnsw` first, then pick a parallel build within the 256 MB `shm_size` or a serial one with more `maintenance_work_mem`, by corpus size; runbook step 3), the catch-up run and the flip to `embedding_v2`; run `make eval` again on the same golden set; record both runs in `eval_runs` and the activity log; then run 0006 in the next release and set `.env.example` to `embedding_v2`. Done when both recall@10 values are recorded and dev is at head. Runbook: `docs/migrations.md`.
- [ ] (later idea, user, 2026-10-16) A deterministic check for derived numbers: recompute a percent of a stated total, or the difference of two cited figures, from the cited figures themselves, so correct arithmetic can pass validation and wrong arithmetic gets caught. Today validation rejects every derived figure (memory.md, step 6a), and the judge criterion counts a computed number as not stated.
- [ ] (after step 6) Decide how a company that changes CIK in a restructure is handled (for example a `cik_aliases` table), since `get_financial_fact` looks facts up by CIK. Known case: XOM (Exxon Mobil Corp, CIK 34088, filed the latest 10-K; SEC now lists the ticker under ExxonMobil Holdings Corp, CIK 2115436).
- [ ] Claude Haiku 5.5 as the answer fallback: `LLM_ANSWER_FALLBACK=anthropic:claude-haiku-5-5` is set in `.env` (user, 2026-10-17). `AI_ENABLED` stays false until step 10 (user), so no answer calls run before then; `.env` has no `AI_ENABLED` line, so the default (false) applies. Its credits expire 2026-11-10. CI never calls Claude (step 7).
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
- [ ] 9, PR B1, the API lookups (from main after PR A merges, branch `step-9-api-lookups`). Plan: section "PR B1".
  - GraphQL `chunks(ids)` and `facts(ids)`:
    - 1 to 20 well-formed ids, otherwise `invalid_input`;
    - order kept;
    - unknown ids, and chunks of filings that are not indexed, left out.
  - `Chunk.section`, `Chunk.filing`, `Filing.company`, `FinancialFact.company`.
  - `Backend.get_chunks` and `get_facts`: one SQL each in LiveBackend, plus FakeBackend.
  - The `Coverage` and `Sources` operations, and `Answer` also selecting `refused` and `warnings`.
  - clients/ts:
    - `ApiError` (status, code, Retry-After, request id);
    - `AbortSignal.any`;
    - a per-call `X-Request-ID`;
    - the trailing slash;
    - `.ts` imports;
    - `@graphql-typed-document-node/core` in dependencies.
  - Tests: Python unit and integration, and clients/ts `node --test` in CI's contracts job.
  - Done when every make check passes, the eval check shows no model call (memory.md, Preferences), and the user ships it.
- [ ] 9, PR B2: web, BFF, sign-in, demo, Playwright, CI web job. **B2 starts here**, so a fresh session can pick it up:
  - **Start:** once PR B1 is merged, create branch `step-9-web` from main.
  - **Read first:**
    - this item;
    - the approved plan `C:\Users\kwonhyuk\.claude\plans\pasted-content-id-3f93-add-this-cheerful-spring.md`, sections "PR B2" (B2.1 to B2.6), "Containers" and "What you do by hand";
    - memory.md "From the step 9 plan" and its 2026-10-18 Preferences;
    - `web/node_modules/next/dist/docs/` before any Next code (`web/AGENTS.md`).
  - **Decisions that hold:**
    - `/demo` is public.
    - The demo answers are the exam records n01, c02, c12, x02, x04, x12, o02 and t01 (no model call).
    - The e2e suite runs against `web/e2e/mock-api.ts`.
    - `@playwright/test` and `@axe-core/playwright` are approved.
    - Axe, plus keyboard and phone specs.
    - No model call, and containers only as memory.md allows.
  - **First task:** the web settings (`lib/settings.ts`, `instrumentation.ts`) and the launcher (`web/scripts/run.mjs`), with their `node --test` tests.
  - **Then:**
    1. Session and sign-in, with `hash-password` and `session-secret`.
    2. `proxy.ts` and the BFF routes.
    3. Pages and styles.
    4. `scripts/export_demo.py` and `web/demo/snapshot.json`. Run the mislabel guard, and list each demo citation's company, form, year and item.
    5. Playwright.
    6. The CI `web` job.
    7. Docs.
  - **Done when:**
    - in web, `npm run typecheck`, `npm test`, `npm run build` and `npx playwright test` pass;
    - every make check passes;
    - `git diff --name-only main -- <EVAL_INPUTS>` is empty, so the eval is skipped;
    - the user has reviewed the snapshot and ships it.
- [ ] 10. Deploy: UI on Vercel, backend on the PC via Tailscale Funnel; phone test passes; 401 without API key; demo mode when the PC is off
  - Notes from the step 9 plan (2026-10-18):
    - **The sign-in limiter** lives in each Vercel instance's memory, so it does not hold across instances. The Vercel firewall rate-limit rule on `POST /login` (about 10 a minute per IP) covers that.
    - **The limiter's client key:**
      - **Locally:** no header is read. The server binds 127.0.0.1, every client is on this PC, and one shared bucket applies, so nothing a client sends changes the key.
      - **On Vercel** (`VERCEL=1`, a system variable no request can set): `x-real-ip`. Vercel sets it to the connecting client's public IP, the same value as `x-forwarded-for`. Vercel overwrites any `X-Forwarded-For` a client sends and forwards no external IP, "to prevent IP spoofing". The trusted proxy that would allow a custom value is Enterprise-only (Vercel's request-headers doc, updated 2025-12-13).
    - **FreightAudit's Vercel lessons** (its `docs/deploy.md` and `docs/memory.md`), as a checklist:
      - only main deploys, through `git.deploymentEnabled` `{"**": false, "main": true}` in `web/vercel.json`, not an `ignoreCommand`;
      - Root Directory `web`, with "Include files outside the root directory in the Build Step" on, since web imports `clients/ts`;
      - the function region;
      - Standard Protection, and Git Fork Protection on;
      - a firewall rate-limit rule on `POST /login`;
      - share only the production domain;
      - after a merge, the user confirms the deploy from the merge commit's GitHub status;
      - check that `crypto.argon2` works on Vercel's Node.
    - **Other hardening:**
      - the api refuses requests with a browser `Origin`;
      - `/readyz` answers from a short cache behind Funnel;
      - GraphQL depth limits, and introspection off in production.

## In Progress

- [ ] 9, PR A: GraphQL GET and WebSocket off, Retry-After fixed. It is the step 9 plan's first PR (approved 2026-10-18), on branch `fix/graphql-get-ws-retry-after` from main.
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
  - [ ] (user) Confirm that Actions → Caches lists an `eval-calls-*` entry, then ship with ship.

## Completed

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
