# FilingLens

Answers analyst questions over SEC 10-K and 10-Q filings with sentence-level citations, and checks every number against SEC XBRL data.

## Setup

Needs uv, Docker, GNU make, and Node 20.9+ (for `web/` and the TypeScript client).

1. `cp .env.example .env`, then change every password and both API keys (`API_KEY`, `ADMIN_API_KEY`), and set `SEC_USER_AGENT` to your tool name and contact email (SEC requires one; compose refuses to start without it).
2. `uv sync` installs the Python workspace (Python 3.12).
3. `uv run python -m pre_commit install` turns on the gitleaks pre-commit hook.
4. `make models` once: it fetches the pinned embedders and rerankers into `HF_HOME` (set it to a folder on the data disk first; here `H:\.cache\huggingface`). Tests and containers load them offline from there.
5. `make dev` builds the images and starts Postgres, Redis, RabbitMQ, the API, the ingest worker and the embed worker. It returns once all are healthy.
6. `make migrate REV=0008`, then `make seed`. Dev stays at revision 0008, the last one before the embedding swap (model A), until the live swap; see `docs/migrations.md`.
7. Optional, live SEC: `make seed-real` ingests the latest 10-K of the 30 golden-set companies (`evals/golden-companies.csv`) through the workers, embeds and indexes them, with their XBRL facts.
8. Optional, answers: set `GEMINI_API_KEY`, `GROQ_API_KEY` and `NVIDIA_API_KEY` in `.env` and `AI_ENABLED=true` (off by default; with it on, startup refuses a missing key).

## Usage

| Target | What it does |
| --- | --- |
| `make dev` / `make down` | Start the stack and wait until it is healthy / stop it (volumes are kept) |
| `make test` / `make test-int` | Unit tests (no Docker, no network; about 10 s) / integration tests in throwaway Postgres, RabbitMQ and Redis containers (needs Docker; about 2 minutes). Tests never reach SEC or a model provider: `network_guard.py` refuses every host but this machine |
| `make lint` / `make typecheck` | ruff / pyright (strict for `packages/*`) |
| `make migrate` / `make seed` | Apply Alembic migrations up to `REV` (default head; dev uses `REV=0008`) / upsert seed data |
| `make seed-real` | Live SEC, needs `make dev`: check the golden-set CIKs and tickers against SEC, then ingest each company's latest 10-K and its XBRL facts through the worker; prints filings per status, chunks per filing, facts per company and the SEC requests made. Do not run it, or queue ingest jobs, until golden set v1's test run is done: new filings (Apple's FY2026 10-K lands around 2026-10-30) change the corpus, and the eval's drift check then stops every run |
| `make models` | Once, outside tests: fetch the pinned local models into `HF_HOME` |
| `make smoke` | Live models: three questions (numeric, textual, unanswerable) through the answer pipeline; prints answers, citations, tokens, stage latencies and time to first token |
| `make record-fixtures` | Live models: re-record the replies the answering tests replay (`services/api/tests/fixtures/answers`) |
| `make check-parallel-hnsw` | Dev stack: build a throwaway HNSW index with parallel workers, to confirm postgres's shared memory (`shm_size`) fits it |
| `make seed-fake` | Load and pagination tests only: 200 fake companies, 2,000 filings, 100k chunks with random vectors (about 2.5 minutes at the dev revision; a rerun adds nothing). Locks `chunks` while it loads |
| `make codegen` | Export `contracts/` from the app, then regenerate `clients/python`, `clients/python-graphql` and `clients/ts` |
| `make contracts-check` | Run codegen and fail if `contracts/` or `clients/` changed (commit or stage the output first) |
| `make contracts-breaking` | oasdiff (Docker): fail on breaking OpenAPI changes against `BASE` (default `main`) |
| `make eval` | Golden-set eval, needs `make dev`: `SUITE=retrieval\|answer\|all SPLIT=dev\|test SUBSET=full\|ci`. `ARGS` takes `--tag=NAME` (calls the answer models live once under NAME; earlier replies stay cached), `--primary-tag=NAME` (the same for the answer model only, with router replies from the cache), `--min-relevance=X`, `--thinking=default` and `--no-judge`. Runs check the floors in `evals/thresholds.json` but never write them; `uv run python -m evals.harness --set-floors REPORT` writes the floors the rule gives a saved report's measured values, latency included, keeping only tighter ones. The answer suite calls the live models and prints a quota estimate first. Replies are cached, so a run stopped by a quota (exit 2) resumes when rerun. Reports go to `evals/reports/`. Exits 1 on a broken floor and 3 when the golden set or the corpus changed since the freeze |
| `make audit` / `make label` | Interactive passage labeling for the golden set (resumable). Both refuse once the set is frozen |
| `make calibrate` | Judge calibration. On screen you label sampled answer sentences against their cited sources. `ARGS=export` writes the sample for an outside labeler, and `ARGS=import` scores its labels from `claude_labels.jsonl`. The judge then scores the same sentences, Cohen's kappa goes to `evals/calibration/v1/result.json` with the labeler named, and judge metrics count only at 0.7 or more. A first argument `followup` (`ARGS="followup export"`) works on the second sample in `evals/calibration/v1-followup/`: natural sentences that fail the validator, from the fallback-model runs |

- API: `http://127.0.0.1:4100`. `/healthz` and `/readyz` need no key; everything else needs `X-API-Key`. `API_KEY` opens `/v1/companies`, `/v1/filings`, `/v1/search`, `/v1/answers` (plus `/stream` for Server-Sent Events) and `/graphql`; the admin routes `/v1/ingest-jobs` take only `ADMIN_API_KEY`. The contract is `contracts/openapi.json` (errors are RFC 9457 problems) and `contracts/schema.graphql`. Companies, filings and the GraphQL sections, chunks and facts come from Postgres. An ingest job discovers each company's 10-K and 10-Q filings on EDGAR, fetches them into the SEC cache (`.cache/sec`, shared by the worker and host runs), splits them into item sections and token-aware chunks, embeds the chunks on the `embed` worker, and loads the company's XBRL facts. Search and answers run on that data (answers need `AI_ENABLED=true`).
- Limits: each key gets 60 requests a minute, and 10 answers a minute (429 with `Retry-After` and `RateLimit-*`). Bodies are capped at 64 KB (413) and answers at 30 s (502). Answers return 503 `ai_unavailable` once the day's LLM tokens (UTC) reach `DAILY_AI_TOKEN_BUDGET`, or when `AI_ENABLED=false` (the default), and 503 `overloaded` past `LLM_MAX_INFLIGHT` answers in progress.
- Dead letters: a task that keeps failing ends in its dead-letter queue (`discover.dlq`, `fetch.dlq`, `parse.dlq`, `chunk.dlq`, `embed.dlq` or `facts.dlq`) and the `dead_letters` table; a filing parse cannot split fails with the reason in its job item. `docker compose exec ingest python -m filinglens_ingest.replay --queue fetch.dlq --limit 100` moves such messages back to their queue with fresh retries. If SEC still answers 403 after a cool-off, every SEC request stops and the job's filings fail with that reason: fix `SEC_USER_AGENT`, restart the worker (`docker compose up -d ingest`), then replay. Without Redis, workers pause instead of sending unlimited requests.
- Schema changes and the embedding model swap runbook: `docs/migrations.md`.
- Clients: `clients/python` (REST) and `clients/python-graphql` (GraphQL) are installed in the dev environment; `clients/ts` exports `createApiClient` and `executeGraphql` for server-side TypeScript.
- Web: `cd web && npm ci && npm run dev`, then open `http://127.0.0.1:3100`.
- Plain `docker compose ...` (for example `docker compose ps`) works from the repo root, because `.env` sets `COMPOSE_FILE`.
- Monitoring: set `COMPOSE_PROFILES=observability` in `.env` for Grafana (3101), Jaeger (16687) and Prometheus (9091). Toxiproxy runs under the `test` profile.
- Production: `docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d` (no published Postgres, RabbitMQ or Redis ports; restart policies; memory limits).
- Logs are JSON lines with a `request_id` (send `X-Request-ID` to set it). Credential fields and the API key are redacted.
- Ports bind to 127.0.0.1 and can be changed in `.env`.

## Evaluation

Golden set v1 (`evals/golden/v1`, frozen 2026-10-16) holds 100 questions over the 30 companies' latest 10-Ks. How it was built and labeled is in `evals/eval-card.md`.

- Textual gold is AI-labeled, spot-checked by a non-expert. Claude labeled every pooled passage.
- The human check was a fast spot-check by a non-expert, which cannot validate the labels on its own. The passage labels are not human-verified.
- Blind agreement on 79 passages was 49.4%, Cohen's kappa 0.10 (95% CI -0.07 to 0.26), which is not distinguishable from chance.
- The human then made the final call on the 40 disagreements and kept Claude's label on 37. That review showed Claude's reason, so it was not independent.
- Later, after reading the passage text, the human corrected 2 of their 3 overrides back to not gold. The final key now differs from Claude's labels on one passage.
- The judge behind citation precision and faithfulness (gpt-oss-120b) is calibrated against labels by Claude, a different and stronger model than the judge, not by a human. On 29 sentences it agreed 93.1%, Cohen's kappa 0.84 (95% CI 0.59 to 1.00), so those metrics count. Every negative in the sample was constructed, so how well the judge catches real unsupported sentences is untested.
- Time to first token misses its target (p50 1.0 s, p95 2.0 s) on the free tiers:
  - Gemini's own first token drifted from p50 0.97 s to 3.37 s within one day (2026-10-16, the same dev questions).
  - The router and retrieval add about 1 s before Gemini starts, so 1.0 s isn't reachable on free tiers with the stages in sequence.
  - Starting the search while the router runs, and keeping it only when the router agrees, cut the time before Gemini starts by a median 268 ms where it applied (18 of 28 dev questions that searched). Details are in `evals/eval-card.md`.
- While golden v1 is in use, don't run `make seed-real` or queue ingest jobs (see `make seed-real` above).

Layout: `services/` (api, ingest), `packages/` (core, db, retrieval, llm, sec_client, telemetry), `contracts/` (exported OpenAPI and GraphQL), `clients/` (generated), `web/`, `evals/`, `infra/`. See `docs/context.md` for the design and `docs/todo.md` for the build plan.
