# To-Do

Concise, verifiable tasks. Move items between sections as status changes. Trim old completed items when the list grows large; the activity log keeps the history.

Each step maps to a Claude Code prompt in the design doc. Done when the check after the colon passes.

## Pending

- [ ] (manual) Get free API keys: Google AI Studio (Gemini) and Groq; optional Cloudflare Workers AI token. Put them in `.env`, never in the repo.
- [ ] (manual, before step 7) GitHub repo created; provider keys added as Actions secrets.
- [ ] (manual, before step 10) Vercel and Tailscale accounts created.
- [ ] (manual, now) Fix `API_KEY` on line 34 of `.env`: it holds the command `uv run python -c "import secrets; ..."` instead of its output, so `uv run --env-file .env` (make migrate, make seed) cannot parse the file. Also add `RETRIEVAL_EMBEDDING_COLUMN=embedding` (as in `.env.example`). Then `make migrate REV=0003` and `make seed` (and `make seed-fake` for load tests): the compose Postgres has no tables, so `/v1/companies` returns 500.
- [ ] (manual, before step 4 runs seed_real) Choose the contact details for the SEC User-Agent (AGENTS.md requires them); step 4 adds the setting to `.env`.
- [ ] (manual, before step 10) Replace the example passwords in `.env`, and set both `API_KEY` and `ADMIN_API_KEY` (step 2 appended a random `ADMIN_API_KEY`).
- [ ] 4. Workers: queue job with retries and dead-letter handling, backpressure and crash-recovery tests pass. Includes `create_ingest_job` (idempotent by Idempotency-Key) and `get_ingest_job` in `LiveBackend`. Moved here from step 3 (user decision): the SEC client (shared Redis limiter at 8 req/s, User-Agent, timeouts, raw responses cached on disk) and `scripts/seed_real.py`, which ingests the 30 golden-set companies through the pipeline; reruns and tests never hit SEC. Code runs at revision 0003 (dev path in `docs/migrations.md`): the embed stage writes the column `RETRIEVAL_EMBEDDING_COLUMN` names, with that column's model, so the ingest settings need the flag too.
- [ ] 5. Tests: unit and integration suites green three runs in a row
- [ ] 6. AI: pipeline built, golden dataset v1 created, eval report lists every target with pass or fail. Replace the `search`, `answer` and `stream_answer` stubs in `LiveBackend`; search reads `RETRIEVAL_EMBEDDING_COLUMN` through `filinglens_retrieval.nearest_chunks` and puts the column in the cursor's `index_version`. Implement `filinglens_llm.embed` (local sentence-transformers first), which also makes the `reembed` task run for real. Raise `OverloadedError(retry_after_s=...)` when shedding load. The evals run on model A at revision 0003.
- [ ] Live embedding swap (after step 6; user decision): with dev at 0003, record the model A baseline (`make eval`, recall@10 and MRR@10, golden set version); run 0004, the reembed backfill, 0005 (run `make check-parallel-hnsw` first, then pick a parallel build within the 256 MB `shm_size` or a serial one with more `maintenance_work_mem`, by corpus size; runbook step 3), the catch-up run and the flip to `embedding_v2`; run `make eval` again on the same golden set; record both runs in `eval_runs` and the activity log; then run 0006 in the next release and set `.env.example` to `embedding_v2`. Done when both recall@10 values are recorded and dev is at head. Runbook: `docs/migrations.md`.
- [ ] 7. CI/CD: GitHub Actions for test, build, docker push; actionlint passes; test PR green. CI also runs `make contracts-check` and `make contracts-breaking BASE=origin/main` (fetch main first).
- [ ] 8. Instrumentation: OpenTelemetry traces span services end to end; dashboard and alerts committed; screenshots saved
- [ ] 9. Review UI and demo mode: resolvers, login, backend-for-frontend, demo snapshot shown when the backend is offline; Playwright tests pass. The BFF uses `clients/ts` (`createApiClient`, `executeGraphql`) with `API_KEY` only.
- [ ] 10. Deploy: UI on Vercel, backend on the PC via Tailscale Funnel; phone test passes; 401 without API key; demo mode when the PC is off

## In Progress

None.

## Completed

- [x] 3. Data (2026-10-14): `alembic upgrade head` works from an empty database (tests and the CLI); downgrading the expand step (0004 to 0003) keeps model A data; EXPLAIN shows the HNSW index serving the search query for both embedding columns and after the contract; the reembed task runs in batches of 256, resumes from its cursor and catches up new chunks; `make seed-fake` loads 100k chunks and a rerun inserts nothing; `LiveBackend` pages filings, sections, chunks and facts from Postgres; `make test` green. User decisions: `seed_real.py` and the SEC client moved to step 4; models A and B are bge-small-en-v1.5 (384) and bge-base-en-v1.5 (768); the embedder is a stub until step 6.
- [x] 2. Contracts (2026-10-14): REST v1 and GraphQL contracts exported to `contracts/`; four clients generated cleanly (`make codegen`); `make contracts-check` fails on stale output and passes on a committed tree; `make contracts-breaking` passes against main and fails on a breaking change; the contract test calls every route through the generated Python client against the app served by uvicorn.
- [x] 1. Scaffolding: monorepo layout, docker-compose infra healthy, every service answers /healthz (2026-10-14). The prompt's done-checks all pass: uv sync, lint, typecheck, compose healthy, api /healthz and /readyz, worker connected to RabbitMQ, a missing env var stops startup. Domain models move to step 3 with the schema; the eval harness to step 6.
- [x] Project created from template (2026-10-13).

## Blocked

None.
