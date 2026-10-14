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
