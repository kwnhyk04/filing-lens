# Run from the repo root. Recipes stay shell-neutral: GNU make on Windows uses cmd.exe unless sh.exe
# is on PATH. Tools run as `python -m`, which also works where Windows blocks uv's .exe launchers.
COMPOSE = docker compose --env-file .env -f infra/docker-compose.yml
PY = uv run python -m
RMTREE = uv run python -c "import shutil, sys; shutil.rmtree(sys.argv[1], ignore_errors=True)"
# ariadne-codegen pins graphql-core and ruff versions that clash with the workspace, so it runs in a
# throwaway env; --exclude-newer keeps that env's dependency versions reproducible.
ARIADNE = uv run --isolated --no-project --exclude-newer 2026-10-01T00:00:00Z --with ariadne-codegen==0.19.0 python -m ariadne_codegen
OASDIFF = docker run --rm --mount "type=bind,source=$(CURDIR),target=/repo,readonly" -w /repo tufin/oasdiff:v1.32.1@sha256:3b14fe0112e5d1bf862f91ab234a4bcd161a3f399e98f8b0b665ce70857694ac
BASE ?= main
REV ?= head
SUITE ?= all
SPLIT ?= dev
SUBSET ?= full
# Git Bash would rewrite /repo into a Windows path before Docker sees it.
export MSYS_NO_PATHCONV = 1

.PHONY: dev down test test-int lint typecheck migrate seed seed-real seed-fake check-parallel-hnsw codegen contracts-check contracts-breaking eval audit label calibrate models smoke record-fixtures

dev: ## build and start the stack; returns once every service is healthy
	$(COMPOSE) up -d --build --wait

down: ## stop the stack and keep its volumes
	$(COMPOSE) down

test: ## unit tests: no Docker, no network
	$(PY) pytest -m unit

test-int: ## needs Docker: Testcontainers starts throwaway Postgres, RabbitMQ and Redis
	$(PY) pytest -m integration

lint:
	$(PY) ruff check .
	$(PY) ruff format --check .

typecheck:
	$(PY) pyright

migrate: ## upgrade to REV (default head); dev stays at REV=0008, before the swap (docs/migrations.md)
	uv run --env-file .env python -m alembic upgrade $(REV)

seed:
	uv run --env-file .env python -m filinglens_db.seed

seed-real: ## live SEC: the latest 10-K of the 30 golden-set companies, through the worker (make dev)
	uv run --env-file .env python scripts/seed_real.py

seed-fake: ## load and pagination tests only: 200 fake companies, 2,000 filings, 100k chunks
	uv run --env-file .env python scripts/seed_fake.py

check-parallel-hnsw: ## dev stack: a parallel HNSW build fits in postgres's shared memory (shm_size)
	$(COMPOSE) exec -T postgres psql -f - < infra/check-parallel-hnsw.sql

codegen: ## export contracts/ from the app, then regenerate every client in clients/ from them
	$(PY) filinglens_api.contracts
	$(PY) strawberry export-schema filinglens_api.graph:schema --output contracts/schema.graphql
	$(PY) openapi_python_client generate --path contracts/openapi.json --output-path clients/python --meta uv --overwrite --config clients/openapi-python-client.yaml
	$(RMTREE) clients/python-graphql/filing_lens_graphql_client
	$(ARIADNE) --config clients/python-graphql/pyproject.toml
	npm --prefix clients/ts ci --ignore-scripts --no-audit --no-fund
	npm --prefix clients/ts run codegen
	npm --prefix clients/ts run typecheck

contracts-check: codegen ## fail if a fresh codegen changes contracts/ or clients/ (staged files count)
	$(PY) filinglens_api.contracts --check

contracts-breaking: ## fail on breaking OpenAPI changes against BASE (default main); needs Docker
	$(OASDIFF) breaking $(BASE):contracts/openapi.json contracts/openapi.json --fail-on ERR

eval: ## golden-set evals: SUITE=retrieval|answer|all SPLIT=dev|test SUBSET=ci|full, flags in ARGS
	uv run --env-file .env python -m evals.harness --suite $(SUITE) --split $(SPLIT) --subset $(SUBSET) $(ARGS)

audit: ## interactive: blind audit of Claude's passage labels, then review of disagreements (resumable)
	uv run python -m evals.label audit

label: ## interactive: label the golden set's candidate passages (resumable)
	uv run python -m evals.label label

calibrate: ## judge calibration: label on screen, or ARGS=export / ARGS=import for an outside labeler
	uv run --env-file .env python -m evals.calibrate $(ARGS)

models: ## once, outside tests: the pinned embedders and rerankers into HF_HOME (on H:)
	uv run python -m filinglens_llm.local

smoke: ## live: three questions through the answer pipeline (calls the models; needs the keys)
	uv run --env-file .env python scripts/smoke_answers.py

record-fixtures: ## live: re-record the model replies the answering tests replay
	uv run --env-file .env python scripts/record_llm_fixtures.py
