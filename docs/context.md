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

Python 3.12+, uv workspace, ruff, pyright, FastAPI, Strawberry, SQLAlchemy 2 (async), Alembic, Celery, RabbitMQ, Redis, Postgres + pgvector, httpx, structlog, pytest, Testcontainers, OpenTelemetry, Docker, GitHub Actions. Thin TypeScript UI.

LLM providers (switchable by env vars): Gemini Flash (free tier) for answers, Groq for the router, Ollama for local runs. Embeddings: local sentence-transformers model by default; the swap series in `docs/migrations.md` moves chunks from BAAI/bge-small-en-v1.5 (384 dimensions, model A) to BAAI/bge-base-en-v1.5 (768, model B). Dev stays on model A at revision 0007, the last before the swap, until the live swap after step 6. Deployment: UI on Vercel, backend on the PC via Tailscale Funnel.

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
- `packages/sec_client`: `SecClient`, with the shared rate limit, the cool-off and the disk cache.
- `packages/db`: the async engine, the models (with a small pgvector `Vector` type and `chunk_id()`), migrations 0001-0007 and the seed.
- `packages/retrieval`: the vector search query `nearest_chunks`.
- `packages/llm`: an `embed` stub and the daily AI budget (`budget.py`).
- `services/ingest/src/filinglens_ingest`: the Celery worker with probes (`worker.py`), kombu queues (`topology.py`), `discover` and `fetch` (`pipeline.py`), the dead-letter replay (`replay.py`) and the `reembed` task (`reembed.py`).
- The fake data seed (`scripts/seed_fake.py`), the 30 golden-set companies (`evals/golden-companies.csv`), and the compose stack with prod override and Dockerfile (`infra/`).

API (`services/api/src/filinglens_api/`): `main.py` (app, probes, request ids, catch-all 500), `routes.py` (REST v1 and key checks), `limits.py` (rate limits, AI switch and budget, body size, answer time), `schemas.py` (pydantic contract models), `problems.py` (RFC 9457 handlers and response docs), `backend.py` (the `Backend` protocol, keyset cursors, `LiveBackend`), `graph.py` (Strawberry schema), `contracts.py` (spec export and `--check`).

Contracts and clients: `contracts/openapi.json` and `contracts/schema.graphql` (generated, committed); `clients/python` (openapi-python-client), `clients/python-graphql` (ariadne-codegen), `clients/ts` (openapi-typescript types, openapi-fetch client, graphql-codegen documents, hand-written `index.ts`); shared GraphQL operations in `clients/operations.graphql`.

Planned: parse, chunk and facts tasks with `scripts/seed_real.py` (step 4b), hybrid retrieval, citation validator, eval harness.

## Implemented Functionality

- Config: each process validates its env vars at startup and exits naming each bad one without echoing values, for example `Invalid configuration: API_KEY: Field required`. Compose also refuses to start without the required `.env` values.
- API keys: `API_KEY` opens every route except the admin routes; `ADMIN_API_KEY` opens every route and is the only key for `POST /v1/ingest-jobs` and `GET /v1/ingest-jobs/{id}`. Both are required, at least 32 characters, must differ, and are read only from the `X-API-Key` header (a key in the URL gets 401). Missing or unknown key: 401 with `WWW-Authenticate: APIKey`; `API_KEY` on an admin route: 403. `/healthz` and `/readyz` need no key. Every response carries `X-Request-ID`.
- REST v1: `POST /v1/ingest-jobs` (202, `Location`, required `Idempotency-Key`), `GET /v1/ingest-jobs/{id}` (status counts plus a page of failures), `GET /v1/companies`, `GET /v1/filings`, `GET /v1/search` (cursor holds score, chunk id and index version), `POST /v1/answers` and `POST /v1/answers/stream` (Server-Sent Events: `delta`, then `completed`, or `failed` mid-stream). Lists use keyset pagination: `limit` at most 100, opaque `cursor`, `next_cursor`.
- Errors: RFC 9457 problems (`application/problem+json`, `type: about:blank`, `code` from the taxonomy). Validation is 422 `validation_failed` with `errors[{detail, pointer}]`; a bad cursor is 400; 429 sends `Retry-After`, `RateLimit-Limit` and `RateLimit-Remaining`; 503 sends `Retry-After`. Unexpected errors are 500 with no detail, logged with the request id.
- Data behind the routes: `LiveBackend` serves companies, filings, sections, chunks and facts from Postgres. It also creates and reports ingest jobs: creation is idempotent per Idempotency-Key, stores the job and one `ingest_job_companies` row per CIK, then queues one discover per company with publisher confirms (503 if RabbitMQ refuses). A retry queues again while the job is still `queued`. The job view counts items by status and pages failures by accession number. Search and answers return 501 `not_implemented` until step 6.
- Request limits:
  - Per API key, a Redis token bucket of 60 a minute on every route (GraphQL included), and 10 a minute shared by `/v1/answers` and its stream; 429 carries `Retry-After` and `RateLimit-*`. The limiter fails open while Redis is down.
  - Answers return 503 `ai_unavailable` when `AI_ENABLED=false` or once the UTC day's LLM tokens (`filinglens_llm.budget`, Redis hash `ai:usage:<date>`) reach `DAILY_AI_TOKEN_BUDGET`. That check fails closed. Nothing records usage until step 6's provider calls `budget.record`.
  - Bodies over 64 KB get 413 (`request_entity_too_large`), chunked ones included. An answer, streamed or not, gets 30 s, then 502 (a `failed` event in a stream).
- Ingest pipeline:
  - The API's job queues `discover`. It walks one page of the company's submissions JSON per run, from the main file through the older files, and skips files whose newest filing predates the job's `since`.
  - Discover upserts the company (if new) and the 10-K and 10-Q filings, and adds job items: `skipped` when already fetched, otherwise `pending`. It then queues a `fetch` per pending filing, with confirms, and marks it `running`. When RabbitMQ nacks because `fetch` holds 10,000 messages, discover queues itself again after a jittered backoff of up to 60 s.
  - `fetch` downloads the primary document into the SEC cache and marks the filing `fetched`; it skips a filing already at or past `fetched`. It retries `TransientError` six times with exponential backoff (at most 300 s, jittered) through `fetch.retry`.
  - A final failure (or any unexpected error) writes a `dead_letters` row and marks the filing and item `failed`. The task then rejects without requeue, so RabbitMQ moves the message to `fetch.dlq` (or `discover.dlq`) through the `filinglens.dlx` exchange.
  - The job ends `succeeded`, `partially_failed` (the prompt's `completed_with_errors`) or `failed` once every company and filing is settled, under a lock on the job row. `python -m filinglens_ingest.replay --queue fetch.dlq --limit 100` moves dead letters back with fresh retries.
- SEC client:
  - One Redis token bucket at 8 req/s (capacity 1) for every process.
  - A 403 or 429 sets a cool-off key (Retry-After or 60 s, at most 120 s) that pauses every process.
  - `User-Agent` from `SEC_USER_AGENT`; timeouts of 5 s to connect and 30 s to read.
  - Gzipped responses cached under their URL path in `SEC_CACHE_DIR`: documents for good, submissions JSON for an hour. The contract tests swap in an in-memory backend. Filings list only status `indexed`, newest first by (`filed_on`, accession number); chunks page in reading order (`char_start`, id), and an unknown chunk id in a cursor is 400; facts page by id, and their `concept` reads `us-gaap:Revenues`.
- GraphQL `/graphql` (either key): `Company`, `Filing`, `Section`, `Chunk`, `FinancialFact`, `Answer`, `Citation`, `Usage`; Relay connections (`edges`, `pageInfo`) for companies, filings, chunks and facts. Resolver errors carry `extensions.code`; unexpected ones are masked.
- Worker: Celery app (late acks, reject on worker lost, prefetch 1, time limits, publisher confirms). It consumes `discover`, `fetch`, `fetch.retry` and `reembed`, and declares the dead-letter queues when ready. `/healthz` and `/readyz` listen on 127.0.0.1:8001 inside the container; readiness pings the worker through RabbitMQ.
- Data: tables `companies` (CIK key, ticker, name, sector), `filings` (accession number unique, `filing_status` enum discovered, fetched, parsed, embedded, indexed, failed), `sections` (item, title, char range), `chunks` (id = sha256 of accession, item and offset; generated English `tsv`; `embedding_v2` vector(768) and its model), `financial_facts` (numeric value, unique per filing, concept, unit and period), `ingest_jobs`, `ingest_job_companies` (discovery status per CIK), `ingest_job_items`, `dead_letters` (one per task id), `eval_runs`. Indexes: HNSW (cosine) on the embedding column, GIN on `tsv`, `(created_at, id)` keyset indexes on the ingest, dead-letter and eval tables. An idempotent seed of 6 companies.
- Migrations: `make migrate` upgrades to head, `make migrate REV=0007` stops at a revision (the dev path). The chain runs 0001-0003, 0007, then the swap 0004-0006, which stays last until the live swap. Every revision runs in its own transaction with `lock_timeout` 5 s (set in `env.py`); indexes are built with `CREATE INDEX CONCURRENTLY` in autocommit blocks. 0004-0006 are the embedding swap (expand, HNSW index, contract), and `docs/migrations.md` is its runbook and the dev path. 0006 refuses to run while any chunk lacks `embedding_v2`.
- Embedding swap: `reembed` (Celery) fills `embedding_v2` in batches of 256 by keyset over chunk id, queues its own next batch, is rate limited to 60 batches a minute, and resumes after a crash. `RETRIEVAL_EMBEDDING_COLUMN` (api setting; code and compose default `embedding_v2`, `.env.example` `embedding` for the dev path) names the column `nearest_chunks` searches. The ORM defers the `embedding_v2` columns, so loading chunks works at 0003.
- Fake data: `make seed-fake` loads 200 companies (CIKs from 9,000,000,000), 2,000 indexed filings, 10,000 sections, 100k chunks and 6,000 facts. Every embedding column the schema has gets random unit vectors. Each company has its own fixed seed, and a rerun skips companies already loaded. Rows go in with psycopg COPY, and the HNSW indexes are dropped and rebuilt once, all in one transaction that locks `chunks`.
- Logs: structlog JSON lines on stdout from the API, the worker, migrations and the seed, including uvicorn, Celery and Alembic records. Each line carries `service`, `level` (threshold from `LOG_LEVEL`) and, during a request, `request_id`. Credential-named fields and the API key value are redacted.
- Compose: `infra/docker-compose.yml` for development; `infra/docker-compose.prod.yml` unpublishes Postgres, RabbitMQ and Redis and adds `restart: unless-stopped` and memory limits (Postgres 1.5 GB). Postgres runs with `shm_size: 256mb` in both, so parallel HNSW builds fit in `/dev/shm`; `make check-parallel-hnsw` checks it on the dev stack. The worker gets `SEC_USER_AGENT` (compose refuses to start without it) and the `sec-cache` volume, and the API gets `AI_ENABLED` and `DAILY_AI_TOKEN_BUDGET`.
- Contracts: `make codegen` exports both contracts and regenerates all four clients, then type-checks the TS client. `make contracts-check` runs codegen and fails if git sees unstaged or untracked changes under `contracts/` or `clients/`. `make contracts-breaking` runs oasdiff (Docker) against `BASE` (default `main`) and fails on breaking changes.
- Web: placeholder Next.js page with `/healthz` and `/readyz`.
- Secrets: gitleaks pre-commit hook, allowlist `.dockerignore`, images run as uid 10001.

## Current Development Status

Steps 1 (scaffolding), 2 (contracts), 3 (data) and 4 (workers: SEC client, discover, fetch, dead letters, backpressure, API limits) done on 2026-10-14. Next: step 4b (parse, chunk, facts and `scripts/seed_real.py`, user decision). Dev runs at revision 0007 (model A) through steps 4b-6; the live embedding swap, with recall@10 before and after, follows step 6 (user decision).

## Known Limitations

All targets are design goals and have not been measured.

The pipeline stops at `fetched`: parse, chunk and facts, and `scripts/seed_real.py` (the 30 companies in `evals/golden-companies.csv`), arrive in step 4b. Their CIKs come from memory and are checked against SEC's `company_tickers.json` in 4b. A job item counts as succeeded once its document is fetched. Company-level discovery failures show in the job status and `dead_letters`, not in the API's failure list, which holds filings only. `filinglens_llm.embed` raises `not_implemented` until step 6, so the `reembed` task can run only in tests (with a fake embedder) until then. Nothing reads `RETRIEVAL_EMBEDDING_COLUMN` outside tests until `LiveBackend.search` lands in step 6; flipping it needs an API restart. `make seed-fake` locks `chunks` while it loads, so it is not for a database that serves traffic. The web `/readyz` equals `/healthz` until the backend-for-frontend lands.

Search and answers (step 6) still return 501; load shedding for in-flight LLM calls also comes in step 6. 500 is not listed in the spec. CI does not exist yet, so `contracts-check` and `contracts-breaking` run only through make until step 7.

## Planned Features

See `docs/todo.md` for the 10-step build plan (8 build steps, review UI, deploy).
