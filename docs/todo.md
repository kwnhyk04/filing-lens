# To-Do

Concise, verifiable tasks. Move items between sections as status changes. Trim old completed items when the list grows large; the activity log keeps the history.

Each step maps to a Claude Code prompt in the design doc. Done when the check after the colon passes.

## Pending

- [ ] (manual) Get free API keys: Google AI Studio (Gemini) and Groq; optional Cloudflare Workers AI token. Put them in `.env`, never in the repo.
- [ ] (manual, before step 7) GitHub repo created; provider keys added as Actions secrets.
- [ ] (manual, before step 10) Vercel and Tailscale accounts created.
- [ ] (manual, before step 10) Replace the example passwords in `.env`, and set both `API_KEY` and `ADMIN_API_KEY` (step 2 appended a random `ADMIN_API_KEY`).
- [ ] (manual, optional) `SEC_USER_AGENT` in `.env` holds only an email. SEC asks for a tool or company name plus a contact, such as `FilingLens Jane Doe jane.doe@mail.com`.
- [ ] (manual, optional) Remove the unused Docker volume `filinglens_sec-cache` (`docker volume rm filinglens_sec-cache`); the SEC cache now lives in `.cache/sec`.
- [ ] 5. Tests: unit and integration suites green three runs in a row
- [ ] 6. AI: pipeline built, golden dataset v1 created, eval report lists every target with pass or fail. Replace the `search`, `answer` and `stream_answer` stubs in `LiveBackend`; search reads `RETRIEVAL_EMBEDDING_COLUMN` through `filinglens_retrieval.nearest_chunks` and puts the column in the cursor's `index_version`. Implement `filinglens_llm.embed` (local sentence-transformers first), which also makes the `reembed` task run for real. Raise `OverloadedError(retry_after_s=...)` when shedding load. The evals run on model A at the dev revision (0008, or a newer one before 0004). `get_financial_fact` follows the latest-filed rule in `docs/memory.md` (step 4b).
- [ ] Live embedding swap (after step 6; user decision): with dev on the last revision before 0004 (now 0008), record the model A baseline (`make eval`, recall@10 and MRR@10, golden set version); run 0004, the reembed backfill, 0005 (run `make check-parallel-hnsw` first, then pick a parallel build within the 256 MB `shm_size` or a serial one with more `maintenance_work_mem`, by corpus size; runbook step 3), the catch-up run and the flip to `embedding_v2`; run `make eval` again on the same golden set; record both runs in `eval_runs` and the activity log; then run 0006 in the next release and set `.env.example` to `embedding_v2`. Done when both recall@10 values are recorded and dev is at head. Runbook: `docs/migrations.md`.
- [ ] 7. CI/CD: GitHub Actions for test, build, docker push; actionlint passes; test PR green. CI also runs `make contracts-check` and `make contracts-breaking BASE=origin/main` (fetch main first).
- [ ] 8. Instrumentation: OpenTelemetry traces span services end to end; dashboard and alerts committed; screenshots saved
- [ ] 9. Review UI and demo mode: resolvers, login, backend-for-frontend, demo snapshot shown when the backend is offline; Playwright tests pass. The BFF uses `clients/ts` (`createApiClient`, `executeGraphql`) with `API_KEY` only.
- [ ] 10. Deploy: UI on Vercel, backend on the PC via Tailscale Funnel; phone test passes; 401 without API key; demo mode when the PC is off

## In Progress

None.

## Completed

- [x] 4b. Parse, chunk, facts and `scripts/seed_real.py` (2026-10-15):
  - One live `make seed-real` run left the 30 golden-set 10-Ks parsed and chunked with facts loaded: 11,263 chunks (158 to 938 per 10-K, median 314), 856,438 facts, no required item missing, fiscal year and period from companyfacts for all 30. 91 SEC requests (30 documents) in 32 s.
  - A second run made 0 SEC requests and downloaded 0 documents.
  - "supply chain risk" on Apple's chunks returned only Item 1A chunks.
  - `make test` 85 passed, `make test-int` 21 passed.
  - User decisions: missing items stored and listed; whole companyfacts with the facts key including `cik`; the latest-filed rule for `get_financial_fact`; only a 10-K/A stops the seed; ConocoPhillips replaced ExxonMobil in the golden set (SEC moved XOM to a new holding company that has no 10-K yet).

- [x] Manual setup checked (2026-10-15): `.env` parses with `uv run --env-file .env`; `API_KEY` (43 characters) holds a value, not a command, and differs from `ADMIN_API_KEY`; `RETRIEVAL_EMBEDDING_COLUMN=embedding`; `SEC_USER_AGENT` set with an email; dev database at 0007 with the 6 seeded companies (now at 0008).

- [x] Step 4 fixes (2026-10-15):
  - The SEC limiter fails closed: without Redis, tasks pause and keep their retries. Tested with a worker on a dead Redis.
  - A 403 after one cool-off fails the job with a reason that names SEC_USER_AGENT. Tested with a refused User-Agent: 2 requests, job `failed`.
  - `make test` 68, `make test-int` 19.
- [x] 4. Workers (2026-10-14): integration tests show:
  - 20 worker processes stay at 8 SEC requests a second: the 9th request after any request arrived at least 0.983 s later at the fake server, within a 50 ms jitter allowance.
  - A filing that fails every attempt (1 + 6 retries) lands in `fetch.dlq` and `dead_letters`, then replays.
  - A full fetch queue makes discover back off without losing filings.
  - A killed worker's message is redelivered without duplicate rows.
  
  Ingest jobs are live in `LiveBackend`. Tests cover the API rate limits, the AI budget guard and the 64 KB and 30 s limits. `make test` (68) and `make test-int` (17) are green.
  
  User decisions: discover and fetch only, with parse, chunk, facts and seed_real in 4b; `partially_failed` kept; the 30 companies in `evals/golden-companies.csv`.
- [x] 3. Data (2026-10-14): `alembic upgrade head` works from an empty database (tests and the CLI); downgrading the expand step (0004 to 0003) keeps model A data; EXPLAIN shows the HNSW index serving the search query for both embedding columns and after the contract; the reembed task runs in batches of 256, resumes from its cursor and catches up new chunks; `make seed-fake` loads 100k chunks and a rerun inserts nothing; `LiveBackend` pages filings, sections, chunks and facts from Postgres; `make test` green. User decisions: `seed_real.py` and the SEC client moved to step 4; models A and B are bge-small-en-v1.5 (384) and bge-base-en-v1.5 (768); the embedder is a stub until step 6.
- [x] 2. Contracts (2026-10-14): REST v1 and GraphQL contracts exported to `contracts/`; four clients generated cleanly (`make codegen`); `make contracts-check` fails on stale output and passes on a committed tree; `make contracts-breaking` passes against main and fails on a breaking change; the contract test calls every route through the generated Python client against the app served by uvicorn.
- [x] 1. Scaffolding: monorepo layout, docker-compose infra healthy, every service answers /healthz (2026-10-14). The prompt's done-checks all pass: uv sync, lint, typecheck, compose healthy, api /healthz and /readyz, worker connected to RabbitMQ, a missing env var stops startup. Domain models move to step 3 with the schema; the eval harness to step 6.
- [x] Project created from template (2026-10-13).

## Blocked

None.
