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

LLM providers (switchable by env vars): Gemini Flash (free tier) for answers, Groq for the router, Ollama for local runs. Embeddings: local sentence-transformers model by default; the swap series in `docs/migrations.md` moves chunks from BAAI/bge-small-en-v1.5 (384 dimensions, model A) to BAAI/bge-base-en-v1.5 (768, model B). Dev stays on model A at revision 0003 until the live swap after step 6. Deployment: UI on Vercel, backend on the PC via Tailscale Funnel.

Pinned versions live in `uv.lock`, `web/package-lock.json`, `clients/ts/package-lock.json`, `infra/docker-compose.yml` (Postgres 18 with pgvector 0.8.7, RabbitMQ 4.3, Redis 8.8) and the `Makefile` (ariadne-codegen 0.19.0, oasdiff v1.32.1 by image digest). Web: Next.js 16, React 19, TypeScript 5.9 in strict mode.

Local ports (bound to 127.0.0.1; chosen so all three projects can run at once; compose project name `filinglens`). Compose publishes exactly these (verified with `docker compose ps` on 2026-10-14) and reads them from `.env`. `web/` takes 3100 from its npm scripts. The fake SEC server (4110) is not built yet. The worker's probe port (8001) stays inside its container.

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

Built: settings and error taxonomy (`packages/core`), structlog JSON logging with redaction (`packages/telemetry`), async engine, models (with a small pgvector `Vector` type and `chunk_id()`), migrations 0001-0006 and seed (`packages/db`), the vector search query `nearest_chunks` (`packages/retrieval`), an `embed` stub (`packages/llm`), Celery worker with probes (`services/ingest/src/filinglens_ingest/worker.py`) and the `reembed` task (`reembed.py`), fake data seed (`scripts/seed_fake.py`), compose stack with prod override and Dockerfile (`infra/`).

API (`services/api/src/filinglens_api/`): `main.py` (app, probes, request ids, catch-all 500), `routes.py` (REST v1 and key checks), `schemas.py` (pydantic contract models), `problems.py` (RFC 9457 handlers and response docs), `backend.py` (the `Backend` protocol, keyset cursors, `LiveBackend`), `graph.py` (Strawberry schema), `contracts.py` (spec export and `--check`).

Contracts and clients: `contracts/openapi.json` and `contracts/schema.graphql` (generated, committed); `clients/python` (openapi-python-client), `clients/python-graphql` (ariadne-codegen), `clients/ts` (openapi-typescript types, openapi-fetch client, graphql-codegen documents, hand-written `index.ts`); shared GraphQL operations in `clients/operations.graphql`.

Planned: SEC client with shared limiter, Celery pipeline with dead-letter exchange, hybrid retrieval, citation validator, eval harness.

## Implemented Functionality

- Config: each process validates its env vars at startup and exits naming each bad one without echoing values, for example `Invalid configuration: API_KEY: Field required`. Compose also refuses to start without the required `.env` values.
- API keys: `API_KEY` opens every route except the admin routes; `ADMIN_API_KEY` opens every route and is the only key for `POST /v1/ingest-jobs` and `GET /v1/ingest-jobs/{id}`. Both are required, at least 32 characters, must differ, and are read only from the `X-API-Key` header (a key in the URL gets 401). Missing or unknown key: 401 with `WWW-Authenticate: APIKey`; `API_KEY` on an admin route: 403. `/healthz` and `/readyz` need no key. Every response carries `X-Request-ID`.
- REST v1: `POST /v1/ingest-jobs` (202, `Location`, required `Idempotency-Key`), `GET /v1/ingest-jobs/{id}` (status counts plus a page of failures), `GET /v1/companies`, `GET /v1/filings`, `GET /v1/search` (cursor holds score, chunk id and index version), `POST /v1/answers` and `POST /v1/answers/stream` (Server-Sent Events: `delta`, then `completed`, or `failed` mid-stream). Lists use keyset pagination: `limit` at most 100, opaque `cursor`, `next_cursor`.
- Errors: RFC 9457 problems (`application/problem+json`, `type: about:blank`, `code` from the taxonomy). Validation is 422 `validation_failed` with `errors[{detail, pointer}]`; a bad cursor is 400; 429 sends `Retry-After`, `RateLimit-Limit` and `RateLimit-Remaining`; 503 sends `Retry-After`. Unexpected errors are 500 with no detail, logged with the request id.
- Data behind the routes: `LiveBackend` serves companies, filings, sections, chunks and facts from Postgres; ingest jobs, search and answers return 501 `not_implemented` until their build step. The contract tests swap in an in-memory backend. Filings list only status `indexed`, newest first by (`filed_on`, accession number); chunks page in reading order (`char_start`, id), and an unknown chunk id in a cursor is 400; facts page by id, and their `concept` reads `us-gaap:Revenues`.
- GraphQL `/graphql` (either key): `Company`, `Filing`, `Section`, `Chunk`, `FinancialFact`, `Answer`, `Citation`, `Usage`; Relay connections (`edges`, `pageInfo`) for companies, filings, chunks and facts. Resolver errors carry `extensions.code`; unexpected ones are masked.
- Worker: Celery app (late acks, reject on worker lost, prefetch 1, time limits). `/healthz` and `/readyz` listen on 127.0.0.1:8001 inside the container; readiness pings the worker through RabbitMQ.
- Data: tables `companies` (CIK key, ticker, name, sector), `filings` (accession number unique, `filing_status` enum discovered, fetched, parsed, embedded, indexed, failed), `sections` (item, title, char range), `chunks` (id = sha256 of accession, item and offset; generated English `tsv`; `embedding_v2` vector(768) and its model), `financial_facts` (numeric value, unique per filing, concept, unit and period), `ingest_jobs`, `ingest_job_items`, `dead_letters`, `eval_runs`. Indexes: HNSW (cosine) on the embedding column, GIN on `tsv`, `(created_at, id)` keyset indexes on the ingest, dead-letter and eval tables. An idempotent seed of 6 companies.
- Migrations: `make migrate` upgrades to head, `make migrate REV=0003` stops at a revision. Every revision runs in its own transaction with `lock_timeout` 5 s (set in `env.py`); indexes are built with `CREATE INDEX CONCURRENTLY` in autocommit blocks. 0004-0006 are the embedding swap (expand, HNSW index, contract), and `docs/migrations.md` is its runbook and the dev path. 0006 refuses to run while any chunk lacks `embedding_v2`.
- Embedding swap: `reembed` (Celery) fills `embedding_v2` in batches of 256 by keyset over chunk id, queues its own next batch, is rate limited to 60 batches a minute, and resumes after a crash. `RETRIEVAL_EMBEDDING_COLUMN` (api setting; code and compose default `embedding_v2`, `.env.example` `embedding` for the dev path) names the column `nearest_chunks` searches. The ORM defers the `embedding_v2` columns, so loading chunks works at 0003.
- Fake data: `make seed-fake` loads 200 companies (CIKs from 9,000,000,000), 2,000 indexed filings, 10,000 sections, 100k chunks and 6,000 facts. Every embedding column the schema has gets random unit vectors. Each company has its own fixed seed, and a rerun skips companies already loaded. Rows go in with psycopg COPY, and the HNSW indexes are dropped and rebuilt once, all in one transaction that locks `chunks`.
- Logs: structlog JSON lines on stdout from the API, the worker, migrations and the seed, including uvicorn, Celery and Alembic records. Each line carries `service`, `level` (threshold from `LOG_LEVEL`) and, during a request, `request_id`. Credential-named fields and the API key value are redacted.
- Compose: `infra/docker-compose.yml` for development; `infra/docker-compose.prod.yml` unpublishes Postgres, RabbitMQ and Redis and adds `restart: unless-stopped` and memory limits (Postgres 1.5 GB). Postgres runs with `shm_size: 256mb` in both, so parallel HNSW builds fit in `/dev/shm`; `make check-parallel-hnsw` checks it on the dev stack.
- Contracts: `make codegen` exports both contracts and regenerates all four clients, then type-checks the TS client. `make contracts-check` runs codegen and fails if git sees unstaged or untracked changes under `contracts/` or `clients/`. `make contracts-breaking` runs oasdiff (Docker) against `BASE` (default `main`) and fails on breaking changes.
- Web: placeholder Next.js page with `/healthz` and `/readyz`.
- Secrets: gitleaks pre-commit hook, allowlist `.dockerignore`, images run as uid 10001.

## Current Development Status

Steps 1 (scaffolding), 2 (contracts) and 3 (data) done on 2026-10-14. Next: step 4 (workers), which now also builds the SEC client and `scripts/seed_real.py`. Dev runs at revision 0003 (model A) through steps 4-6; the live embedding swap, with recall@10 before and after, follows step 6 (user decision).

## Known Limitations

All targets are design goals and have not been measured.

`sec_client` is empty, and `scripts/seed_real.py` (30 real companies for the golden set, with raw SEC responses cached on disk) moved to step 4, where the pipeline it runs through is built. `filinglens_llm.embed` raises `not_implemented` until step 6, so the `reembed` task can run only in tests (with a fake embedder) until then. Nothing reads `RETRIEVAL_EMBEDDING_COLUMN` outside tests until `LiveBackend.search` lands in step 6; flipping it needs an API restart. `make seed-fake` locks `chunks` while it loads, so it is not for a database that serves traffic. The web `/readyz` equals `/healthz` until the backend-for-frontend lands.

Ingest jobs (step 4), search and answers (step 6) still return 501. Nothing raises 429 or 503 yet: the headers are documented and emitted from `RateLimitedError` and `OverloadedError`, but the rate limiter and load shedding come later. 500 is not listed in the spec. CI does not exist yet, so `contracts-check` and `contracts-breaking` run only through make until step 7.

## Planned Features

See `docs/todo.md` for the 10-step build plan (8 build steps, review UI, deploy).
