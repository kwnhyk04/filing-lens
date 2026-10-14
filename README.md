# FilingLens

Answers analyst questions over SEC 10-K and 10-Q filings with sentence-level citations, and checks every number against SEC XBRL data.

## Setup

Needs uv, Docker, GNU make, and Node 20.9+ (for `web/` and the TypeScript client).

1. `cp .env.example .env`, then change every password and the API key.
2. `uv sync` installs the Python workspace (Python 3.12).
3. `uv run python -m pre_commit install` turns on the gitleaks pre-commit hook.
4. `make dev` builds the images and starts Postgres, Redis, RabbitMQ, the API and the worker. It returns once all are healthy.
5. `make migrate`, then `make seed`.

## Usage

| Target | What it does |
| --- | --- |
| `make dev` / `make down` | Start the stack and wait until it is healthy / stop it (volumes are kept) |
| `make test` / `make test-int` | Unit tests / integration tests in throwaway containers (needs Docker) |
| `make lint` / `make typecheck` | ruff / pyright (strict for `packages/*`) |
| `make migrate` / `make seed` | Apply Alembic migrations / upsert seed data |
| `make codegen` | Export `contracts/`, then regenerate `clients/python` and `clients/ts` |
| `make eval` | Eval harness (arrives with the AI pipeline) |

- API: `http://127.0.0.1:4100` with `/healthz`, `/readyz` (Postgres, RabbitMQ, Redis) and `/graphql` (send `X-API-Key`).
- Web: `cd web && npm ci && npm run dev`, then open `http://127.0.0.1:3100`.
- Plain `docker compose ...` (for example `docker compose ps`) works from the repo root, because `.env` sets `COMPOSE_FILE`.
- Monitoring: set `COMPOSE_PROFILES=observability` in `.env` for Grafana (3101), Jaeger (16687) and Prometheus (9091). Toxiproxy runs under the `test` profile.
- Production: `docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d` (no published Postgres, RabbitMQ or Redis ports; restart policies; memory limits).
- Logs are JSON lines with a `request_id` (send `X-Request-ID` to set it). Credential fields and the API key are redacted.
- Ports bind to 127.0.0.1 and can be changed in `.env`.

Layout: `services/` (api, ingest), `packages/` (core, db, retrieval, llm, sec_client, telemetry), `contracts/` (exported OpenAPI and GraphQL), `clients/` (generated), `web/`, `evals/`, `infra/`. See `docs/context.md` for the design and `docs/todo.md` for the build plan.
