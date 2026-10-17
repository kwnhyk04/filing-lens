# Run from the repo root. Recipes stay shell-neutral: GNU make on Windows uses cmd.exe unless sh.exe
# is on PATH. Tools run as `python -m`, which also works where Windows blocks uv's .exe launchers.
COMPOSE = docker compose --env-file .env -f infra/docker-compose.yml
PY = uv run python -m
RMTREE = uv run python -c "import shutil, sys; shutil.rmtree(sys.argv[1], ignore_errors=True)"
# ariadne-codegen pins graphql-core and ruff versions that clash with the workspace, so it runs in a
# throwaway env; --exclude-newer keeps that env's dependency versions reproducible.
ARIADNE = uv run --isolated --no-project --exclude-newer 2026-10-01T00:00:00Z --with ariadne-codegen==0.19.0 python -m ariadne_codegen
MKDIR = uv run --no-project python -c "import os, sys; os.makedirs(sys.argv[1], exist_ok=True)"
# Tools run from digest-pinned images with the repo mounted read-only and no token or secret.
# git inside them refuses a checkout another user owns (Linux runners), so they trust /repo.
REPO_RO = --mount "type=bind,source=$(CURDIR),target=/repo,readonly" -w /repo
GIT_TRUST = -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo
OASDIFF = docker run --rm $(REPO_RO) $(GIT_TRUST) tufin/oasdiff:v1.32.1@sha256:3b14fe0112e5d1bf862f91ab234a4bcd161a3f399e98f8b0b665ce70857694ac
GITLEAKS = docker run --rm $(REPO_RO) $(GIT_TRUST) ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
ACTIONLINT = docker run --rm $(REPO_RO) rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
# Trivy's actions, setup-trivy tags, binary 0.69.4 and images 0.69.5-0.69.6 were hijacked in March
# 2026 to steal CI secrets: never those, never the actions, and no Docker socket here.
TRIVY = docker run --rm $(REPO_RO) --mount "type=bind,source=$(CURDIR)/.cache/trivy,target=/cache" aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa --cache-dir /cache
TRIVY_ARGS = --scanners vuln --ignore-unfixed --skip-version-check --exit-code 1 --no-progress
# The compose images of Prometheus and the collector, by digest, check the monitoring configs.
PROMTOOL = docker run --rm $(REPO_RO) --entrypoint promtool prom/prometheus:v3.15.0@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e
OTELCOL = docker run --rm $(REPO_RO) -e API_PORT=4100 otel/opentelemetry-collector-contrib:0.162.0@sha256:39923a8e431bd1f57be82411999d389fcfe40857492e4365456d97a4c1f74be6
IMAGE ?= filinglens-api
BASE ?= main
REV ?= head
SUITE ?= all
SPLIT ?= dev
SUBSET ?= full
# Git Bash would rewrite /repo into a Windows path before Docker sees it.
export MSYS_NO_PATHCONV = 1

.PHONY: dev down test test-int lint typecheck migrate seed seed-real seed-fake check-parallel-hnsw codegen contracts-check contracts-breaking eval audit label calibrate models smoke record-fixtures corpus-dump corpus-restore actionlint monitoring-check secrets-scan vuln-scan image-scan

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

corpus-dump: ## dev stack: golden v1's corpus for CI, rows of the public SEC tables only (evals/corpus.py)
	uv run --env-file .env python -m evals.corpus dump

corpus-restore: ## an empty Postgres (CI): fetch the corpus-v1 release asset if missing, check its sha256, restore
	uv run --env-file .env python -m evals.corpus restore

actionlint: ## lint the GitHub Actions workflows (CI runs it too)
	$(ACTIONLINT) -color

monitoring-check: ## Prometheus config and alert rules with their tests, then the collector's config
	$(PROMTOOL) check config infra/prometheus.yml
	$(PROMTOOL) test rules infra/prometheus-alerts.test.yml
	$(OTELCOL) validate --config=infra/otel-collector.yaml

secrets-scan: ## gitleaks over every commit of every ref (CI runs it on each PR; run it before a push)
	$(GITLEAKS) git --redact --log-opts=--all --no-banner /repo

vuln-scan: ## Trivy on each lockfile, dev dependencies included: fail on a high or critical with a fix
	$(MKDIR) .cache/trivy
	$(TRIVY) fs $(TRIVY_ARGS) --include-dev-deps --severity HIGH,CRITICAL uv.lock
	$(TRIVY) fs $(TRIVY_ARGS) --include-dev-deps --severity HIGH,CRITICAL web/package-lock.json
	$(TRIVY) fs $(TRIVY_ARGS) --include-dev-deps --severity HIGH,CRITICAL clients/ts/package-lock.json

image-scan: ## Trivy on IMAGE (default filinglens-api) from a saved tarball: fail on a critical with a fix
	$(MKDIR) .cache/trivy
	$(MKDIR) .cache/images
	docker save $(IMAGE) -o .cache/images/scan.tar
	$(TRIVY) image $(TRIVY_ARGS) --severity CRITICAL --input /repo/.cache/images/scan.tar
