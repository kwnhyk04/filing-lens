# Context

Current state of the project. Document only confirmed information. Update after meaningful technical or functional changes.

Source: design doc "Three AI-Native Portfolio Projects" (2026-10-13).

## Overview and Objectives

AI-native portfolio project showing retrieval-augmented generation with verifiable citations over public SEC filings (capital markets research domain).

## Scope and Requirements

- Ingest filings for selected companies from EDGAR, plus XBRL company facts.
- Hybrid retrieval (pgvector + full-text, reciprocal rank fusion, cross-encoder rerank).
- Router that sends numeric questions to structured facts first.
- Answers with citations that are validated against source text.
- Zero-downtime embedding model swap.
- Must demonstrate: backpressure, retries, pagination, partial failures, schema migrations.

Targets (design goals, not yet measured):

| Metric | Target |
| --- | --- |
| Retrieval recall@10 | 0.90 |
| MRR@10 | 0.70 |
| Numeric exact match (0.5% tolerance) | 0.92 |
| Citation precision | 0.95 |
| Citation coverage | 0.95 |
| Faithfulness | 0.92 |
| Correct refusal | 0.90 |
| False refusal | 5% or lower |
| Retrieval latency at about 250k chunks | p95 250 ms |
| Time to first token | p50 1.0 s, p95 2.0 s |
| Full answer latency | p95 6 s |
| Tokens per query | 8,000 input / 600 output |
| Cost per query | $0.015 |
| Ingestion | 500 filings in under 2 hours |

## Technical Stack

Python 3.12+, uv workspace, ruff, pyright, FastAPI, Strawberry, SQLAlchemy 2 (async), Alembic, Celery, RabbitMQ, Redis, Postgres + pgvector, httpx, structlog, pytest (with pytest-asyncio, respx and hypothesis), Testcontainers, OpenTelemetry, Docker, GitHub Actions. Thin TypeScript UI.

LLM roles from env vars (`provider:model`): `gemini:gemini-3.5-flash-lite` answers, `groq:openai/gpt-oss-20b` routes, `nvidia:openai/gpt-oss-20b` is the fallback. Production puts Claude Haiku 5.5 first, on prepaid credits (`LLM_PRIMARY=anthropic:claude-haiku-5-5`, `LLM_ANSWER_FALLBACK=gemini:gemini-3.5-flash-lite`; user, 2026-10-21).
- **Off for good, stored in Redis:** credits gone, a rejected key or model (alert `ClaudeKeyOrModelRejected`), or from 2026-11-10.
- **Sits out one answer:** a 429, or its day's 1,500,000 tokens used. Each stack counts that day in its own Redis: prod alone, and the dev api with the local `--claude-primary` evals (user, 2026-10-21).
- **Limits:** 1,052 tokens out per call; no prompt that could pass 100,000 tokens. One OpenAI-compatible client (Groq, OpenRouter, NVIDIA NIM, Ollama), a Gemini adapter on google-genai, and a Claude adapter on the `anthropic` SDK (1.15.0, which runs on httpx2). Local models on CPU through sentence-transformers and torch (2.14.1+cpu in the Linux images; 2.12.1 on Windows, pinned below 2.13 there, see memory.md): bge-small (model A) and bge-base (model B) embedders, TinyBERT-L-2 reranker by default. Embeddings: local sentence-transformers model by default; the swap series in `docs/migrations.md` moves chunks from BAAI/bge-small-en-v1.5 (384 dimensions, model A) to BAAI/bge-base-en-v1.5 (768, model B). Dev stays on model A at revision 0008, the last before the swap, until the live swap after step 6. Deployment: UI on Vercel, backend on the PC via Tailscale Funnel.

Pinned versions live in `uv.lock`, `web/package-lock.json`, `clients/ts/package-lock.json`, `infra/docker-compose.yml` (Postgres 18 with pgvector 0.8.7, RabbitMQ 4.3, Redis 8.8) and the `Makefile` (ariadne-codegen 0.19.0; oasdiff v1.32.1, gitleaks v8.30.1, actionlint 1.7.12 and Trivy 0.75.0 by image digest). `infra/Dockerfile` pins its base images by digest, and the workflows pin each action to a commit, each release at least 7 days old when pinned. Web: Next.js 16, React 19, TypeScript 5.9 in strict mode; Playwright 1.64.0 (its Chromium headless shell, revision 1248, in `PLAYWRIGHT_BROWSERS_PATH=H:\.cache\ms-playwright`) and `@axe-core/playwright` 4.13.0 for the e2e suite.

Local ports (bound to 127.0.0.1; chosen so all three projects can run at once; compose project name `filinglens`). Compose publishes exactly these (verified with `docker compose ps` on 2026-10-14) and reads them from `.env`. `web/` takes `WEB_PORT` (default 3100) through its launcher, `web/scripts/run.mjs`. The e2e suite's ports come from `E2E_MOCK_PORT`, `E2E_LIVE_PORT` and `E2E_OFFLINE_PORT`. The fake SEC server lives in the ingest tests on a free port; 4110 stays reserved for a local-run server. The worker's probe port (8001) stays inside its container.

| Service | Host port |
| --- | --- |
| Postgres (pgvector) | 5433 |
| Redis | 6380 |
| RabbitMQ AMQP / management UI | 5672 / 15672 |
| api | 4100 |
| fake SEC server (tests and local runs) | 4110 |
| web (Next.js) | 3100 |
| e2e mock API (`web/e2e/mock-api.ts`, Playwright runs only) | 4101 |
| e2e web servers, live / offline (Playwright runs only) | 3102 / 3103 |
| Grafana | 3101 |
| Jaeger UI | 16687 |
| Prometheus | 9091 |
| OTel Collector (gRPC / HTTP) | 4327 / 4328 |
| Toxiproxy API | 8475 (proxies in 15433-15499) |

## Architecture and System Design

Planned design (step 1 built the skeleton; see Implemented Functionality):

1. `services/api`: FastAPI REST + Strawberry GraphQL. Sheds load with 503 when in-flight LLM calls pass a cap.
2. `services/ingest`: Celery pipeline discover, fetch, parse, chunk, embed, index, plus a facts task for XBRL.
3. Retrieval: hybrid search, fusion, rerank. Returns `degraded: true` if the reranker times out.
4. Answering: router, `get_financial_fact` tool, answer model with mandatory citations, post-validation.
5. `packages/sec_client`, `packages/retrieval`, `packages/llm`, `packages/db`, `packages/telemetry`, `evals/`, `web/`.

## Important Components

Built:
- `packages/core`: settings, the error taxonomy (`TransientError` is the base of the retryable errors), the RabbitMQ queue definitions (`queues.py`) and the Redis token-bucket Lua (`ratelimit.py`).
- `packages/telemetry`: structlog JSON logging with redaction, trace ids on log lines, and query values dropped from uvicorn's access lines; `otel.py` (OpenTelemetry providers over OTLP/HTTP, query names only on spans, our Celery trace propagation) and `metrics.py` (every metric, `SPECS`).
- `packages/sec_client`: `SecClient`, with the shared rate limit, the cool-off, the disk cache, companyfacts and the company ticker list, and a count of the requests it sends.
- `packages/db`: the async engine, the models (with a small pgvector `Vector` type and `chunk_id()`), migrations 0001-0008 and the seed.
- `packages/retrieval`: `search` (scoped vector and full-text candidates, `reciprocal_rank_fusion` with k = 60, rerank with a timeout) and `facts.get_financial_fact` (latest-filed rule).
- `packages/llm`: the provider clients (`providers.py`, Claude's credit rules and `credits_usd` included), the local embedders and rerankers (`local.py`), the router (`router.py`), the reply format and stream filter (`answer.py`), post-validation (`validate.py`: `citation_error`, amounts, per-sentence checks) and the daily AI budget (`budget.py`).
- `services/ingest/src/filinglens_ingest`: the Celery worker with probes (`worker.py`), kombu queues (`topology.py`), the tasks `discover`, `fetch`, `parse`, `chunk`, `embed` and `facts` (`pipeline.py`), HTML to text and item sections (`parsing.py`), token-aware chunks with the vendored bge-small tokenizer (`chunking.py`, `tokenizer-bge-small-en-v1.5.json`), companyfacts rows and fiscal periods (`companyfacts.py`), the dead-letter replay (`replay.py`) and the `reembed` task (`reembed.py`).
- The fake data seed (`scripts/seed_fake.py`), the real one (`scripts/seed_real.py`), the 30 golden-set companies (`evals/golden-companies.csv`), and the compose stack with prod override and Dockerfile (`infra/`).

API (`services/api/src/filinglens_api/`): `main.py` (app, probes, request ids, catch-all 500), `routes.py` (REST v1 and key checks), `limits.py` (rate limits, AI switch and budget, body size, answer time), `schemas.py` (pydantic contract models), `problems.py` (RFC 9457 handlers and response docs), `backend.py` (the `Backend` protocol, keyset cursors, `LiveBackend`), `answering.py` (router, evidence, draft, validation, refusals), `graph.py` (Strawberry schema), `contracts.py` (spec export and `--check`).

Contracts and clients: `contracts/openapi.json` and `contracts/schema.graphql` (generated, committed); `clients/python` (openapi-python-client), `clients/python-graphql` (ariadne-codegen), `clients/ts` (openapi-typescript types, openapi-fetch client, graphql-codegen documents, hand-written `index.ts`); shared GraphQL operations in `clients/operations.graphql` (`Companies`, `Filings`, `Answer`, `Coverage`, `Sources`).

`clients/ts/index.ts` (step 9, PR B1), for server-side TypeScript:
- `createApiClient` (REST) and `executeGraphql` send `X-Request-ID` on every call, generated when the caller gives none.
- A call stops at the caller's abort (`AbortError`) or at its timeout (`TimeoutError`, 30 s by default).
- Base URLs may end in a slash.
- Failures throw `ApiError`, which holds the status, the problem's `code`, the detail as its message, Retry-After in seconds (delta-seconds only) and the request id. A GraphQL error gives its first `extensions.code`, and any reply that is not one of the API's problems gives `unexpected_response`.
- The REST client throws for an error reply too. It does so inside its fetch, because openapi-fetch reads an error body before the caller could.
- Imports end in `.ts`, so Node's type stripping loads it. `npm --prefix clients/ts test` runs `index.test.ts` with `node --test` against a stubbed fetch.
- Since PR B2: a GraphQL reply of 200 whose body is not JSON, is null, or has no data throws `ApiError` (`unexpected_response`, detail `HTTP 200`), not `SyntaxError` or `TypeError`. `Coverage` also selects its filings' `pageInfo { hasNextPage }` (depth 5). Since 2026-10-20, `Sources` also selects a chunk's `filing { periodEnd }`.

Web (`web/`, step 9, PR B2):
- `lib/` holds the logic, tested with `node --test` and no `next/*` import: `settings.ts` (startup check), `password.ts` (argon2id PHC), `session.ts` (HMAC tokens), `guards.ts` (`next=`, the origin rule, the sign-in limiter), `errors.ts` (failure classes), `answer.ts` (SSE parser, quote locator, citation markers, form names), `demo.ts` (the snapshot) and `log.ts`. `server.ts` is the server-only glue (settings, `requireSession`, the API calls), and `startup.ts` runs the check from `instrumentation.ts`.
- `proxy.ts`: a CSP with a fresh nonce on every response, and the sign-in gate.
- Routes: `app/login` (server action), `app/page.tsx` (Ask), `app/coverage`, `app/demo` and `app/demo/coverage`, `app/api/answers`, `app/api/sources`, `app/logout`, plus `not-found.tsx` and `error.tsx`. Components in `components/`.
- `scripts/`: `run.mjs` (launcher), `hash-password.mjs`, `session-secret.mjs`.
- `demo/snapshot.json` comes from `scripts/export_demo.py` (`make demo-export`) and is imported at build time.
- `e2e/`: the Playwright suite, its mock API and its settings. `e2e/screens.ts`, run by `npm run screens` (`playwright.screens.config.ts`, after a build), writes every screen in light, dark and phone width to `docs/screenshots/ui/`, each after an axe check; the e2e run never matches it.
- `app/globals.css` holds the whole visual design (`docs/design.md`). `components/quote-in-view.tsx`, on Ask and the demo, scrolls the sources panel to a citation's highlighted words after its jump.

Tests: the root `conftest.py` (network guard, markers, JSON logs, hypothesis profile, Testcontainers fixtures) and `network_guard.py`; each package and service keeps its tests in its own `tests/`.

CI: `.github/workflows/ci.yml` (pull requests, main, manual runs), `.github/workflows/nightly-eval.yml`, `.github/actions/setup/action.yml` (uv, the workspace, cached models) and `.github/dependabot.yml`.

Evals (`evals/`):
- `golden.py`: golden set v1 build and freeze.
- `label.py`: `make audit` and `make label`; both refuse once the set is frozen.
- `metrics.py`: ranking metrics, exact match, percentiles, Cohen's kappa, bootstrap intervals and the floor rule.
- `calls.py`: the reply cache, call records and 429 handling.
- `judge.py`: the `LLM_JUDGE` prompt, schema and parsing.
- `harness.py`: `make eval`.
- `providers.json`: limits and prices, each with its source and date.
- `corpus.py`: `make corpus-dump` and `make corpus-restore`, golden v1's corpus for CI.
- `eval-card.md`.
- `golden/v1/`: frozen, with a sha256 manifest.
- `reports/`.

## Implemented Functionality

- Config: each process validates its env vars at startup and exits naming each bad one without echoing values, for example `Invalid configuration: API_KEY: Field required`. Compose also refuses to start without the required `.env` values.
- Public-URL hardening (step 10, PR 10a, 2026-10-21):
  - **Browsers refused:** a request with an `Origin` header, `null` included, gets 403 `forbidden` on every route. It is an app-wide dependency (`routes.refuse_browsers`), so it runs before the key check and the rate limit; a navigation without Origin still gets 401.
  - **No docs routes:** `/docs`, `/redoc` and `/openapi.json` are off. `contracts.py` still exports the spec in process.
  - **`/readyz` cache:** one round of checks at most every 5 s (`READY_TTL_S`), stamped when the round ends. Calls that arrive during a round wait for its result.
  - **GraphQL:** introspection is off (`DisableIntrospection`).
    - A value that does not fit its type (a variable, a literal, or an argument coerced at execution) answers "Invalid value for an argument or variable." with `invalid_input`, never the value.
    - `graph.Schema.process_errors` logs `graphql_error` with code and path only: `internal` at error with its traceback, the rest at warning.
    - `fiscalYear` takes 1993-2100, as on REST.
  - **NUL:** a NUL is refused in `q` (422), `question` (422, or `invalid_input` on GraphQL), `concept` (`invalid_input`) and every cursor key (400), through `schemas.NoNul`. Cursor CIKs are bounded (`Cik`).
  - **SQL errors:** `make_engine` sets `hide_parameters`, so SQLAlchemy's errors leave the statement's parameters out.
- API keys: `API_KEY` opens every route except the admin routes; `ADMIN_API_KEY` opens every route and is the only key for `POST /v1/ingest-jobs` and `GET /v1/ingest-jobs/{id}`. Both are required, at least 32 characters, must differ, and are read only from the `X-API-Key` header (a key in the URL gets 401). Missing or unknown key: 401 with `WWW-Authenticate: APIKey`; `API_KEY` on an admin route: 403. `/healthz` and `/readyz` need no key. Every response carries `X-Request-ID`.
- REST v1: `POST /v1/ingest-jobs` (202, `Location`, required `Idempotency-Key`), `GET /v1/ingest-jobs/{id}` (status counts plus a page of failures), `GET /v1/companies`, `GET /v1/filings`, `GET /v1/search` (cursor holds score, chunk id and index version), `POST /v1/answers` and `POST /v1/answers/stream` (Server-Sent Events: `delta`, then `completed`, or `failed` mid-stream). Lists use keyset pagination: `limit` at most 100, opaque `cursor`, `next_cursor`.
- Errors: RFC 9457 problems (`application/problem+json`, `type: about:blank`, `code` from the taxonomy). Validation is 422 `validation_failed` with `errors[{detail, pointer}]`; a bad cursor is 400; 429 sends `Retry-After`, `RateLimit-Limit` and `RateLimit-Remaining`.

A 503 sends `Retry-After` only when waiting helps:
- `overloaded`: answers in progress (2 s), a busy reranker on a later page (1 s), or a broker that refused a job (5 s);
- `ai_unavailable`: a used-up daily budget (until 00:00 UTC), a budget that cannot be checked (30 s), or rate-limited providers (theirs, or 60 s).

Without it, waiting does not help: AI is switched off, or the last model refused the key, has no credits or was retired. `test_a_503_carries_retry_after_only_when_waiting_helps` pins each case. These rules were fixed on 2026-10-18; before, the description claimed every 503 carried Retry-After. Unexpected errors are 500 with no detail, logged with the request id.
- Data behind the routes: `LiveBackend` serves companies, filings, sections, chunks and facts from Postgres. It also creates and reports ingest jobs: creation is idempotent per Idempotency-Key, stores the job and one `ingest_job_companies` row per CIK, then queues one discover per company with publisher confirms (503 if RabbitMQ refuses). A retry queues again while the job is still `queued`. The job view counts items by status and pages failures by accession number. Search and answers are live (see Search and answers below).
- Request limits:
  - Per API key, a Redis token bucket of 60 a minute on every route (GraphQL included), and 10 a minute shared by every answer: `/v1/answers`, its stream and GraphQL `answer`. 429 carries `Retry-After` and `RateLimit-*`; GraphQL refuses an answer with an error whose `extensions.code` is `rate_limited`. The limiter fails open while Redis is down.
  - Answers return 503 `ai_unavailable` (GraphQL: an `ai_unavailable` error) when `AI_ENABLED=false` or once the UTC day's LLM tokens (`filinglens_llm.budget`, Redis hash `ai:usage:<date>`) reach `DAILY_AI_TOKEN_BUDGET`. That check fails closed. Every model call adds its tokens (`budget.record`).
  - Bodies over 64 KB get 413 (`request_entity_too_large`), chunked ones included. An answer, streamed or not, REST or GraphQL, gets 30 s, then 502 (a `failed` event in a stream, an `upstream_error` error over GraphQL).
  - GraphQL `answer` runs the same guard code as REST: `answer_limits`, which `answer_limits_for` binds to the request so it applies to `answer` only, and `timed_answer`. Fixed on 2026-10-18; before that, GraphQL answers skipped the answer bucket, the budget and the time limit.
  - In-flight cap:
    - An answer counts against `LLM_MAX_INFLIGHT` from its admission (`Answerer.admit`), not from its first event, so streams opened together cannot pass the cap.
    - Its `Admitted` events give the slot back at the last event, on an error or a cancellation, or on `aclose()`. The stream route's request-scoped dependency calls `aclose()` after the response, so a client gone before the first event frees it too.
    - Evals and scripts call `Answerer.events` directly, one answer at a time, and are not counted.
  - Entry points that reach a model, and their guards (audited 2026-10-18):

    | Entry point | Key | 60/min | 10/min answers | Budget and AI switch | In-flight cap | 30 s | 64 KB body |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | `POST /v1/answers` | API or admin | yes | yes | yes | yes | yes | yes |
    | `POST /v1/answers/stream` | API or admin | yes | yes | yes | yes | yes (deadline) | yes |
    | GraphQL `answer` | API or admin | yes | yes (the same bucket) | yes | yes | yes | yes |
    | `GET /v1/search` (local embedder and reranker, no LLM) | API or admin | yes | n/a | n/a | n/a | n/a | n/a |
    | `POST /v1/ingest-jobs` (workers, local embedder, no LLM) | admin | yes | n/a | n/a | n/a | n/a | yes |

    The catalog routes, the GraphQL catalog fields and the probes reach no model. The operator tools run outside the API with no API guards by design:
    - `make eval`: one pinned answer model, no fallback, tokens counted in Redis db 15, 30 s per question.
    - `make calibrate`: judge calls only.
    - `make smoke` and `make record-fixtures`: the Answerer directly, with per-call HTTP timeouts only.
- Ingest pipeline:
  - The API's job queues `discover`. It walks one page of the company's submissions JSON per run, from the main file through the older files, and skips files whose newest filing predates the job's `since`.
  - Discover upserts the company (if new) and the 10-K and 10-Q filings, and adds job items: `skipped` when already parsed, otherwise `pending`. It then queues a `fetch` per pending filing, with confirms, and marks it `running`. When RabbitMQ nacks because `fetch` holds 10,000 messages, discover queues itself again after a jittered backoff of up to 60 s. After its last page it queues `facts` for the company.
  - `fetch` downloads the primary document into the SEC cache and marks the filing `fetched`, then queues `parse`; a filing already at or past `fetched` goes straight to `parse`.
  - `parse` reads the document from the SEC cache, turns the HTML into text (one line per block; a table row becomes one line with cells joined by " | "; hidden inline XBRL dropped) and splits it into item sections by heading, skipping the table of contents (10-K items 1-16, 10-Q items keyed by part, such as `II-1A`). Sections keep their text and char range; required items it cannot find go to `filings.missing_items`. A filing with no required item fails with the reason. It then queues `chunk`.
  - `chunk` cuts each section into chunks of at most 384 bge-small tokens with 64 overlapping (ids `chunk_id(accession, item, offset)`, token counts stored, no vectors), marks the filing `parsed` and settles its job item.
  - `facts` loads the company's whole companyfacts into `financial_facts` (as published; entries without fiscal year, or with a period outside FY and Q1-Q4, skipped) and sets each of its filings' fiscal year and period from its companyfacts entries, else from `period_end` and the fiscal year end (`fiscal_source`). It then settles the company. SEC answering 404 means no facts.
  - Parse, chunk and facts use unbounded queues with dead-letter queues `parse.dlq`, `chunk.dlq` and `facts.dlq`, and the same retry, pause and dead-letter rules as fetch. It retries `TransientError` six times with exponential backoff (at most 300 s, jittered) through `fetch.retry`. Without Redis, fetch and discover pause instead: each sends itself again after about 30 s (jittered) with its retry count unchanged, so an outage dead-letters nothing. `attempts` counts the tries that ran; neither a pause nor a try killed mid-request counts.
  - A final failure (or any unexpected error) writes a `dead_letters` row and marks the filing and item `failed`. The task then rejects without requeue, so RabbitMQ moves the message to `fetch.dlq` (or `discover.dlq`) through the `filinglens.dlx` exchange.
  - A job item succeeds once its filing is chunked, a job company once its facts are loaded. The job ends `succeeded`, `partially_failed` (the prompt's `completed_with_errors`) or `failed` once every company and filing is settled, under a lock on the job row. `python -m filinglens_ingest.replay --queue fetch.dlq --limit 100` moves dead letters back with fresh retries.
- SEC client:
  - One Redis token bucket at 8 req/s (capacity 1) for every process.
  - A 403 or 429 sets a cool-off key (Retry-After or 60 s, at most 120 s) that pauses every process. A 403 again after that cool-off is a refusal: the client stores the reason in `sec:refused`, and every later call fails at once with `SecRefusedError`, without a request, until a worker restarts (`worker_ready` clears it). A success in between clears the strike, so a later 403 is a throttle again; a 429 is always a throttle.
  - Fails closed: without Redis no request goes out (`LimiterUnavailableError`).
  - `User-Agent` from `SEC_USER_AGENT`; timeouts of 5 s to connect and 30 s to read.
  - Gzipped responses cached under their URL path in `SEC_CACHE_DIR` (the repo's `.cache/sec`, shared by the worker and host runs): documents for good, JSON (submissions, companyfacts, company tickers) for an hour. Every request sent is counted by kind in the Redis hash `sec:requests`. The contract tests swap in an in-memory backend. Filings list only status `indexed`, newest first by (`filed_on`, accession number); chunks page in reading order (`char_start`, id), and an unknown chunk id in a cursor is 400; facts page by id, and their `concept` reads `us-gaap:Revenues`.
- GraphQL `/graphql` (either key) takes POST only: GET gets 405 before the key check, and there is no WebSocket route (2026-10-18). It has `Company`, `Filing`, `Section`, `Chunk`, `FinancialFact`, `Answer`, `Citation`, `Usage`; Relay connections (`edges`, `pageInfo`) for companies, filings, chunks and facts. `chunks(ids)` and `facts(ids)` look up an answer's citations by id (PR B1): 0 to 20 ids per call, of 1 to 64 characters with no NUL, otherwise `invalid_input`. An answer can cite more than 20 facts, so a caller sends longer lists in batches. Results come in the order given, each once; unknown ids and chunks of filings that are not indexed are left out. The links `Chunk.section`, `Chunk.filing`, `Filing.company` and `FinancialFact.company` come pre-joined from those lookups. On other paths they load through two per-request DataLoaders, `chunk_sources` (`get_chunks`) and `companies` (`get_companies`), so the links on one page make one lookup, each id once. A row that is gone gets its own `not_found` error, at its link's path (PR 10b). A query is refused before any resolver runs when it nests deeper than 6 levels or uses an alias (Strawberry's `QueryDepthLimiter` and `MaxAliasesLimiter`, validation rules with no `extensions.code`). Coverage and Filings, the deepest operations in `clients/operations.graphql`, sit at depth 6. A connection inside another list (a list index on its path) takes `first` 1 to 20, the default page size, and the outermost list 1 to 100; past that, `invalid_input` before its page is read (`graph._page_size`, step 10c, 2026-10-24). The web asks for 5 inside a list. Resolver errors carry `extensions.code`; unexpected ones are masked.
- Worker: Celery app (late acks, reject on worker lost, prefetch 1, time limits, publisher confirms). It consumes `discover`, `fetch`, `fetch.retry` and `reembed`, and, when ready, declares the dead-letter queues and clears a recorded SEC refusal. `/healthz` and `/readyz` listen on 127.0.0.1:8001 inside the container; readiness pings the worker through RabbitMQ.
- Data: tables `companies` (CIK key, ticker, name, sector), `filings` (accession number unique, `filing_status` enum discovered, fetched, parsed (sections and chunks stored), embedded, indexed, failed; fiscal year, period and `fiscal_source`; `missing_items`), `sections` (item, title, char range, text), `chunks` (id = sha256 of accession, item and offset; generated English `tsv`; `embedding_v2` vector(768) and its model), `financial_facts` (numeric value as published, form, `filed_on`; unique per CIK, taxonomy, concept, unit, period and filing), `ingest_jobs`, `ingest_job_companies` (discovery status per CIK), `ingest_job_items`, `dead_letters` (one per task id), `eval_runs`. Indexes: HNSW (cosine) on the embedding column, GIN on `tsv`, `(created_at, id)` keyset indexes on the ingest, dead-letter and eval tables. An idempotent seed of 6 companies.
- Migrations: `make migrate` upgrades to head, `make migrate REV=0008` stops at a revision (the dev path). The chain runs 0001-0003, 0007, 0008, then the swap 0004-0006, which stays last until the live swap. Every revision runs in its own transaction with `lock_timeout` 5 s (set in `env.py`); indexes are built with `CREATE INDEX CONCURRENTLY` in autocommit blocks. 0004-0006 are the embedding swap (expand, HNSW index, contract), and `docs/migrations.md` is its runbook and the dev path. 0006 refuses to run while any chunk lacks `embedding_v2`.
- Embedding swap: `reembed` (Celery) fills `embedding_v2` in batches of 256 by keyset over chunk id, queues its own next batch, is rate limited to 60 batches a minute, and resumes after a crash. `RETRIEVAL_EMBEDDING_COLUMN` (api setting; code and compose default `embedding_v2`, `.env.example` `embedding` for the dev path) names the column `nearest_chunks` searches. The ORM defers the `embedding_v2` columns, so loading chunks works at 0003.
- Real data: `make seed-real` (live SEC, worker running) checks each CIK and ticker in `evals/golden-companies.csv` against SEC's `company_tickers.json` and stops on any mismatch. It then queues one ingest job per company for its latest original 10-K through `LiveBackend`, waits, and prints filings per status, chunks per filing, facts per company, the SEC requests of the run and its wall time. Measured on 2026-10-15, with the dev stack on this PC:
  - First run: 30 jobs succeeded and all 30 filings were parsed, with no required item missing. Chunks per 10-K: min 158 (Apple), median 314, mean 375, max 938 (JPMorgan Chase); 11,263 in all. Facts: 856,438 rows (14,276 for Linde to 50,029 for JPMorgan Chase). Fiscal year and period came from companyfacts for all 30. The run made 91 SEC requests (30 documents, 30 submissions, 30 companyfacts, 1 ticker list) in 32 s.
  - A second run made no SEC request, downloaded no document, and inserted nothing (6 s).
  - Full-text search for "supply chain risk" in Apple's chunks matched 5 chunks, all in Item 1A. Table sizes after the run: `financial_facts` 373 MB with its indexes, `chunks` 41 MB, `sections` 6.6 MB.
  - Corpus estimate, from the mean of 375 chunks per 10-K: about 190k chunks for one 10-K from each S&P 500 company (the earlier unmeasured guess was 200k to 300k). 10-Qs would add more; they are not measured yet.
- Fake data: `make seed-fake` loads 200 companies (CIKs from 9,000,000,000), 2,000 indexed filings, 10,000 sections, 100k chunks and 6,000 facts. Every embedding column the schema has gets random unit vectors. Each company has its own fixed seed, and a rerun skips companies already loaded. Rows go in with psycopg COPY, and the HNSW indexes are dropped and rebuilt once, all in one transaction that locks `chunks`.
- Embedding: chunk queues `embed` on the `embed` service (one process, `-Q embed,reembed -c 1`), which fills `RETRIEVAL_EMBEDDING_COLUMN` and its `_model` column, 512 chunks a run, then marks the filing indexed (fiscal year known) or embedded; facts indexes embedded filings. The 30 golden-set filings are indexed: 11,263 chunks in about 14 min, 13.0 chunks/s on this CPU (2026-10-15). Models load offline from `HF_HOME` (`make models` fetches the pinned commits; containers mount it read-only).
- Search and answers:
  - `GET /v1/search` (optional `cik`, `fiscal_year`): vector top 50 and full-text top 50 (words OR-ed) within indexed filings, RRF (k = 60), the fused top `RERANK_CANDIDATES` reranked (`RERANK_MODEL`, `RERANK_MAX_TOKENS`); past `RERANK_TIMEOUT_MS` the fused order with `degraded: true`. Keyset over (score, chunk id); a cursor from another embedding column gets 409. Warm in the API container: embed 15-25 ms, SQL 5-110 ms, rerank 128-182 ms.
  - Answers (`filinglens_api.answering`): the router picks numeric, textual, comparison or out_of_scope with tickers, years, period and metric; numeric questions read XBRL facts (`get_financial_fact`, latest-filed rule), others search. The search starts while the router runs, on the companies and years the question names (`router.guess`), and is kept only when the router's plan asks for the same scope; otherwise it is cancelled at once, and a rerank it still has queued skips the model (2026-10-21). The primary writes cited text with quotes, streamed as `delta` events; validation checks every sentence's citations and amounts, regenerates once, then drops failing sentences with a warning. A sentence that holds a bracketed marker with a digit that is no source id, such as `[12]` for C12, fails ("[12] is not one of the sources"); a bracket without a digit, such as `[sic]`, does not (2026-10-18, merged as #7). Refusals: out of scope, untracked company, fiscal year without a 10-K yet, best rerank score under -3.0. A failed router call falls back to `LLM_FALLBACK`. A failed answer call tries `LLM_ANSWER_FALLBACK` first when it is set and on, then `LLM_FALLBACK`. Each fallback is counted in `ai:usage:<date>` field `fallbacks`; a 402 or a failed last model gives 503. Claude (production's `LLM_PRIMARY` since 2026-10-21) is off for good in every process (Redis `ai:claude:off`) once a 402, or a 400 naming a spend limit or the credit balance, shows its credits are gone, after a 401, 403 or 404 (alert `ClaudeKeyOrModelRejected`), and from `ANTHROPIC_CREDITS_EXPIRE` (UTC). A 429 hands on that answer only, after one retry when it asks for 10 s or less. `usage.cost_usd` is the credits an answer spent, $0 on the free tiers.
  - Answer length:
    - Every answer call (the streamed draft and the one regeneration) gets `max_tokens` 1,024. It is set as `MAX_TOKENS` in `packages/llm/src/filinglens_llm/answer.py` and passed by `filinglens_api.answering`.
    - Why:
      - Latency: output tokens set most of an answer's time.
      - Cost: output is the dearest token, $0.50 per 1M on Haiku and $2.50 on Gemini's paid tier.
      - Focus: a cited answer of a few sentences plus its Sources block fits. On golden v1 Gemini used 161 output tokens per query, router included, and Claude's longest reply with thinking off was 956.
      - Runaway protection: a model that loops or rambles stops at a known size, inside the 30 s answer limit.
    - Reasoning tokens count toward the limit, so every answer model runs its lowest reasoning setting: Gemini minimal thinking, gpt-oss reasoning effort low, Claude thinking off. With adaptive thinking, Claude used up the limit on 4 dev answers.
    - Evals raise it to 4,096 only for Gemini's `--thinking=default`. Past `LLM_MAX_INFLIGHT` answers in progress: 503 `overloaded`. `Answer` carries `refused` and `warnings`.
- Evals:
  - Golden set v1 (`evals/golden/v1`, frozen 2026-10-16, card `evals/eval-card.md`) holds 100 questions: 40 numeric, 20 textual, 15 comparison, 15 unanswerable and 10 time traps, split 70 dev and 30 test, with a 20-question ci subset.
    - Numeric and comparison gold are XBRL facts.
    - Passage gold is AI-labeled, spot-checked by a non-expert; it is not human-verified.
  - `make eval SUITE=retrieval|answer|all SPLIT=dev|test SUBSET=full|ci ARGS=...` runs the harness:
    - Before each run it checks the manifest and the corpus: the latest fiscal years, the gold chunk texts and the fact values. Any change exits 3.
    - The retrieval suite times every question as a query, with a 60 s rerank cap, and scores the textual ones on recall, MRR, nDCG and judged@10.
    - The answer suite runs the Answerer as the API does (no fallback, `today` pinned to the set's as_of, 30 s per question). Its searches wait up to 60 s for the reranker, as the retrieval suite's do (`harness.eval_settings`, 2026-10-21). So a reply's prompt never depends on the runner's speed. Each model reply is cached by call key, progress goes to a run file, and tokens are counted in Redis db 15.
    - A 429 waits when Retry-After is 120 s or less. The third in a row, or a longer wait, exits 2, and a rerun resumes. Exit 2 is only for a quota or rate limit; a refused key, credits gone or a retired model exit 4.
    - Intervals: pass/fail per question (numeric and comparison match, correct and false refusal, router and route accuracy) uses a Wilson score interval, and everything else a percentile bootstrap. `--set-floors REPORT --replace` replaces a report's floors even when looser; it runs only on request, with the reason in memory.md.
    - The ci subset is golden v1's ci flag plus `harness.CI_EXTRA` (a04, a07, a09, t04, t08): 25 dev questions, 10 of them should-refuse. Golden v1 itself is unchanged.
    - `--ci` (CI runs): it stops with exit 4 before any call when the setup has no floors. It reports latency marked "not gated" and checks no latency floor. Any errored question, judge errors included, exits 4 with its reason. It writes a verdict (PASS, FAILED, or INCOMPLETE for a quota or rate limit only) with the report to `.cache/evals/ci/<suite>-<split>-<subset>.md`, and a GitHub error annotation unless the run passed. A setup error such as a missing key also exits 4 with its reason.
    - The judge scores every answer that was not refused. A sentence that cites a number with no source never reaches it: `judge.user_prompt` raises JudgeError first, and the question errors (2026-10-18, merged as #7). Calibrated on 2026-10-16: Cohen's kappa 0.84 (95% CI 0.59 to 1.00) against Claude's labels on 29 sentences, so citation precision and faithfulness count. With the one unparsed reply counted as a disagreement, kappa is 0.77 (0.47 to 1.00). Every negative in that sample was constructed, so its detection of natural unsupported sentences is untested. The follow-up spot check (2026-10-17) took 6 natural sentences that fail the validator, from decision 4's NVIDIA runs (`evals/calibration/v1-followup/`). The judge failed 3 of the 4 that Claude labeled not supported (`evals/eval-card.md`).
    - Reports go to `evals/reports/runs/`: JSON with per-question records, plus a markdown table of target, measured value, 95% bootstrap CI, n and status. Each run also adds an `eval_runs` row and prints the deltas against the previous report.
    - Floors live in `evals/thresholds.json`, and a broken floor exits 1. Runs never write them: `python -m evals.harness --set-floors REPORT` applies the floor rule to a saved report's measured values (quality, tokens, cost and latency, TTFT included) and keeps only tighter floors. Answer floors are keyed per primary model, so the free setup's $0 billed floor never meets Claude. They were written on 2026-10-17 from Gemini's test report. The dev floors that CI gates (`retrieval:dev:full`, `answer:dev:ci:gemini:gemini-3.5-flash-lite`) followed the same day, from the dev reports. Retrieval accuracy floors are the measured value less one question's share, capped at the target, because retrieval calls no model and repeats exactly (`metrics.deterministic_floor`). Pass/fail metrics take Wilson intervals. On 2026-10-17 every floor key was recomputed from its own saved report under these rules (user decision). The dev ci floors came from a fresh run of the widened subset, and the test floors from the exam report. CI floors are a tripwire for large drops: the numeric floor of 0.676 still lets 6 of 8 pass.
    - Cost as billed is the prepaid credits each call spent, from its usage (`credits_usd`), and $0 on the free tiers. Evals pin one answer model with no fallback, and credits gone exit 4. `LLM_JUDGE` can never be Claude. The official run refuses a Claude `LLM_PRIMARY`. `--claude-primary` is a labelled local run: Claude answers on the official free run's router replies, those of the default `LLM_PRIMARY` whatever `.env` sets, and its report sits beside that run's. It never checks or sets floors, and CI refuses it (2026-10-21).
    - `--compare A B` prints paired per-question differences, including the primary call's own first-token and total times.
    - `--tag=NAME` calls the answer models live once under their own cache keys, so earlier reports still read their replies. `--primary-tag=NAME` does that for the primary only, with router replies from the cache.
    - `--router-primary=PROVIDER:MODEL` keys router calls as that primary's run did. Another answer model then gets identical routes (the Haiku comparison on test), and its end-to-end latency is not measured.
    - Each report records the code it measured (the commit, whether the source files differ from it, and a sha256 of them as they stand; data and docs left out) and the sha256 of each system prompt and schema.
- Logs: structlog JSON lines on stdout from the API, the worker, migrations and the seed, including uvicorn, Celery and Alembic records. Each line carries `service`, `level` (threshold from `LOG_LEVEL`) and, during a request, `request_id`. Credential-named fields and the API key value are redacted. A line written inside a span carries `trace_id` and `span_id`. Uvicorn's access lines keep query parameter names only (`GET /v1/search?q&cursor`).
- Monitoring (step 8, built 2026-10-18; `docs/monitoring.md`):
  - `OTEL_EXPORTER_OTLP_ENDPOINT` (empty means off) makes api, ingest and embed export traces and metrics over OTLP/HTTP to the collector in the `observability` profile. Compose gives the containers the collector's URL whenever `.env` sets it.
  - Traces: one per request (FastAPI's own telemetry, probes left out, `request_id` on the span, `url.query` names only), with answer stage spans, model call spans (`gen_ai.*`), search phase spans, and one trace per ingest job from `POST /v1/ingest-jobs` through every task (our own Celery propagation), SEC calls included.
  - Metrics: the registry in `metrics.py`; answers by outcome and refusal code, rejections, TTFT and stage times, model calls and tokens, search phases and rerank time-outs, ingest task outcomes, embed chunks, SEC requests, cool-offs and refusals; RabbitMQ's queue depth and consumers; the collector's probe of `/readyz`.
  - Three provisioned Grafana dashboards (service health, answers and LLM, ingest pipeline) and 13 Prometheus alert rules with promtool tests (`make monitoring-check`, in CI's lint job). No alert delivery until step 10.
- Compose: `infra/docker-compose.yml` for development. Postgres runs with `shm_size: 256mb`, so parallel HNSW builds fit in `/dev/shm`; `make check-parallel-hnsw` checks it on the dev stack. The worker gets `SEC_USER_AGENT` (compose refuses to start without it) and the repo's `.cache/sec` folder as its SEC cache (a bind mount), and the API gets `AI_ENABLED`, `DAILY_AI_TOKEN_BUDGET` and, since 10c (2026-10-24), `CLAUDE_DAILY_TOKEN_BUDGET`, which compose had never passed, so a value in `.env` had no effect.
- Production stack (step 10c, built 2026-10-24, uncommitted; `docs/deploy.md`): `infra/docker-compose.prod.yml` on top of the dev file, run as `docker compose --env-file .env.prod <command>`.
  - Its own project `filinglens-prod`. api, ingest and embed run CI's GHCR images by `IMAGE_TAG` (`sha-<7>`), with no build section; compose stops without `IMAGE_TAG` or `RETRIEVAL_EMBEDDING_COLUMN`.
  - No host port. Postgres, Redis and RabbitMQ sit on the internal `data` network only; the api joins `data` and `default`, the workers sit behind the `ingest` profile.
  - A `tailscale` sidecar (`tag:filinglens`, the image FreightAudit pins, state in the external volume `filinglens-prod-tailscale-state`) serves Funnel on 443 to `http://api:4100` (`infra/tailscale/serve.json`).
  - The api and the tailscale container run read-only with a `/tmp` tmpfs, no capabilities and `no-new-privileges`. Every service restarts unless stopped and keeps 3 log files of 10 MB.
  - Models and keys come from `.env.prod`, nothing forced: Claude Haiku first, its key there only.
  - Web on Vercel: `web/vercel.json` deploys `main` only, in `hkg1`; `engines.node` is `^24.7.0`.
- Contracts: `make codegen` exports both contracts and regenerates all four clients, then type-checks the TS client. `make contracts-check` runs codegen and fails if git sees unstaged or untracked changes under `contracts/` or `clients/`. `make contracts-breaking` runs oasdiff (Docker) against `BASE` (default `main`) and fails on breaking changes.
- Web (PR B2 merged as #10, B3 as 9b829a6, the design round as #15 and the mockup style as #16 and the first mockup features as #17; the source cards' fiscal year end as #18):
  - **Settings:** `API_URL`, `API_KEY` (32+ characters), `SESSION_SECRET` (32+) and `LOGIN_PASSWORD_HASH` (argon2id PHC: m 19 MiB to 1 GiB, t 2 to 10, p 1 to 16, a salt of 8+ bytes, a hash of 16 to 64), checked when the server starts. A bad value stops it with one JSON line that names each variable, never a value. No `NEXT_PUBLIC_` variable exists. `npm run dev` and `npm start` run `scripts/run.mjs`, which adds the web's keys from the repo's `.env` (`node:util` `parseEnv`, literal values) where the environment lacks them, and drops `ADMIN_API_KEY`.
  - **Sign-in:** a password form as a server action. The limiter allows 5 attempts per 15 minutes, counted as each starts and before argon2 (a success resets it), so parallel attempts cannot all pass; locally all clients share one bucket, and on Vercel (`VERCEL=1`) the key is `x-real-ip`. The button stays focusable while pending, and each failure renders a new message node, so a repeated error is announced. Node 24.7+ is needed (`crypto.argon2`; `engines` in `web/package.json`). A success sets `__Host-filinglens_session`: `v1.<expiry>.<HMAC-SHA256>`, HttpOnly, Secure, SameSite=Lax, Path=/, 8 hours. `next=` keeps only a path on the web's own origin.
  - **Gate:** `proxy.ts` sends signed-out pages to `/login?next=...` and `/api/**` a JSON 401; `/login`, `/logout`, `/demo/**`, `/healthz` and `/readyz` are public. Every live page and BFF route checks the session again. A missing `SESSION_SECRET`, or one shorter than the startup check's 32 characters, signs no one in.
  - **BFF:** `POST /api/answers` pipes the API's answer stream unchanged (35 s timeout, `maxDuration` 45) and turns admission errors into `{code, detail, retryAfter, requestId}`. `POST /api/sources` runs GraphQL `Sources` in batches of 20 ids per kind (at most 200 per kind). `POST /logout` answers 303 to `/login` with an expired cookie and `Clear-Site-Data: "cache"`. All three need `Sec-Fetch-Site: same-origin` or an `Origin` whose host equals `Host`; BFF replies send `no-store`. Each API call sends a fresh `X-Request-ID` and logs one JSON line (`ts, level, service, event, route, status, ms, request_id`), with no question, key or cookie. A failed call logs its failure class at warn, except one the browser gave up on (`AbortError`, or Next's `ResponseAborted` when it disconnects): `client_aborted` at info (B3).
  - **Failures:** a network error, a timeout, a reply that is not an API problem (such as a proxy's 502 page) or `internal` (a 500, or a GraphQL error on a 200) counts as offline: a live page goes to its demo twin (`/demo?offline=1`, `/demo/coverage?offline=1`) with a banner. A 401 or 403 shows a configuration-error page with the request id and logs `api_key_rejected`, never the demo. A cursor the API refuses goes to the first page.
  - **Pages:** Ask streams a draft marked "citations not checked yet". On `completed`, the checked answer replaces it, with warnings, the refusal, a degraded note, tokens and cost. Leaving Ask, or a new question, aborts the running stream and sources lookup, and the abort reaches the API's stream. A failed sources lookup keeps the answer and says "Sources could not be loaded." under Sources and in the status line; "The web server could not be reached." is only for the stream (B3). Each `[n]` links to a card: a chunk card (company, form, fiscal year, its filing's period end such as "Fiscal year ended December 31, 2025", item and title, the passage with the quote marked) or a fact card (label, value and unit as published, period, accession, company). The answer's header shows what the browser timed from the question's send (first words, complete, the source count). Under the answer, "Copy answer with sources" (when it cites any) copies the text with its markers, then each source's name, quote and link; "New question" stops a sources lookup still running, clears the answer and the question box and puts the focus there (2026-10-20). Coverage pages companies 20 at a time, each filing with an "Indexed" pill, since the API lists indexed filings only. `/demo` shows the 8 saved answers with their cards, and `/demo/coverage` the saved coverage. The demo header shows the snapshot's coverage ("30 companies · 30 filings") and offers Sign in, or Sign out to a signed-in visitor (while the API is offline, the demo is the only page).
  - **Headers:** the CSP (nonce, `'strict-dynamic'`, `connect-src 'self'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, nosniff, `Referrer-Policy: no-referrer`, a Permissions-Policy, no `X-Powered-By`.
  - **Accessibility:** landmarks, a skip link, a title per page, labelled native controls, a polite status line, a draft outside any live region with `aria-busy`, citation links named like "Source 1: AMZN 10-K FY2025, Item 1", light and dark tokens, no sideways scroll at 390 px.
  - **Design** (`docs/design.md`, the mockup style): the separately made mockup's look, chosen by the user over the design round's paper and ink (kept in design.md as a dated section). White cards on a pale green-grey page, one green accent, the system sans for the interface, serif for the answer and the passages, mono for identifiers, system fonts only. Figures in the answer and the cited words sit under a yellow highlighter (the cited words also underlined); citations are small numbered boxes. From 64rem Ask's sources panel sits beside the whole column, half the width, with its own scroll; it sticks where it starts and ends 16 px above the window's bottom, so it fits from the first screen. A citation's jump brings its highlighted words into view in the panel. Coverage takes the mockup's Filings table look and the demo its landing look. Light and dark tokens in `app/globals.css`; every text pair in use reaches 5.01:1 or more.
  - **Demo snapshot** (`make demo-export`, 2026-10-19; exported again on 2026-10-20 for the chunks' `periodEnd`, which changed nothing else but `commit` and `recorded_at`; 46.1 KB): 8 answers recorded in golden v1's test run (n01, c02, c12, x02, x04, x12, o02, t01; 0 model calls), 30 companies, every citation resolved through the API's GraphQL in process, none inside the four mislabeled sections. 44.8 KB, LF on every platform (`write_snapshot` writes `\n`, and `.gitattributes` keeps `web/demo/**` LF).
  - **Tests:** `npm test` in web (84 `node --test` units) and `npx playwright test` (72 specs) after `npm run build`: sign-in, the gate, Ask (numeric, textual, comparison, refusal, warnings, errors, a failed sources lookup, leaving mid-answer, where the mock notes a stream the web cut, the sources panel fitting the window from the first screen, with a citation's quote brought into view, the timings, copying, New question, also while the sources still load), coverage and its pills, offline twins and the demo header's line, a rejected key and `error.tsx`, headers, the API key absent from every response, axe on every page (light and dark), keyboard and phone, then the lockout. They run against `e2e/mock-api.ts`, which replays the snapshot.
- Secrets: gitleaks pre-commit hook and a CI scan of the full history, allowlist `.dockerignore`, images run as uid 10001 with a `HEALTHCHECK` on `/healthz` (the api on `API_PORT`, a worker's probe on `HEALTH_PORT`).
- CI (step 7, built 2026-10-17 and merged as pull request #1 on 2026-10-18; it runs on GitHub, see Known Limitations):
  - `ci.yml` jobs:
    - changes;
    - lint: ruff, pyright, actionlint, and guards against `secrets.ANTHROPIC`, an Anthropic model and steps that cannot fail;
    - unit and integration;
    - contracts: `make contracts-check`, and `make contracts-breaking` against the pull request's base or the commit before a push;
    - web (PR B2): `npm ci` in web (its postinstall installs `clients/ts`'s runtime dependencies), typecheck, `node --test`, `next build`, Playwright's Chromium cached by version, then `playwright test`, with the report and traces as an artifact on failure. No secrets. It joins `publish` and `ci-ok`;
    - security: gitleaks over every commit, Trivy on each lockfile with dev dependencies, failing on a high or critical with a fix;
    - migrations: on the restored corpus at the deployed revision, upgrade to the last revision before 0004, down one step, up again;
    - eval;
    - images: api and ingest, Trivy failing on a critical with a fix, from a saved tarball with no Docker socket;
    - publish: main only, after every check, to GHCR as `sha-<short>` and `latest` with provenance;
    - `ci-ok`, the required check, which fails when any job failed or was cancelled.
  - Secrets: only `GEMINI_API_KEY` and `GROQ_API_KEY`, in the answer eval step alone. CI never calls Claude: `LLM_ANSWER_FALLBACK` is empty and there is no Anthropic key. `LLM_FALLBACK` is set to the router's Groq model only so startup validation passes; evals never call a fallback.
  - Eval: it runs only when an eval input changed (`packages/{core,db,llm,retrieval,telemetry}/src`, `services/api/src`, `evals` without reports, tests and Markdown, `uv.lock`), or on a manual run.
    - It restores `corpus-v1.dump` (release asset `corpus-v1`, published 2026-10-17 at 15:28 UTC; sha256 pinned in `evals/corpus.py`) into the compose Postgres.
    - It runs the retrieval suite on dev full, then the answer suite on dev ci with `--no-judge`, both with `--ci`.
    - The model reply cache carries over between runs (`actions/cache`).
    - Verdicts head the PR comment and the job summary, and reports go to an artifact.
    - A PR without secrets (Dependabot or a fork) shows the answer eval as NOT RUN at the top, with a warning annotation.
  - Nightly (`nightly-eval.yml`, 19:17 UTC, which is 03:17 Taipei; first run by hand on 2026-10-18, see Known Limitations): the test split with the judge. A scheduled run measures only when the eval inputs' hash differs from the last complete nightly run's, and a manual run always measures. A complete run is a pass, or broken floors with a verdict. It calls the harness directly, because make reports every failure as its own exit 2. It opens an issue on broken floors. Its artifact copies the run's reports, also one that replaced a committed report: the full test run is named by date (`--modified`, 2026-10-18, merged as #7).
  - Corpus dump (`make corpus-dump`):
    - Every table's schema goes in, but rows only for companies, filings, sections, chunks, financial_facts and alembic_version, plus those tables' id sequences.
    - It fails when the table of contents holds any other table's rows or sequence values.
    - It fails when the value of a secret-named variable or the SEC contact appears in its SQL.
    - Made 2026-10-17: 46.5 MB. gitleaks found nothing in its 257.6 MB of SQL. A restore takes about 11 s.
  - Dependabot: uv, Docker, GitHub Actions and npm, weekly, grouped, with a 7-day cooldown. It ignores (memory.md, 2026-10-19): typescript's major updates until openapi-typescript accepts typescript 7; `@types/node` 25 and up while the app runs on Node 24; the python image's minor and major updates, since a move to a new Python changes `.python-version`, the uv lock, CI and the image together.
  - main: ruleset 25308468 (active; user, from GitHub's API on 2026-10-18) requires a pull request (0 approvals) and the `ci-ok` check, not strict (a branch need not be up to date with main to merge). It blocks force pushes and deletion.
- Tests:
  - `make test` runs the unit tests (marker `unit`: no Docker, no network; about 10 s) and `make test-int` the integration tests (`integration`: Testcontainers with the compose images of Postgres with pgvector, RabbitMQ and Redis, on 127.0.0.1; about 1 min 50 s). The root `conftest.py` marks every test without `integration` or `e2e` as `unit`; `e2e` is registered but unused: the web's Playwright suite is TypeScript, in `web/e2e`. `async def` tests run under pytest-asyncio (auto mode).
  - No network: `network_guard.py` wraps `socket.getaddrinfo`, so looking up any host but localhost, loopback or 0.0.0.0 raises `NetworkBlockedError` at once. The root conftest installs it in the pytest process, and `run_worker.py` and the rate test's client processes install it too. Tests use recorded fixtures and respx instead.
  - Hypothesis keeps its example database in the repo's `.cache/hypothesis` (gitignored, on H:).
  - Beyond the earlier suites: chunker properties on generated texts (hypothesis), RRF, citation validation, amounts, SecClient timeouts and headers (unit); keyset pages over 100k chunks while chunks are inserted, and the embedding swap 0004-0006 while the API reads REST and GraphQL in a loop, with zero failed reads (integration).

## Current Development Status

Steps 1 (scaffolding), 2 (contracts), 3 (data) and 4 (workers: SEC client, discover, fetch, dead letters, backpressure, API limits) done on 2026-10-14; step 4b (parse, chunk, facts and `scripts/seed_real.py`) and step 5 (tests) on 2026-10-15. Step 6a (providers, local models, embed stage, hybrid search, answers) done on 2026-10-15. The dev database holds the 30 golden-set companies' latest 10-Ks, indexed with model A vectors, and their XBRL facts. Step 6b is in progress. Golden set v1 is AI-labeled, spot-checked by a non-expert and frozen, the eval harness is built, and decision 1 (the reranker) is settled on dev: TinyBERT-L-2 over the top 50 stays (2026-10-16). The gate-off dev answer run and decision 2 (`RELEVANCE_MIN` stays -3.0) followed. Router v2 and its dev rerun followed, and the calibration sample is drawn. The judge is calibrated against labels by Claude, a different and stronger model than the judge, not by a human; the sample is exported for it (`make calibrate ARGS=export`, then `ARGS=import`). The sentence splitter no longer cuts after abbreviations such as "U.S.", the judge is calibrated (kappa 0.84), and the dev answer suite was rerun with both (2026-10-16). Decision 3 is settled: minimal thinking stays, and fix B (the search starts while the router runs) is built and measured on dev. Decision 4 is settled: NVIDIA gpt-oss-20b stays the fallback; Groq gpt-oss-120b was skipped and NVIDIA's gpt-oss-120b is retired (410). On 2026-10-17 the judge follow-up spot check ran (3 of 4 natural unsupported sentences caught), then golden v1's test run. Its results are in the README and `evals/reports/2026-10-17.md`, and no floors are written until the user reviews them. Claude Haiku 5.5 can then be the answer's first fallback (`LLM_ANSWER_FALLBACK`, off by default), with thinking off. Its pinned test run is a comparison column in the README. The floors are written from Gemini's run, and the api runs this code. Step 6b is done (2026-10-17). Step 7 (CI/CD) is merged (pull request #1, 2026-10-18): its first CI run failed on a floor, fixed with Wilson intervals, and the next push and the push to main passed. The repo `kwnhyk04/filing-lens` is public and requires actions pinned to full-length commit SHAs, both CI-only Actions secrets are set, and the dev floors are written. Dev runs at revision 0008 (model A) through steps 5-6; the live embedding swap, with recall@10 before and after, follows step 6 (user decision). Step 8 (monitoring) is built and checked on branch `step-8-monitoring` (2026-10-18): offline checks, a final review, and a live check on a throwaway stack (screenshots in `docs/screenshots/`). The user committed it (5c8cb70) and opened a pull request. Its CI eval job stopped at startup, because `ApiSettings` had lost the empty-means-off rule for `OTEL_EXPORTER_OTLP_ENDPOINT` (a validator name clash, memory.md). With that fix, step 8 is merged to main as pull request #6 (febbe5f, git log). The first manual nightly run (2026-10-18) exited 4 on x18's judge error. The fix (validation rejects a marker that names no source; the artifact keeps the report) is merged as #7 (f58524b, git log).

Step 9 (review UI and demo mode) was planned on 2026-10-18 as three pull requests, each from main after the one before merges:
- A turns GraphQL over GET and the unused WebSocket route off, and fixes the Retry-After description.
- B1 adds the API lookups by id and links that citations need, plus the `clients/ts` fixes.
- B2 builds the web, the BFF, sign-in, the public demo, the Playwright suite and the CI web job.

The plan and its checklists are in todo.md. PR A merged as #8 (35902f3, git log), B1 as #9 (a2037af) and B2 as #10 (ab325a2). B3, added on 2026-10-19, fixed three of B2's review minors (leaving Ask, a failed sources lookup, the log label) and merged the same day (9b829a6). Step 9 is done (todo.md). A design round followed: the web app's own visual design, merged as #15 (73bb1c0). The user then compared it with a mockup made separately and chose the mockup's style, with a bigger sources panel that fits the window from the first screen, merged as #16 (a14a019; `docs/design.md`, screenshots in `docs/screenshots/ui/`). What the mockup has and the app lacks is listed as candidates in todo.md. The first five, small and with no API change (copy, New question, the answer's timings, the demo header's coverage line, the Indexed pill), were merged as #17 (e1059d7). The source cards' fiscal year end followed, from a new snapshot, merged as #18 (86718cd). Dependabot's python group merged as #4 (93f464d) and the Dependabot follow-ups as #12 (e2b581d).

Step 10 (deploy) was planned on 2026-10-20 and approved on 2026-10-21 with three changes (memory.md):
- production runs free providers only (superseded on 2026-10-21: Claude Haiku first, then the free chain);
- the Gemini key gets its own Google project before AI goes on;
- the egress proxy is the first item after go-live.

It is four PRs plus the user's manual steps, all listed under step 10 in todo.md:
- 10a, API hardening: merged as #19 (1f15729).
- 10b, a GraphQL DataLoader: built on `step-10-dataloader` (2026-10-21) and committed as 305b123, but not merged then. Main (8e638a2) was merged into it on 2026-10-24, uncommitted; the user's ship concludes the merge.
- 10c, the deploy config and runbook: built on `step-10-deploy-config` from main at 7979cdb (2026-10-24), merged as #28 (e75cb57).
- 10d, a docs record after go-live.

Before 10c: the rerank deadline merged as #21 (aca22a6), Claude first as #22 (7979cdb), the certifi bump as #23 (fe90d5f) and the Next.js security update as #27 (5c62f7f). After it, the commit-message rule as #26 (8e638a2).

## Known Limitations

The targets are design goals; 6b measures them on the golden set.

Production (step 10, planned) runs no egress proxy until the first PR after go-live adds one, as FreightAudit runs it (user, 2026-10-21). Until then, the internet-facing api and tailscale containers can reach services listening on the PC's own ports through `host.docker.internal`.

GraphQL page queries (a filing's sections, chunks and facts; a company's filings) still run once per parent. Within the depth limit, one query can make 708 of them on corpus-v1 (found by PR 10b's review). The user chose 10c's nested `first` cap (#28), which shrinks each nested page but keeps the 708. Measured on corpus-v1's rows with 10b's loaders and the cap together (2026-10-24, memory.md): that query reads 4,413 rows, against 9,081 before the cap, and a cited-chunks query with links reads 1,280 rows, against 6,080. Batching `Section.chunks` would cut the page queries themselves.

First dev measurements (gate off, judge not yet calibrated, 2026-10-16; single run, 95% CIs in the report):
- Numeric exact match 0.821 and comparison match 0.200.
- False refusal 0.288, and correct refusal 1.000.
- Time to first token: p50 1.8 s and p95 2.3 s (36 live answers). Full answer p95 9.3 s.

The router caused most of those misses: wrong tickers and comparisons without a metric. Router v2 fixed them (`docs/prompt-log.md`), with these dev results (gate off):
- numeric and comparison match 1.000;
- correct refusal 1.000;
- false refusal 0.096 (5 of 52: 3 where the model found no evidence in the retrieved passages, 2 where no sentence held up).

The rerun with the splitter fix and the calibrated judge (gate off, 2026-10-16) kept false refusal at 0.096, with the same five questions. x16 now keeps its whole sentence, and citation coverage rose from 0.930 to 0.941 (target 0.95). Citation precision (0.981) and faithfulness (0.937) now count and pass, but the judge's calibration sample held no natural unsupported sentence.

Decision 3 (dev, 2026-10-16, 09:00-09:25 UTC; numbers in `docs/memory.md`):
- With every call live, time to first token was p50 4.2 s and p95 9.3 s. Stage p50: router 0.66 s, retrieval 0.30 s, and Gemini's own first token 3.4 s.
- Gemini's own first token drifts with the hour on the free tier: 1.0 s p50 at 05:56 UTC against 3.4 s at 09:00, on the same questions. The 09:00 runs also drew Gemini 503s.
- Its thinking setting makes no measurable difference, so minimal stays.
- Even at Gemini's best, router and retrieval take about 1 s before Gemini starts, so the p50 1.0 s target is out of reach on free tiers with the stages in sequence.
- Fix B (search started with the router): where the router agreed (18 of 28 searching dev questions), the time before Gemini starts fell from p50 1,060 to 684 ms. End to end, TTFT stayed Gemini-bound at p50 3.7 s and p95 9.6 s (10:00 UTC).
- The router sometimes leaves tickers empty for a company the question names, such as x01 (Apple) and x11 (Visa); those questions search every company. On dev that is not clearly worse: the question names the company, so the unscoped search ranks its chunks anyway (memory.md). No code fills the ticker in.

Test split (2026-10-17, free tiers; README table):
- Missed: false refusal 0.130 (the router sent 3 textual questions out of scope), citation precision 0.944 (one comparison conclusion), recall@10 0.583 (6 questions), TTFT p50 1.55 s.
- Passed: numeric exact match, coverage, faithfulness, correct refusal, MRR, TTFT p95 (1.84 s), full answer p95, tokens and cost.

Claude Haiku 5.5, pinned (2026-10-17):
- **Dev:** adaptive thinking used up the 1,024-token answer cap, so its thinking is now off. The rerun had no truncated or empty reply.
  - On dev it answered n17 and n24 INSUFFICIENT_EVIDENCE: their fact headings read "fiscal 2025 Q2" for year-end values taken from 2026 10-Qs. Not fixed.
- **Test (comparison on Gemini's router replies, judge on):** numeric 1.000, citation precision 0.958, faithfulness 0.944, false refusal 0.130 (the same 3 router calls). Its own first token was 0.13 s faster at p50, paired.
  - A first Haiku run that asked the router again was replaced, because the router routed x13, x14 and x18 differently.
  - Findings: n28 hedged over a fact heading, and c12's comparison conclusion was rated "partly".
- Claude's switch-off is stored in Redis (`ai:claude:off`) since 2026-10-21, so a restart keeps it.

The refusal gate stays at -3.0, which adds no false refusal on dev. `split_sentences` ends a sentence after an abbreviation (U.S., e.g., Inc., Corp., Co., No., etc.) only when a common sentence starter follows (The, It, However...), so "in the U.S. Revenue rose" stays one sentence.

Golden v1's passage gold, which retrieval metrics rest on, is AI-labeled, spot-checked by a non-expert: a fast check that cannot validate the labels on its own (blind kappa 0.10, `evals/eval-card.md`). Time to first token already misses its target (6b item): textual answers took 2.2 s and 3.8 s in the 6a smoke runs (single runs, 2026-10-15) against p95 2.0 s. Cause: the stages run one after another, the router call (0.53-0.54 s), then retrieval (0.21-0.27 s), then Gemini's first visible text 1.4-3.0 s after its call, with a prompt of about 4,600 tokens (12 chunks); the stream filter holds back only 24 characters. The numeric answer's first token came at 2.0 s (router 0.68 s, facts 0.05 s, Gemini 1.3 s with a prompt of about 340 tokens), so Gemini's first token alone exceeded the p50 1.0 s target in every run.

Tables are flattened row by row into the text. Four 10-Ks keep MD&A or the statements in a separate financial section that their Items 7, 7A or 8 only point to. That content is chunked under the item heading before it:
- JPM under Item 15;
- CVX under Item 14;
- NVDA and PLD under Items 15 and 16, for their Item 8 content.

That is 1,373 chunks, 12% of the corpus; XOM is not in the corpus. The fix is deferred to the next corpus (memory.md, 2026-10-18), and the UI shows the item as stored.

The fiscal year and period fallback (period of report) is approximate for 52-53 week years; it was not needed for the 30 golden-set filings. Company-level failures (discovery, facts) show in the job status and `dead_letters`, not in the API's failure list, which holds filings only. Flipping `RETRIEVAL_EMBEDDING_COLUMN` needs an API and embed restart. Validation rejects derived figures (growth rates computed by the model), and the refusal threshold is provisional until 6b. Streamed deltas are the draft: when validation changes it, the `completed` answer (with warnings) replaces them. `make seed-fake` locks `chunks` while it loads, so it is not for a database that serves traffic. The web `/readyz` equals `/healthz` by design: the web serves the demo when the API is down. `citation_error` is exact on letter case, so a quote that recapitalizes a word fails. `parse_amount` reads a single amount, not amounts inside prose (step 6 adds the finder), with the scale words thousand, million, billion and trillion or the abbreviations K, M, B or bn, and T; others, such as MM, are refused. The test network guard stops name lookups; a client that connects to a literal IP address would pass it (none does).

500 is not listed in the spec.

CI (step 7):
- A setup without floors fails the CI eval on purpose ("No floors ... --ci would gate nothing"). The dev floors are written, but a new primary model needs its own.
- A restored corpus builds its HNSW index afresh. Two restores give identical top 10s on all 70 dev questions, but the dev database's index differs on 2: o03 and u02, both unanswerable, by one chunk each. Scored retrieval metrics are identical.
- Dependabot and fork PRs get no secrets, so the answer eval is NOT RUN there; the nightly run measures main after the merge.
- On this PC, Trivy over the whole repo through the Windows bind mount took 11 min, so `make vuln-scan` names each lockfile (seconds).
- The image scans report 44 HIGH Debian packages without a fix, and no critical.
- The workflows run on GitHub (the public Actions page, read on 2026-10-18 at 03:07 Taipei):
  - CI #1 on pull request #1 failed (the floor problem fixed with Wilson intervals). CI #2 on its next push and CI #3 on the push to main passed.
  - CI #7 on pull request #5 and CI #8 on its push to main passed.
  - So the `safe.directory` setup for oasdiff's and gitleaks' git works on the runner's checkout.
- Dependabot's npm group pull request #3 failed CI on typescript 7.0.2, which openapi-typescript 7.13.0 refuses (peer `typescript ^5.x`). The typescript-major ignore merged with B2 (#10), and the user ruled the #3 item obsolete (2026-10-19). After the follow-ups merged (#12), #2 and #11 closed or were replaced (user).
- Nightly eval:
  - GitHub's API showed no runs of `nightly-eval.yml` at 04:37 Taipei on 2026-10-18, after its old 03:00 schedule. Likely cause, not confirmed: the cron was on minute 0, where GitHub delays or drops scheduled runs under load. It now runs at 19:17 UTC; whether the schedule fires is still to be checked (todo.md).
  - The first manual run (39068994474, 2026-10-18, main at febbe5f) ran all 30 test questions, then exited 4: "x18 (judge): sentence 1: judged sources [1, 2], cited [1, 2, 12]".
    - Cause: x18's answer showed a bare `[12]`, which Gemini wrote for C12. Validation reads only source ids, so it let the marker through. The harness then gave the judge no source 12 to rate.
    - The recorded textual fixture holds the same defect. Replayed live once, the judge invented a rating for the unseen source instead, which `parse` accepted. The eval now refuses such a sentence before any judge call (merged as #7).
    - Step 8 changed nothing on that path.
    - The fix (validation rejects such a marker) is merged as #7 (f58524b). The next manual nightly run checks it (todo.md).
  - comparison_match fell to 0.800 (4 of 5): c15 was refused after validation dropped every sentence of its draft and its regeneration. This is answer-model variation, not a regression; the code and gold facts are unchanged. A rerun replays c15's cached refusal; comparison_match has no floor.
  - The run's artifact held only the verdict. The full test run's report is named by date, so it replaced the committed `evals/reports/2026-10-17.json` in the checkout, and the copy step listed untracked files only. The copy now adds `--modified` (merged as #7).

## Planned Features

See `docs/todo.md` for the 10-step build plan (8 build steps, review UI, deploy).
