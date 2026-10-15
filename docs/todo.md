# To-Do

Concise, verifiable tasks. Move items between sections as status changes. Trim old completed items when the list grows large; the activity log keeps the history.

Each step maps to a Claude Code prompt in the design doc. Done when the check after the colon passes.

## Pending

- [ ] (manual, before step 7) GitHub repo created; provider keys added as Actions secrets.
- [ ] (manual, before step 10) Vercel and Tailscale accounts created.
- [ ] (manual, before step 10) Replace the example passwords in `.env`, and set both `API_KEY` and `ADMIN_API_KEY` (step 2 appended a random `ADMIN_API_KEY`).
- [ ] (manual, optional) Remove the unused Docker volume `filinglens_sec-cache` (`docker volume rm filinglens_sec-cache`); the SEC cache now lives in `.cache/sec`.
- [ ] 6b. Golden dataset v1, judge calibration and the eval harness; the eval report lists every target with pass or fail. The evals run on model A at the dev revision (0008, or a newer one before 0004), through `LiveBackend` with `allow_fallback=False`, and score numeric exact match with the amount finder from 6a. Calibrate the 6a refusal thresholds there. An eval run needs about 0.7M tokens, close to `DAILY_AI_TOKEN_BUDGET` (1M).
  - Reranker choice (user decision, 2026-10-15): on the dev split only, compare recall@10, MRR@10 and rerank p95 for TinyBERT-L-2 top 50 whole chunks (the 6a default), MiniLM-L-2 top 24 cut to 256 tokens, and MiniLM-L-6 all 100 as the quality ceiling (settings `RERANK_MODEL`, `RERANK_CANDIDATES`, `RERANK_MAX_TOKENS`). Pick the default from those numbers and record the choice and the numbers in `docs/memory.md`. All latencies are on this PC's CPU, which is also the production host.
  - Time to first token (from 6a): textual answers took 2.2-3.8 s in the smoke runs against p95 2.0 s, because the stages run one after another (router, retrieval, then Gemini's first token 1.4-3.0 s after its call). Measure p50 and p95 on the golden set, then propose a fix. Cause and numbers: `docs/context.md`, Known Limitations.
- [ ] Live embedding swap (after step 6; user decision): with dev on the last revision before 0004 (now 0008), record the model A baseline (`make eval`, recall@10 and MRR@10, golden set version); run 0004, the reembed backfill, 0005 (run `make check-parallel-hnsw` first, then pick a parallel build within the 256 MB `shm_size` or a serial one with more `maintenance_work_mem`, by corpus size; runbook step 3), the catch-up run and the flip to `embedding_v2`; run `make eval` again on the same golden set; record both runs in `eval_runs` and the activity log; then run 0006 in the next release and set `.env.example` to `embedding_v2`. Done when both recall@10 values are recorded and dev is at head. Runbook: `docs/migrations.md`.
- [ ] (after step 6) Decide how a company that changes CIK in a restructure is handled (for example a `cik_aliases` table), since `get_financial_fact` looks facts up by CIK. Known case: XOM (Exxon Mobil Corp, CIK 34088, filed the latest 10-K; SEC now lists the ticker under ExxonMobil Holdings Corp, CIK 2115436).
- [ ] 7. CI/CD: GitHub Actions for test, build, docker push; actionlint passes; test PR green. CI also runs `make contracts-check` and `make contracts-breaking BASE=origin/main` (fetch main first).
- [ ] 8. Instrumentation: OpenTelemetry traces span services end to end; dashboard and alerts committed; screenshots saved
- [ ] (before step 9) Chunks from a separate financial section (JPM, CVX, NVDA, PLD, XOM) are labeled with the last item (15 or 16). Detect the MD&A and financial-statement headings inside that section and label those chunks Items 7, 7A and 8, so citations show the right section.
- [ ] 9. Review UI and demo mode: resolvers, login, backend-for-frontend, demo snapshot shown when the backend is offline; Playwright tests pass. The BFF uses `clients/ts` (`createApiClient`, `executeGraphql`) with `API_KEY` only.
- [ ] 10. Deploy: UI on Vercel, backend on the PC via Tailscale Funnel; phone test passes; 401 without API key; demo mode when the PC is off

## In Progress

None.

## Completed

- [x] 6a (2026-10-15). Provider layer, local embeddings, hybrid retrieval, answers with verified citations. Done when `make test` and `make test-int` are green three runs in a row, then a live smoke run with `AI_ENABLED=true` answers a numeric question (fact id and value), a textual one (citations and quotes) and an unanswerable one (refusal), each with tokens, latency per stage and time to first token.
  - [x] Models (user decision, 2026-10-15): `LLM_PRIMARY=gemini:gemini-3.5-flash-lite`, `LLM_ROUTER=groq:openai/gpt-oss-20b`, `LLM_FALLBACK` on NVIDIA NIM. `AI_ENABLED` now defaults to false (it defaulted to true).
  - [x] Providers (`filinglens_llm.providers`): OpenAI-compatible client and Gemini adapter, fallback for the primary and the router (recorded in logs, answer stats and the Redis field `fallbacks`), 402 permanent (503).
  - [x] Local models (`filinglens_llm.local`, `make models`): bge-small/bge-base embedders with the bge query prefix, TinyBERT/MiniLM rerankers, pinned commits in `HF_HOME`, offline in tests and containers. torch pinned below 2.13 (Smart App Control blocks its `torch_python.dll` from 2.13).
  - [x] Embed stage and `embed` worker service: the 30 filings are indexed, 11,263 chunks with bge-small vectors in about 14 min (13.0 chunks/s in the embed container).
  - [x] Retrieval (`filinglens_retrieval.search`, `/v1/search` with `cik` and `fiscal_year`, 409, degraded): warm in the API container embed 15-25 ms, SQL 5-110 ms, rerank 128-182 ms (TinyBERT, 50 candidates).
  - [x] Answers (`filinglens_api.answering`, `filinglens_llm.router`/`answer`/`validate`): routing, facts, retrieval, cited draft streamed, validation, one regeneration, refusals (out of scope, unknown company, time trap, low relevance at a provisional -3.0), in-flight cap. Contract: `Answer.refused` and `warnings`, search filters and 409 (`make contracts-breaking`: none breaking).
  - [x] Tests: unit 211; answering on recorded fixtures (`scripts/record_llm_fixtures.py`, `services/api/tests/fixtures/answers`); integration for search paging, 409 and degraded, `get_financial_fact`, and the pipeline through embed.
  - [x] User decision (2026-10-15): test `deepseek-ai/deepseek-v4.1-flash` and `openai/gpt-oss-20b` on NVIDIA with one real answering call each (same question, 12 retrieved chunks, our schema): schema, every citation through `citation_error`, latency and tokens. Pick the one that passes; if both, deepseek-v4.1-flash. Record the results and date in `docs/memory.md`. Done: neither passed in full; gpt-oss-20b kept (memory.md).
  - [x] Three runs in a row: `make test` 211 passed (18.1, 17.0, 21.2 s), `make test-int` 28 passed (171.2, 178.6, 161.9 s). An earlier run had 2 failures in `test_limits.py`, which assumed AI on by default; fixed.
  - [x] Live smoke run (`make smoke`, 2026-10-15): numeric (fact 37437, 416,161,000,000 USD), textual (quoted citations, all passing validation), fiscal 2027 refused as a time trap; tokens, stage latencies and time to first token in the activity log. Docs updated.
  - [x] Before the commit (user requests, 2026-10-16): torch pinned below 2.13 on Windows only (`sys_platform == 'win32'`), so the Linux images run 2.14.1+cpu (checked in the api and embed containers, search warm 0.19 s); `make test` 211 passed in 17.7 s. gpt-oss-120b probed on NVIDIA: 410, retired on 2026-09-03; gpt-oss-20b stays `LLM_FALLBACK` (memory.md). The first-token miss is a 6b item (context.md, Known Limitations).

- [x] `.env` `SEC_USER_AGENT` names the tool and a contact; its value is now quoted, so `uv run --env-file .env` parses the file again (2026-10-15). `uv run` and the ingest container read the same 35-character value without quote characters.

- [x] 5. Tests (2026-10-15):
  - Three runs each, all green: `make test` 127 passed in 7.9, 8.2 and 8.4 s; `make test-int` 23 passed in 105.2, 104.4 and 105.6 s (pytest's times; wall adds about 2 s). After `parse_amount` gained abbreviations: `make test` 139 passed in 8.4 s (9.9 s wall).
  - Unit: chunker properties (hypothesis), RRF, citation validation, amounts, SecClient timeouts (respx), the network guard. Integration: keyset pages over 100k chunks under concurrent inserts (page size 100, 24 s); the embedding swap 0004-0006 with the API reading in a loop, zero failed reads.
  - User decisions: keep Testcontainers; citations normalized (NFKC, straight quotes, collapsed whitespace) but exact on words and digits; page size 100 with all 100k chunks; `parse_amount` reads K, M, B or bn, and T.

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
