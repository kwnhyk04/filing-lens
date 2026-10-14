# FilingLens

Answers analyst questions over SEC 10-K and 10-Q filings with sentence-level citations, and checks every number against SEC XBRL data.

## Setup

Needs uv, Docker, GNU make, and Node 20.9+ (for `web/` and the TypeScript client).

1. `cp .env.example .env`, then change every password and both API keys (`API_KEY`, `ADMIN_API_KEY`).
2. `uv sync` installs the Python workspace (Python 3.12).
3. `uv run python -m pre_commit install` turns on the gitleaks pre-commit hook.
4. `make dev` builds the images and starts Postgres, Redis, RabbitMQ, the API and the worker. It returns once all are healthy.
5. `make migrate REV=0003`, then `make seed`. Dev stays at revision 0003 (embedding model A) until the live embedding swap; see `docs/migrations.md`.

## Usage

| Target | What it does |
| --- | --- |
| `make dev` / `make down` | Start the stack and wait until it is healthy / stop it (volumes are kept) |
| `make test` / `make test-int` | Unit tests / integration tests in throwaway containers (needs Docker) |
| `make lint` / `make typecheck` | ruff / pyright (strict for `packages/*`) |
| `make migrate` / `make seed` | Apply Alembic migrations up to `REV` (default head; dev uses `REV=0003`) / upsert seed data |
| `make check-parallel-hnsw` | Dev stack: build a throwaway HNSW index with parallel workers, to confirm postgres's shared memory (`shm_size`) fits it |
| `make seed-fake` | Load and pagination tests only: 200 fake companies, 2,000 filings, 100k chunks with random vectors (about 2.5 minutes at revision 0003; a rerun adds nothing). Locks `chunks` while it loads |
| `make codegen` | Export `contracts/` from the app, then regenerate `clients/python`, `clients/python-graphql` and `clients/ts` |
| `make contracts-check` | Run codegen and fail if `contracts/` or `clients/` changed (commit or stage the output first) |
| `make contracts-breaking` | oasdiff (Docker): fail on breaking OpenAPI changes against `BASE` (default `main`) |
| `make eval` | Eval harness (arrives with the AI pipeline) |

- API: `http://127.0.0.1:4100`. `/healthz` and `/readyz` need no key; everything else needs `X-API-Key`. `API_KEY` opens `/v1/companies`, `/v1/filings`, `/v1/search`, `/v1/answers` (plus `/stream` for Server-Sent Events) and `/graphql`; the admin routes `/v1/ingest-jobs` take only `ADMIN_API_KEY`. The contract is `contracts/openapi.json` (errors are RFC 9457 problems) and `contracts/schema.graphql`. Companies, filings and the GraphQL sections, chunks and facts come from Postgres; ingest jobs, search and answers answer 501 until steps 4 and 6.
- Schema changes and the embedding model swap runbook: `docs/migrations.md`.
- Clients: `clients/python` (REST) and `clients/python-graphql` (GraphQL) are installed in the dev environment; `clients/ts` exports `createApiClient` and `executeGraphql` for server-side TypeScript.
- Web: `cd web && npm ci && npm run dev`, then open `http://127.0.0.1:3100`.
- Plain `docker compose ...` (for example `docker compose ps`) works from the repo root, because `.env` sets `COMPOSE_FILE`.
- Monitoring: set `COMPOSE_PROFILES=observability` in `.env` for Grafana (3101), Jaeger (16687) and Prometheus (9091). Toxiproxy runs under the `test` profile.
- Production: `docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d` (no published Postgres, RabbitMQ or Redis ports; restart policies; memory limits).
- Logs are JSON lines with a `request_id` (send `X-Request-ID` to set it). Credential fields and the API key are redacted.
- Ports bind to 127.0.0.1 and can be changed in `.env`.

Layout: `services/` (api, ingest), `packages/` (core, db, retrieval, llm, sec_client, telemetry), `contracts/` (exported OpenAPI and GraphQL), `clients/` (generated), `web/`, `evals/`, `infra/`. See `docs/context.md` for the design and `docs/todo.md` for the build plan.
