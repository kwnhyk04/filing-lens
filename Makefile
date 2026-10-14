# Run from the repo root. Recipes stay shell-neutral: GNU make on Windows uses cmd.exe unless sh.exe
# is on PATH. Tools run as `python -m`, which also works where Windows blocks uv's .exe launchers.
COMPOSE = docker compose --env-file .env -f infra/docker-compose.yml
PY = uv run python -m

.PHONY: dev down test test-int lint typecheck migrate seed codegen eval

dev: ## build and start the stack; returns once every service is healthy
	$(COMPOSE) up -d --build --wait

down: ## stop the stack and keep its volumes
	$(COMPOSE) down

test:
	$(PY) pytest -m "not integration"

test-int: ## needs Docker: Testcontainers starts throwaway Postgres and Redis
	$(PY) pytest -m integration

lint:
	$(PY) ruff check .
	$(PY) ruff format --check .

typecheck:
	$(PY) pyright

migrate:
	uv run --env-file .env python -m alembic upgrade head

seed:
	uv run --env-file .env python -m filinglens_db.seed

codegen: ## export contracts/, then regenerate clients/python and clients/ts from them
	$(PY) filinglens_api.contracts
	$(PY) openapi_python_client generate --path contracts/openapi.json --output-path clients/python --meta uv --overwrite
	npx --yes openapi-typescript@7.13.0 contracts/openapi.json --output clients/ts/openapi.d.ts

eval:
	uv run python evals/harness.py
