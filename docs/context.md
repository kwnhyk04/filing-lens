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

LLM roles from env vars (`provider:model`): `gemini:gemini-3.5-flash-lite` answers, `groq:openai/gpt-oss-20b` routes, `nvidia:openai/gpt-oss-20b` is the fallback. Optionally `LLM_ANSWER_FALLBACK=anthropic:claude-haiku-5-5` (Claude Haiku 5.5 on prepaid credits) is tried for answers between the primary and the fallback. One OpenAI-compatible client (Groq, OpenRouter, NVIDIA NIM, Ollama), a Gemini adapter on google-genai, and a Claude adapter on the `anthropic` SDK (1.15.0, which runs on httpx2). Local models on CPU through sentence-transformers and torch (2.14.1+cpu in the Linux images; 2.12.1 on Windows, pinned below 2.13 there, see memory.md): bge-small (model A) and bge-base (model B) embedders, TinyBERT-L-2 reranker by default. Embeddings: local sentence-transformers model by default; the swap series in `docs/migrations.md` moves chunks from BAAI/bge-small-en-v1.5 (384 dimensions, model A) to BAAI/bge-base-en-v1.5 (768, model B). Dev stays on model A at revision 0008, the last before the swap, until the live swap after step 6. Deployment: UI on Vercel, backend on the PC via Tailscale Funnel.

Pinned versions live in `uv.lock`, `web/package-lock.json`, `clients/ts/package-lock.json`, `infra/docker-compose.yml` (Postgres 18 with pgvector 0.8.7, RabbitMQ 4.3, Redis 8.8) and the `Makefile` (ariadne-codegen 0.19.0, oasdiff v1.32.1 by image digest). Web: Next.js 16, React 19, TypeScript 5.9 in strict mode.

Local ports (bound to 127.0.0.1; chosen so all three projects can run at once; compose project name `filinglens`). Compose publishes exactly these (verified with `docker compose ps` on 2026-10-14) and reads them from `.env`. `web/` takes 3100 from its npm scripts. The fake SEC server lives in the ingest tests on a free port; 4110 stays reserved for a local-run server. The worker's probe port (8001) stays inside its container.

| Service | Host port |
| --- | --- |
| Postgres (pgvector) | 5433 |
| Redis | 6380 |
| RabbitMQ AMQP / management UI | 5672 / 15672 |
| api | 4100 |
| fake SEC server (tests and local runs) | 4110 |
| web (Next.js) | 3100 |
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
- `packages/telemetry`: structlog JSON logging with redaction.
- `packages/sec_client`: `SecClient`, with the shared rate limit, the cool-off, the disk cache, companyfacts and the company ticker list, and a count of the requests it sends.
- `packages/db`: the async engine, the models (with a small pgvector `Vector` type and `chunk_id()`), migrations 0001-0008 and the seed.
- `packages/retrieval`: `search` (scoped vector and full-text candidates, `reciprocal_rank_fusion` with k = 60, rerank with a timeout) and `facts.get_financial_fact` (latest-filed rule).
- `packages/llm`: the provider clients (`providers.py`, Claude's credit rules and `credits_usd` included), the local embedders and rerankers (`local.py`), the router (`router.py`), the reply format and stream filter (`answer.py`), post-validation (`validate.py`: `citation_error`, amounts, per-sentence checks) and the daily AI budget (`budget.py`).
- `services/ingest/src/filinglens_ingest`: the Celery worker with probes (`worker.py`), kombu queues (`topology.py`), the tasks `discover`, `fetch`, `parse`, `chunk`, `embed` and `facts` (`pipeline.py`), HTML to text and item sections (`parsing.py`), token-aware chunks with the vendored bge-small tokenizer (`chunking.py`, `tokenizer-bge-small-en-v1.5.json`), companyfacts rows and fiscal periods (`companyfacts.py`), the dead-letter replay (`replay.py`) and the `reembed` task (`reembed.py`).
- The fake data seed (`scripts/seed_fake.py`), the real one (`scripts/seed_real.py`), the 30 golden-set companies (`evals/golden-companies.csv`), and the compose stack with prod override and Dockerfile (`infra/`).

API (`services/api/src/filinglens_api/`): `main.py` (app, probes, request ids, catch-all 500), `routes.py` (REST v1 and key checks), `limits.py` (rate limits, AI switch and budget, body size, answer time), `schemas.py` (pydantic contract models), `problems.py` (RFC 9457 handlers and response docs), `backend.py` (the `Backend` protocol, keyset cursors, `LiveBackend`), `answering.py` (router, evidence, draft, validation, refusals), `graph.py` (Strawberry schema), `contracts.py` (spec export and `--check`).

Contracts and clients: `contracts/openapi.json` and `contracts/schema.graphql` (generated, committed); `clients/python` (openapi-python-client), `clients/python-graphql` (ariadne-codegen), `clients/ts` (openapi-typescript types, openapi-fetch client, graphql-codegen documents, hand-written `index.ts`); shared GraphQL operations in `clients/operations.graphql`.

Tests: the root `conftest.py` (network guard, markers, JSON logs, hypothesis profile, Testcontainers fixtures) and `network_guard.py`; each package and service keeps its tests in its own `tests/`.

Evals (`evals/`):
- `golden.py`: golden set v1 build and freeze.
- `label.py`: `make audit` and `make label`; both refuse once the set is frozen.
- `metrics.py`: ranking metrics, exact match, percentiles, Cohen's kappa, bootstrap intervals and the floor rule.
- `calls.py`: the reply cache, call records and 429 handling.
- `judge.py`: the `LLM_JUDGE` prompt, schema and parsing.
- `harness.py`: `make eval`.
- `providers.json`: limits and prices, each with its source and date.
- `eval-card.md`.
- `golden/v1/`: frozen, with a sha256 manifest.
- `reports/`.

## Implemented Functionality

- Config: each process validates its env vars at startup and exits naming each bad one without echoing values, for example `Invalid configuration: API_KEY: Field required`. Compose also refuses to start without the required `.env` values.
- API keys: `API_KEY` opens every route except the admin routes; `ADMIN_API_KEY` opens every route and is the only key for `POST /v1/ingest-jobs` and `GET /v1/ingest-jobs/{id}`. Both are required, at least 32 characters, must differ, and are read only from the `X-API-Key` header (a key in the URL gets 401). Missing or unknown key: 401 with `WWW-Authenticate: APIKey`; `API_KEY` on an admin route: 403. `/healthz` and `/readyz` need no key. Every response carries `X-Request-ID`.
- REST v1: `POST /v1/ingest-jobs` (202, `Location`, required `Idempotency-Key`), `GET /v1/ingest-jobs/{id}` (status counts plus a page of failures), `GET /v1/companies`, `GET /v1/filings`, `GET /v1/search` (cursor holds score, chunk id and index version), `POST /v1/answers` and `POST /v1/answers/stream` (Server-Sent Events: `delta`, then `completed`, or `failed` mid-stream). Lists use keyset pagination: `limit` at most 100, opaque `cursor`, `next_cursor`.
- Errors: RFC 9457 problems (`application/problem+json`, `type: about:blank`, `code` from the taxonomy). Validation is 422 `validation_failed` with `errors[{detail, pointer}]`; a bad cursor is 400; 429 sends `Retry-After`, `RateLimit-Limit` and `RateLimit-Remaining`; 503 sends `Retry-After`. Unexpected errors are 500 with no detail, logged with the request id.
- Data behind the routes: `LiveBackend` serves companies, filings, sections, chunks and facts from Postgres. It also creates and reports ingest jobs: creation is idempotent per Idempotency-Key, stores the job and one `ingest_job_companies` row per CIK, then queues one discover per company with publisher confirms (503 if RabbitMQ refuses). A retry queues again while the job is still `queued`. The job view counts items by status and pages failures by accession number. Search and answers are live (see Search and answers below).
- Request limits:
  - Per API key, a Redis token bucket of 60 a minute on every route (GraphQL included), and 10 a minute shared by `/v1/answers` and its stream; 429 carries `Retry-After` and `RateLimit-*`. The limiter fails open while Redis is down.
  - Answers return 503 `ai_unavailable` when `AI_ENABLED=false` or once the UTC day's LLM tokens (`filinglens_llm.budget`, Redis hash `ai:usage:<date>`) reach `DAILY_AI_TOKEN_BUDGET`. That check fails closed. Every model call adds its tokens (`budget.record`).
  - Bodies over 64 KB get 413 (`request_entity_too_large`), chunked ones included. An answer, streamed or not, gets 30 s, then 502 (a `failed` event in a stream).
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
- GraphQL `/graphql` (either key): `Company`, `Filing`, `Section`, `Chunk`, `FinancialFact`, `Answer`, `Citation`, `Usage`; Relay connections (`edges`, `pageInfo`) for companies, filings, chunks and facts. Resolver errors carry `extensions.code`; unexpected ones are masked.
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
  - Answers (`filinglens_api.answering`): the router picks numeric, textual, comparison or out_of_scope with tickers, years, period and metric; numeric questions read XBRL facts (`get_financial_fact`, latest-filed rule), others search. The search starts while the router runs, on the companies and years the question names (`router.guess`), and is kept only when the router's plan asks for the same scope; the primary writes cited text with quotes, streamed as `delta` events; validation checks every sentence's citations and amounts, regenerates once, then drops failing sentences with a warning. Refusals: out of scope, untracked company, fiscal year without a 10-K yet, best rerank score under -3.0. A failed router call falls back to `LLM_FALLBACK`. A failed answer call tries `LLM_ANSWER_FALLBACK` first when it is set and on, then `LLM_FALLBACK`. Each fallback is counted in `ai:usage:<date>` field `fallbacks`; a 402 or a failed last model gives 503. Claude (`LLM_ANSWER_FALLBACK=anthropic:claude-haiku-5-5`) is off for the rest of the credit period once a 402, a 400 naming a spend limit, or a 429 without `Retry-After` shows its credits are gone (one log line), and from `ANTHROPIC_CREDITS_EXPIRE` (UTC); a 429 asking for 10 s or less is retried once. `usage.cost_usd` is the credits an answer spent, $0 on the free tiers.
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
    - The answer suite runs the Answerer as the API does (no fallback, `today` pinned to the set's as_of, 30 s per question). Each model reply is cached by call key, progress goes to a run file, and tokens are counted in Redis db 15.
    - A 429 waits when Retry-After is 120 s or less. The third in a row, or a longer wait, exits 2, and a rerun resumes.
    - The judge scores every answer that was not refused. Calibrated on 2026-10-16: Cohen's kappa 0.84 (95% CI 0.59 to 1.00) against Claude's labels on 29 sentences, so citation precision and faithfulness count. With the one unparsed reply counted as a disagreement, kappa is 0.77 (0.47 to 1.00). Every negative in that sample was constructed, so its detection of natural unsupported sentences is untested. The follow-up spot check (2026-10-17) took 6 natural sentences that fail the validator, from decision 4's NVIDIA runs (`evals/calibration/v1-followup/`). The judge failed 3 of the 4 that Claude labeled not supported (`evals/eval-card.md`).
    - Reports go to `evals/reports/runs/`: JSON with per-question records, plus a markdown table of target, measured value, 95% bootstrap CI, n and status. Each run also adds an `eval_runs` row and prints the deltas against the previous report.
    - Floors live in `evals/thresholds.json`, and a broken floor exits 1. Runs never write them: `python -m evals.harness --set-floors REPORT` applies the floor rule to a saved report's measured values (quality, tokens, cost and latency, TTFT included) and keeps only tighter floors. Answer floors are keyed per primary model, so the free setup's $0 billed floor never meets Claude. They were written on 2026-10-17 from Gemini's test report.
    - Cost as billed is the prepaid credits each call spent, from its usage (`credits_usd`), and $0 on the free tiers. Evals pin one answer model with no fallback, and credits gone exit 2. `LLM_JUDGE` can never be Claude.
    - `--compare A B` prints paired per-question differences, including the primary call's own first-token and total times.
    - `--tag=NAME` calls the answer models live once under their own cache keys, so earlier reports still read their replies. `--primary-tag=NAME` does that for the primary only, with router replies from the cache.
    - `--router-primary=PROVIDER:MODEL` keys router calls as that primary's run did. Another answer model then gets identical routes (the Haiku comparison on test), and its end-to-end latency is not measured.
    - Each report records the code it measured (the commit, whether the source files differ from it, and a sha256 of them as they stand; data and docs left out) and the sha256 of each system prompt and schema.
- Logs: structlog JSON lines on stdout from the API, the worker, migrations and the seed, including uvicorn, Celery and Alembic records. Each line carries `service`, `level` (threshold from `LOG_LEVEL`) and, during a request, `request_id`. Credential-named fields and the API key value are redacted.
- Compose: `infra/docker-compose.yml` for development; `infra/docker-compose.prod.yml` unpublishes Postgres, RabbitMQ and Redis and adds `restart: unless-stopped` and memory limits (Postgres 1.5 GB). Postgres runs with `shm_size: 256mb` in both, so parallel HNSW builds fit in `/dev/shm`; `make check-parallel-hnsw` checks it on the dev stack. The worker gets `SEC_USER_AGENT` (compose refuses to start without it) and the repo's `.cache/sec` folder as its SEC cache (a bind mount), and the API gets `AI_ENABLED` and `DAILY_AI_TOKEN_BUDGET`.
- Contracts: `make codegen` exports both contracts and regenerates all four clients, then type-checks the TS client. `make contracts-check` runs codegen and fails if git sees unstaged or untracked changes under `contracts/` or `clients/`. `make contracts-breaking` runs oasdiff (Docker) against `BASE` (default `main`) and fails on breaking changes.
- Web: placeholder Next.js page with `/healthz` and `/readyz`.
- Secrets: gitleaks pre-commit hook, allowlist `.dockerignore`, images run as uid 10001.
- Tests:
  - `make test` runs the unit tests (marker `unit`: no Docker, no network; about 10 s) and `make test-int` the integration tests (`integration`: Testcontainers with the compose images of Postgres with pgvector, RabbitMQ and Redis, on 127.0.0.1; about 1 min 50 s). The root `conftest.py` marks every test without `integration` or `e2e` as `unit`; `e2e` is registered for step 9's Playwright tests. `async def` tests run under pytest-asyncio (auto mode).
  - No network: `network_guard.py` wraps `socket.getaddrinfo`, so looking up any host but localhost, loopback or 0.0.0.0 raises `NetworkBlockedError` at once. The root conftest installs it in the pytest process, and `run_worker.py` and the rate test's client processes install it too. Tests use recorded fixtures and respx instead.
  - Hypothesis keeps its example database in the repo's `.cache/hypothesis` (gitignored, on H:).
  - Beyond the earlier suites: chunker properties on generated texts (hypothesis), RRF, citation validation, amounts, SecClient timeouts and headers (unit); keyset pages over 100k chunks while chunks are inserted, and the embedding swap 0004-0006 while the API reads REST and GraphQL in a loop, with zero failed reads (integration).

## Current Development Status

Steps 1 (scaffolding), 2 (contracts), 3 (data) and 4 (workers: SEC client, discover, fetch, dead letters, backpressure, API limits) done on 2026-10-14; step 4b (parse, chunk, facts and `scripts/seed_real.py`) and step 5 (tests) on 2026-10-15. Step 6a (providers, local models, embed stage, hybrid search, answers) done on 2026-10-15. The dev database holds the 30 golden-set companies' latest 10-Ks, indexed with model A vectors, and their XBRL facts. Step 6b is in progress. Golden set v1 is AI-labeled, spot-checked by a non-expert and frozen, the eval harness is built, and decision 1 (the reranker) is settled on dev: TinyBERT-L-2 over the top 50 stays (2026-10-16). The gate-off dev answer run and decision 2 (`RELEVANCE_MIN` stays -3.0) followed. Router v2 and its dev rerun followed, and the calibration sample is drawn. The judge is calibrated against labels by Claude, a different and stronger model than the judge, not by a human; the sample is exported for it (`make calibrate ARGS=export`, then `ARGS=import`). The sentence splitter no longer cuts after abbreviations such as "U.S.", the judge is calibrated (kappa 0.84), and the dev answer suite was rerun with both (2026-10-16). Decision 3 is settled: minimal thinking stays, and fix B (the search starts while the router runs) is built and measured on dev. Decision 4 is settled: NVIDIA gpt-oss-20b stays the fallback; Groq gpt-oss-120b was skipped and NVIDIA's gpt-oss-120b is retired (410). On 2026-10-17 the judge follow-up spot check ran (3 of 4 natural unsupported sentences caught), then golden v1's test run. Its results are in the README and `evals/reports/2026-10-17.md`, and no floors are written until the user reviews them. Claude Haiku 5.5 can then be the answer's first fallback (`LLM_ANSWER_FALLBACK`, off by default), with thinking off. Its pinned test run is a comparison column in the README. The floors are written from Gemini's run, and the api runs this code. Step 6b is done (2026-10-17); step 7 (CI/CD) is next. Dev runs at revision 0008 (model A) through steps 5-6; the live embedding swap, with recall@10 before and after, follows step 6 (user decision).

## Known Limitations

The targets are design goals; 6b measures them on the golden set.

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
- Claude's credits-gone flag lives in the process, so a restart costs one refused call.

The refusal gate stays at -3.0, which adds no false refusal on dev. `split_sentences` ends a sentence after an abbreviation (U.S., e.g., Inc., Corp., Co., No., etc.) only when a common sentence starter follows (The, It, However...), so "in the U.S. Revenue rose" stays one sentence.

Golden v1's passage gold, which retrieval metrics rest on, is AI-labeled, spot-checked by a non-expert: a fast check that cannot validate the labels on its own (blind kappa 0.10, `evals/eval-card.md`). Time to first token already misses its target (6b item): textual answers took 2.2 s and 3.8 s in the 6a smoke runs (single runs, 2026-10-15) against p95 2.0 s. Cause: the stages run one after another, the router call (0.53-0.54 s), then retrieval (0.21-0.27 s), then Gemini's first visible text 1.4-3.0 s after its call, with a prompt of about 4,600 tokens (12 chunks); the stream filter holds back only 24 characters. The numeric answer's first token came at 2.0 s (router 0.68 s, facts 0.05 s, Gemini 1.3 s with a prompt of about 340 tokens), so Gemini's first token alone exceeded the p50 1.0 s target in every run.

Tables are flattened row by row into the text. Some 10-Ks (XOM, CVX, JPM, PLD and NVDA in the survey) keep MD&A or the statements in a separate financial section, and their Items 7, 7A or 8 only point to it: that content is chunked under the last item (15 or 16). The fiscal year and period fallback (period of report) is approximate for 52-53 week years; it was not needed for the 30 golden-set filings. Company-level failures (discovery, facts) show in the job status and `dead_letters`, not in the API's failure list, which holds filings only. Flipping `RETRIEVAL_EMBEDDING_COLUMN` needs an API and embed restart. Validation rejects derived figures (growth rates computed by the model), and the refusal threshold is provisional until 6b. Streamed deltas are the draft: when validation changes it, the `completed` answer (with warnings) replaces them. `make seed-fake` locks `chunks` while it loads, so it is not for a database that serves traffic. The web `/readyz` equals `/healthz` until the backend-for-frontend lands. `citation_error` is exact on letter case, so a quote that recapitalizes a word fails. `parse_amount` reads a single amount, not amounts inside prose (step 6 adds the finder), with the scale words thousand, million, billion and trillion or the abbreviations K, M, B or bn, and T; others, such as MM, are refused. The test network guard stops name lookups; a client that connects to a literal IP address would pass it (none does).

500 is not listed in the spec. CI does not exist yet, so `contracts-check` and `contracts-breaking` run only through make until step 7.

## Planned Features

See `docs/todo.md` for the 10-step build plan (8 build steps, review UI, deploy).
