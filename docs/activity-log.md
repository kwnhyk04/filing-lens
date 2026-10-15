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

### 2026-10-16: Before the 6a commit: Windows-only torch pin, gpt-oss-120b probe, first-token miss recorded

- Changes:
  - `packages/llm/pyproject.toml`: torch `>=2.12.0,<2.13` for `sys_platform == 'win32'` only, `>=2.12.0` elsewhere (user request). `uv lock --upgrade-package torch` changed only torch: Linux from 2.12.1+cpu to 2.14.1+cpu; Windows stays at 2.12.1, and uv resolved macOS to 2.12.1 too.
  - NVIDIA probe of openai/gpt-oss-120b (user request; the same answer call as the two-model test, gpt-oss-20b run again beside it): 410 Gone, end of life 2026-09-03, absent from the key's model list. gpt-oss-20b stays `LLM_FALLBACK`; its second run passed the format and the router schema, with 2 of 6 quotes passing `citation_error` (memory.md).
  - Docs: the first-token miss with its cause in context.md (Known Limitations) and as a 6b item in todo.md; a pitfall for retired NVIDIA models (a 410 ends in 502). Stale 6a lines fixed: context.md components, usage recording and status; README's 501 note and its dead-letter queues (`embed.dlq`).
- Files: packages/llm/pyproject.toml, uv.lock, README.md, docs/context.md, docs/memory.md, docs/todo.md, docs/activity-log.md
- Validation:
  - `make test`: 211 passed in 17.67 s.
  - `make dev` rebuilt the images; all six services healthy. The api and embed containers run torch 2.14.1+cpu (sentence-transformers 6.1.0). A search through the API ("supply chain risk", Apple): cold 6.03 s (model load), warm 0.19 s (embed 14 ms, SQL 10 ms, load 4 ms, rerank 161 ms), not degraded, top 3 hits from Item 1A.
  - `make test-int` not rerun: it runs on the host, where torch stays at 2.12.1.
- Outstanding: step 6b. A retired `LLM_FALLBACK` would end answers whose primary fails in 502 rather than 503 (memory.md).

### 2026-10-15: Step 6a: providers, local models, embed stage, hybrid search, answers

- Changes:
  - User decisions: Gemini `gemini-3.5-flash-lite` answers, Groq `openai/gpt-oss-20b` routes, NVIDIA NIM is the fallback (model chosen by a two-model test, pending); NVIDIA 402 is permanent (503); a failed router call routes with the fallback. Reranker: TinyBERT-L-2 over the fused top 50, whole chunks, after MiniLM-L-6 over 100 missed the target (p95 3,235 ms on this CPU); `RERANK_MODEL`, `RERANK_CANDIDATES`, `RERANK_MAX_TOKENS` are settings for 6b to tune.
  - `filinglens_llm`: `local` (pinned embedders and rerankers, bge query prefix, `make models`), `providers` (OpenAI-compatible client, Gemini adapter on google-genai with the key only in `x-goog-api-key`), `router` (strict JSON schema, metric table), `answer` (reply format with source-id markers renumbered 1, 2..., stream filter), `validate` (amount finder, per-sentence check), `budget.record_fallback`.
  - `filinglens_retrieval`: scoped vector and full-text candidates, RRF, rerank with a timeout (degraded), `facts.get_financial_fact` with the latest-filed rule.
  - Ingest: `embed` task and queue (`embed.dlq`), statuses parsed, embedded, indexed (facts indexes filings embedded before their fiscal year was known); job items succeed at embed; a separate `embed` compose service (`-Q embed,reembed -c 1`). `ingest` now consumes the other queues only.
  - API: `LiveBackend.search` (keyset over reranked hits, 409 on another index, a degraded cursor keeps the fused order), `answering.Answerer` (router, facts, retrieval, streamed draft, validation, one regeneration, refusals, fallback, in-flight cap), `AI_ENABLED` default false, contract additions (`Answer.refused`, `warnings`, search filters, 409).
  - Dependencies: sentence-transformers 6.1, torch 2.12.1 (pinned below 2.13: Smart App Control blocks `torch_python.dll` in 2.13 and 2.14; the CPU wheel index for Linux images), google-genai 2.31. Images about 2.1 GB.
  - `.env` line 46 (`SEC_USER_AGENT`) quoted; `uv run` and compose read the same 35-character value.
- Files: packages/core (settings, errors, queues, tests), packages/llm (local, providers, router, answer, validate, budget, tests), packages/retrieval (search, facts, tests), services/api (answering, backend, main, routes, schemas, graph, problems, tests, fixtures), services/ingest (pipeline, worker, tests), scripts (seed_real, record_llm_fixtures, smoke_answers), infra (compose, prod override), conftest.py, Makefile, .env.example, pyproject files, uv.lock, contracts/, clients/, docs/todo.md
- Validation so far:
  - Keys: `GEMINI_API_KEY` (AQ.) and `GROQ_API_KEY` listed models with 200 (2026-10-15 07:35 UTC); Groq headers: 1,000 requests/day, 8,000 tokens/min.
  - Embedding: `make seed-real` carried the 30 parsed filings through embed (61 SEC JSON requests, 0 documents): 11,263 chunks, 13.0 chunks/s in the embed container (8 torch threads). The first run failed every filing at the final status update (a CASE of untyped parameters for the enum column); fixed, `embed.dlq` replayed, all 30 indexed, 30 jobs succeeded.
  - Search in the API container (warm): embed 15-25 ms, SQL 5-110 ms, load 3-5 ms, rerank 128-182 ms; on-topic top scores 0.7-9.4, off-topic -10.6 and -10.9.
  - Recorded answers: numeric (fact cited, first token 1.9 s), textual (chunks quoted), out of scope and time trap refused.
  - `make contracts-breaking`: no breaking changes. A first `make test-int` had 2 failures (`test_limits.py` assumed AI on by default); fixed.
  - Three runs in a row: `make test` 211 passed in 18.1, 17.0 and 21.2 s; `make test-int` 28 passed in 171.2, 178.6 and 161.9 s. Afterwards two small changes (the smoke script's printing; facts shown in fixed point instead of 4.1616100E+11 in the prompt and the citation quote), then `make test` 211 passed again.
  - NVIDIA two-model test (user rule; numbers in memory.md): deepseek-v4.1-flash failed the format and the router schema (first token at 50.6 s); gpt-oss-20b passed both, with 2 of 5 quotes passing `citation_error`. gpt-oss-20b kept.
  - Live smoke run (`make smoke`, AI on, models loaded first; final run after the fixed-point change):
    - Numeric, "What was Apple's total revenue in fiscal 2025?": route numeric (revenue, 2025, AAPL); fact 37437, 416,161,000,000 USD, cited [1]; 963 in / 126 out tokens; route 675 ms, facts 46 ms, generate 1,405 ms, total 2,127 ms; first token 1,978 ms.
    - Textual, "What supply chain risks does Apple describe in its latest annual report?": route textual (AAPL); no warnings, so every quote passed `citation_error` (the first run printed its 6 citations with their quotes); 5,263 in / 586 out; route 531 ms, retrieve 269 ms (embed 38, SQL 17, load 13, rerank 171), generate 4,961 ms, total 5,767 ms; first token 3,831 ms (2,172 ms on the first run).
    - Unanswerable, "What was Apple's revenue in fiscal 2027?": refused, "Apple Inc. (AAPL) has filed no 10-K for fiscal 2027; its latest is fiscal 2025."; router only, 621 in / 62 out; total 727 ms.
- Outstanding: step 6b (golden set, judge, eval harness; reranker and refusal-threshold choices on the dev split). The textual first token (2.2-3.8 s) misses the p95 2.0 s target: the router (about 0.55 s) and Gemini's first token dominate.

### 2026-10-15: Step 5: tests (markers, network guard, property tests, load tests)

- Changes:
  - Setup: dev dependencies pytest-asyncio 1.4.0, respx 0.23.1 and hypothesis 6.155.7 (pinned below 6.156, whose Rust extension Application Control blocks). Markers `unit` (the root conftest adds it to every test without another marker), `integration` and `e2e`; `make test` runs `-m unit`. Integration tests keep Testcontainers (user decision).
  - `network_guard.py`: a lookup of any host but this machine raises at once, in pytest and in the worker and client processes that tests start.
  - Unit suite from 33.8 s to about 8 s, test-side only: dead dependencies at 0.0.0.0:1 (a closed 127.0.0.1 port takes 2 s to refuse on Windows), the production JSON log format in tests (rich tracebacks took 3.8 s for one 500), one uvicorn per contract-test module.
  - Pure functions for step 6: `filinglens_retrieval.reciprocal_rank_fusion` (k = 60, exact sums, ties by id) and `filinglens_llm.validate`: `citation_error` (quote and chunk normalized the same way, exact on words and digits; user decision), `parse_amount` (scale words, K/M/B/bn/T, accounting negatives, table scales; user request) and `amounts_match` (0.5%).
  - Tests: a chunker property test (hypothesis), RRF, citations, amounts, SecClient timeouts and headers (respx), the guard; integration tests for keyset pages over 100k chunks under concurrent inserts and for the embedding swap under API reads.
  - Todo: the search-cursor 409 and reranker-timeout tests, the Hugging Face offline note and the amount finder for answer text went into step 6; new items for CIK changes (after step 6) and financial-section headings (before step 9). AGENTS.md now says chunks are keyed by sha256(accession + section + offset).
- Files: AGENTS.md, Makefile, README.md, pyproject.toml, uv.lock, conftest.py, network_guard.py, packages/retrieval (src, tests), packages/llm (validate.py, tests), packages/sec_client/tests, services/api/tests (conftest.py, test_under_load.py), services/ingest/tests (run_worker.py, test_chunking.py, test_pipeline.py, test_probes.py), docs/*
- Validation:
  - `ruff check`, `ruff format --check` and pyright clean.
  - Three runs each: `make test` 127 passed in 7.86, 8.17 and 8.44 s; `make test-int` 23 passed in 105.21, 104.42 and 105.58 s (pytest's times; wall adds about 2 s). Before: 85 unit tests in 33.8 s, 21 integration tests in 82.7 s.
  - After the abbreviations: `make test` 139 passed in 8.42 s (9.9 s wall).
  - The keyset test runs at page size 100 with all 100k chunks in 24 s. With `>=` in place of `>` in `list_chunks` it fails (103,641 chunks returned, 102,605 distinct).
- Outstanding: step 6 builds the amount finder for answer text, search with the 409 cursor check, and the reranker timeout test.

### 2026-10-15: Step 4b: parse, chunk, XBRL facts and seed_real

- Changes:
  - New Celery tasks after fetch, all idempotent with the fetch task's retry, pause and dead-letter rules and their own dead-letter queues:
    - parse: inline XBRL HTML to text, item sections found by heading, the table of contents skipped by item order;
    - chunk: at most 384 bge-small tokens with 64 overlapping, using the model's vendored tokenizer through `tokenizers` (new dependency);
    - facts: whole companyfacts per company, plus each filing's fiscal year and period and their source.
  - Migration 0008 (dev now at 0008): `filings.fiscal_source` and `missing_items`, `sections.text`, `financial_facts.filed_on`, and the facts key with `cik` replacing the old one.
  - `SecClient` gained `companyfacts()`, `company_tickers()` and a per-kind request count in Redis.
  - The SEC cache is now a bind mount of the repo's `.cache/sec`, shared with host runs (`SEC_CACHE_DIR`).
  - `scripts/seed_real.py` (`make seed-real`).
  - User decisions: missing items stored and listed, with only a filing that has no required item failing; whole companyfacts; the `get_financial_fact` latest-filed rule recorded in memory.md; a company with only a 10-K/A stops the seed; XOM replaced by COP in the golden set after SEC moved the XOM ticker to a new holding company.
- Files: packages/sec_client, packages/core (queues.py), packages/db (models.py, migrations 0004 and 0008), services/ingest (pipeline.py, parsing.py, chunking.py, companyfacts.py, worker.py, tokenizer JSON, pyproject.toml, tests and fixtures), services/api/tests/test_app.py, scripts/seed_real.py, evals/golden-companies.csv, infra/docker-compose.yml, Makefile, .env.example, .gitignore, uv.lock, README.md, docs/*
- Validation:
  - Survey before the seed: the parser found every required item in the latest 10-K of each golden-set company (all 30, XOM included), in at most 2.1 s per document.
  - `make test` 85 passed. `make test-int` 21 passed, including `alembic check`, the swap from 0008, facts loaded twice (28 rows both times, fiscal year from companyfacts, fallback for a filing it lacks), and an unparseable filing failing only its own item with a rerun that downloads no document.
  - First `make seed-real` run: 30 jobs succeeded, 30 filings parsed, no required item missing. Chunks per 10-K: min 158, median 314, max 938; 11,263 in all. 856,438 facts. 91 SEC requests, 30 of them documents. 32 s.
  - Second run: 0 SEC requests, 0 documents downloaded, no rows added (6 s).
  - "supply chain risk" on Apple's chunks matched 5 chunks, all in Item 1A.
  - EXPLAIN of the latest-filed facts lookup used `uq_financial_facts_cik`.
- Outstanding: the old `filinglens_sec-cache` Docker volume is unused (not removed). Content in a separate financial section lands under the last item (known limit in memory.md).

### 2026-10-15: SEC limiter fails closed; a 403 after a cool-off fails the job

- Changes (user request):
  - Fails closed: without Redis, `SecClient` raises `LimiterUnavailableError` before any request. fetch and discover then send themselves again after a jittered 30 s pause, with the same task id and retry count, so an outage dead-letters nothing.
  - Attempts: `attempts` now counts tries that ran (a pause or a try killed mid-request does not).
  - Refusals: a 403 sets a strike beside its cool-off, and a 403 after that cool-off is a refusal. The reason goes to `sec:refused`, and every SEC call fails at once with `SecRefusedError` (not retried). The job's filings fail with the reason, which names SEC_USER_AGENT, and the job ends `failed`. A success clears the strike, a 429 always only cools off, and the worker clears the refusal on start.
- Files: packages/sec_client/src/filinglens_sec_client/__init__.py, services/ingest/src/filinglens_ingest (pipeline.py, worker.py), services/ingest/tests (test_pipeline.py, run_worker.py), README.md, docs/*
- Validation:
  - `make lint` and `make typecheck` clean. `make test`: 68 passed. `make test-int`: 19 passed.
  - Redis down: a worker on a dead Redis port paused the fetch more than 7 times, with no request to the fake SEC, no attempt, nothing dead-lettered and an empty `fetch.dlq`. Then a worker with Redis fetched it: 1 attempt, job `succeeded`.
  - Refused User-Agent: two filings answered 403 by every request. SEC saw exactly 2 requests (the 403 that cooled off and the 403 after it), and both filings failed with `SecRefusedError` naming SEC_USER_AGENT. The job was `failed` within seconds.
  - Client level: a 403, then a success, then a 403 is a throttle; a 403 after a cool-off is a refusal, and later calls fail without a request.
- Outstanding: None new.

### 2026-10-14: Step 4 workers (SEC client, discover and fetch, dead letters, backpressure, API limits)

- Changes:
  - Scope (user decisions): step 4 builds discover and fetch; parse, chunk, facts and `scripts/seed_real.py` move to a new step 4b; the job status `partially_failed` stays as the prompt's `completed_with_errors`; the 30 golden-set companies are an editable `evals/golden-companies.csv`.
  - `packages/sec_client`: the Redis token bucket (one Lua script on Redis's clock, 8 req/s, capacity 1) shared by every process; a cool-off key that pauses every process after a 403 or 429; the User-Agent from `SEC_USER_AGENT` (required, placeholder refused); 5 s connect and 30 s read timeouts; a gzipped disk cache.
  - `filinglens_ingest.pipeline`:
    - `discover` walks the submissions JSON and its older files one page at a time, skipping files older than the job's `since`.
    - `fetch` follows the prompt's settings, with retries on the unbounded `fetch.retry` queue. On final failure it writes a `dead_letters` row, marks the filing and item failed, and raises `Reject(requeue=False)`.
    - Queues come from `filinglens_core.queues`: dead-letter exchange `filinglens.dlx`, `fetch` limited to 10,000 with reject-publish. Publisher confirms are on, and discover queues itself again with backoff when a fetch publish is nacked.
  - `python -m filinglens_ingest.replay`.
  - Revision 0007 adds `ingest_job_companies`, so a job finishes once discovery and all its filings are done. 0007 slots in between 0003 and 0004, so the swap stays last and dev moves to `REV=0007`.
  - `LiveBackend` creates ingest jobs (idempotent; it queues discover with confirms) and reports them (counts plus a keyset page of failures).
  - API limits:
    - Redis token buckets per key: 60/min everywhere (GraphQL included), plus 10/min shared by both answers routes.
    - The AI switch and daily token budget (`filinglens_llm.budget`), which answer 503 `ai_unavailable`.
    - 413 over 64 KB, chunked bodies included.
    - A 30 s answer limit (502).
  - `TransientError` is the new base of the retryable errors.
  - Compose passes `SEC_USER_AGENT` and mounts a `sec-cache` volume for the worker, and passes `AI_ENABLED` and `DAILY_AI_TOKEN_BUDGET` to the API.
- Files: packages/core (errors.py, settings.py, queues.py, ratelimit.py, tests), packages/sec_client, packages/llm (budget.py, pyproject), packages/db (models.py, versions/0007_ingest_job_companies.py, 0004 parent), services/ingest (pipeline.py, topology.py, replay.py, worker.py, tests/test_pipeline.py, tests/run_worker.py, test_probes.py, test_embedding_swap.py), services/api (limits.py, backend.py, routes.py, main.py, problems.py, tests), contracts/openapi.json, clients/python, clients/ts, infra (docker-compose.yml, Dockerfile), .env.example, Makefile, evals/golden-companies.csv, pyproject files, uv.lock, README.md, docs/*
- Validation:
  - `make lint` and `make typecheck` clean. `make test`: 68 passed. `make test-int`: 17 passed.
  - The four done checks:
    1. 20 processes x 4 requests through the shared bucket. Over three measuring runs, the 9th request after any request arrived at least 0.983 s later at the fake server: ~16 ms of arrival jitter, against a 50 ms allowance in the test. Throughput was 7.9 req/s.
    2. A filing answering 503 every time was requested 7 times (first attempt plus `max_retries=6`), then landed in `fetch.dlq` (`x-death` reason rejected) and `dead_letters`, with the item failed after 7 attempts and the job `failed`. Replay then fetched it, and the job turned `succeeded`.
    3. With `fetch` at 10,000 messages, discover logged its back-off and left 30 items pending while the queue stayed at the limit. After a purge it queued all 50 filings of both pages exactly once. It never requested the older file that predates `since`.
    4. A worker killed mid-download had its message requeued and finished by a second worker: one row per filing, item and company, no dead letter, attempts 2.
  - Also covered: the cool-off pauses a second client; the cache serves repeat reads; the API's ingest jobs are idempotent, 422 on a reused key, and page their failures; 429 headers and per-key buckets; 503 at the budget and with `AI_ENABLED=false`; 413 with and without a length; the 502 timeout for answers and their stream.
  - `make codegen` regenerated `contracts/` and the clients (413 and 503 docs). `make contracts-breaking`: no breaking changes.
  - The api and ingest images build. A one-off ingest container (uid 10001) wrote to the new `sec-cache` volume and loaded the queues, confirms and routes. Compose refuses to start without `SEC_USER_AGENT`.
- Outstanding: the user's `.env` needs `SEC_USER_AGENT` before `make dev` (compose stops without it). Step 4b: parse, chunk, facts and `seed_real.py`. Nothing records LLM usage until step 6.

### 2026-10-14: Shared memory for parallel HNSW builds

- Changes: Postgres gets `shm_size: 256mb` in `infra/docker-compose.yml` and `infra/docker-compose.prod.yml`, and its prod memory limit rises from 1G to 1.5G (user decision). Compose also sets `PGUSER` and `PGDATABASE` for psql inside the container. New `make check-parallel-hnsw` runs `infra/check-parallel-hnsw.sql` on the dev stack: a throwaway database, 10k random 768-dimension vectors, and an HNSW build with two parallel workers and a 200 MB `maintenance_work_mem`. Runbook step 3 and the live-swap todo now cover choosing between a parallel build within the 256 MB and a serial one, and setting the values with `ALTER DATABASE` before 0005.
- Files: infra/docker-compose.yml, infra/docker-compose.prod.yml, infra/check-parallel-hnsw.sql, Makefile, scripts/seed_fake.py (comment), README.md, docs/migrations.md, docs/todo.md, docs/context.md, docs/memory.md
- Validation: `docker compose config` resolves `shm_size` to 268435456 bytes in dev and prod, and the prod memory limit to 1610612736 bytes, with the prod Postgres ports still unpublished. Control run of the same SQL in throwaway containers: Docker's default 64 MB failed ("could not resize shared memory segment ... to 206605824 bytes: No space left on device"), which shows the build ran in parallel; 256 MB passed in 2.5 s. Recreated the dev `postgres` service only (volume kept; api and ingest stayed up): `/dev/shm` is 256M, and `make check-parallel-hnsw` passed from Git Bash and from PowerShell.
- Outstanding: the live swap still has to choose the 0005 build settings once the corpus is measured.

### 2026-10-14: Dev path on model A until the live swap; COPY seed

- Changes: `make migrate REV=<revision>` (default head). `docs/migrations.md` documents the dev path (user decision): dev stays at 0003 on model A through steps 4-6, and after the step 6 evals the swap runs for real with recall@10 before and after. A todo item holds the live swap. Safety for that path: 0006 refuses to run while any chunk lacks `embedding_v2`; each revision commits in its own transaction; the ORM defers the `embedding_v2` columns; `.env.example` sets `RETRIEVAL_EMBEDDING_COLUMN=embedding`. `EMBEDDING_DIMENSIONS` joins `EMBEDDING_MODELS` in core. `scripts/seed_fake.py` now loads with psycopg COPY (psycopg 3.3.6 added to the dev group, user request), seeds each company separately, skips companies already loaded, fills every embedding column the schema has, and drops and rebuilds the HNSW indexes once inside its transaction.
- Files: Makefile, .env.example, README.md, packages/core/src/filinglens_core/settings.py, packages/db (models.py, migrations/env.py, versions/0006_drop_embedding_v1.py), scripts/seed_fake.py, services/api/tests/test_app.py, services/ingest/tests/test_embedding_swap.py, pyproject.toml, uv.lock, docs/*
- Validation: make lint and make typecheck clean; make test: 64 passed; make test-int: 7 passed. The swap test now checks that a stray `upgrade head` from 0004 commits 0005 and stops at 0006 with model A intact. The live paging test runs at 0003 and at head, seeds twice, and checks every chunk has a vector and the HNSW index was rebuilt. In a throwaway container with Docker's default 64 MB `/dev/shm`: the seed took 148 s at 0003 (384 dimensions) and 233 s at head (768), down from 779 s at head; a rerun took 0.8 s (was 124 s); counts matched; the planner chose the HNSW index unaided at both revisions (about 10 ms). A parallel HNSW build with 512 MB `maintenance_work_mem` failed at once ("could not resize shared memory segment ... No space left on device"), and the same build serially took 140 s.
- Outstanding: the live swap's 0005 build needs a larger postgres `shm_size` or a serial build (runbook step 3). The user's `.env` still lacks `RETRIEVAL_EMBEDDING_COLUMN=embedding` (manual todo).

### 2026-10-14: Step 3 data (schema, migrations, embedding swap, fake seed, live catalog reads)

- Changes: SQLAlchemy models and Alembic revisions 0002-0006. `companies` gains `sector`; new `filings` (status enum), `sections`, `chunks` (generated English tsvector, pgvector embedding), `financial_facts`, `ingest_jobs`, `ingest_job_items`, `dead_letters` and `eval_runs`; concurrent indexes (HNSW cosine, GIN, `(created_at, id)` keysets, chunk reading order, newest-first filings). `env.py` sets `lock_timeout` 5 s for every migration and gives migrations a 1 hour statement limit. Embedding swap from BAAI/bge-small-en-v1.5 (384) to BAAI/bge-base-en-v1.5 (768): expand 0004, Celery `reembed` task (batches of 256, keyset over chunk id, queues its own next batch, at most 60 a minute), concurrent HNSW 0005, `RETRIEVAL_EMBEDDING_COLUMN` (validated API setting) passed into `filinglens_retrieval.nearest_chunks`, contract 0006; runbook in `docs/migrations.md`. `filinglens_llm.embed` is a stub until step 6. `scripts/seed_fake.py` and `make seed-fake` (Faker 40.43 added to the dev group). `LiveBackend` now reads filings, sections, chunks and facts. User decisions: `seed_real.py` and the SEC client moved to step 4; models A and B as above; stub embedder.
- Files: packages/core (settings.py, tests), packages/db (models.py, __init__.py, migrations/env.py, versions/0002-0006), packages/retrieval, packages/llm, services/ingest (reembed.py, worker.py, tests/test_embedding_swap.py), services/api (backend.py, tests/test_app.py), scripts/seed_fake.py, conftest.py, pyproject.toml files, uv.lock, Makefile, .env.example, infra/docker-compose.yml, README.md, docs/*
- Validation: make lint and make typecheck clean. make test: 64 passed. make test-int: 6 passed. They cover the migration round trip from empty with `alembic check`, and the swap: model A data at 0003, expand, downgrade to 0003 with the data intact, reembed, 0005, EXPLAIN showing `Index Scan using ix_chunks_embedding` or `ix_chunks_embedding_v2` for each flag value with the exact nearest chunk, contract 0006, EXPLAIN again. Reembed ran batches of 256, 256 and 88, resumed from the cursor through the eager Celery task, and caught up one new chunk. `LiveBackend` paged seeded filings (with filters), sections, chunks (reading order, section filter, 400 for an unknown cursor chunk) and facts after seeding twice. Mutation check: an ORDER BY the index cannot serve made the EXPLAIN test fail. In a throwaway container: `alembic upgrade head` through the CLI from empty (1.2 s) and `alembic check` passed; `scripts/seed_fake.py` took 779 s for 200 companies, 2,000 filings, 10,000 sections, 100k chunks and 6,000 facts; the rerun took 124 s and left the counts unchanged; at 100k chunks the planner chose the HNSW index unaided (7 ms for 10 neighbours, index 391 MB); a vector read back through the ORM had 768 values and norm 1.0. Celery registers `filinglens_ingest.reembed.reembed` (60/m, late acks). The exported OpenAPI contract is unchanged, and `docker compose config` passes.
- Outstanding: `seed_real.py` and the SEC client (step 4). The embedding provider (step 6): until then `reembed` fails outside tests. `LiveBackend.search` reads the flag in step 6. The dev compose Postgres was not touched: `make migrate` still waits on the `.env` `API_KEY` line (manual item), and the running api and ingest containers keep the old image until `make dev`.

### 2026-10-14: Step 2 contracts (REST v1, GraphQL, generated clients, drift and breaking-change checks)

- Changes: REST v1 with pydantic models and explicit response models: ingest jobs (admin key, required Idempotency-Key, 202 with Location), companies, filings, search, answers and a Server-Sent Events answer stream; keyset pagination with opaque cursors. Errors are RFC 9457 problems with taxonomy codes; 429 and 503 headers are documented and emitted. Two keys (`API_KEY`, `ADMIN_API_KEY`: 401 missing or wrong, 403 normal key on admin routes) declared as security schemes (user decision). Routes call a `Backend` protocol: companies come from Postgres, the rest answer 501 until their step (user decision). Strawberry types with Relay connections, exported with `strawberry export-schema`. Codegen now builds four clients: openapi-python-client, ariadne-codegen (isolated env), openapi-typescript with openapi-fetch, and the graphql-codegen client preset. New `make contracts-check` and `make contracts-breaking` (oasdiff in Docker). Unexpected errors are answered in the request-id middleware, so a 500 no longer drops the keep-alive connection. `.gitattributes` keeps generated files LF. `ADMIN_API_KEY` added to settings, compose and `.env.example`; a random value was appended to the local `.env`.
- Files: packages/core (errors.py, settings.py, tests), services/api/src/filinglens_api (main.py, __main__.py, contracts.py, schemas.py, problems.py, backend.py, routes.py, graph.py), services/api/tests (conftest.py, test_app.py, test_contract.py), contracts/*, clients/* (openapi-python-client.yaml, operations.graphql, python, python-graphql, ts), Makefile, pyproject.toml, uv.lock, .gitattributes, .env.example, infra/docker-compose.yml, README.md, docs/context.md, docs/memory.md, docs/todo.md
- Validation: `make codegen` ran with no generator warnings, and `tsc` passed on clients/ts. make lint and make typecheck clean. make test: 64 passed, 39 of them contract tests through the generated clients against the app served by uvicorn. make test-int: 3 passed, including companies paged from a real Postgres through the generated client. oasdiff against main: no breaking changes (14 info). In a scratch copy committed to git, `make contracts-check` passed; after renaming a response field and lowering a page limit there, `make contracts-breaking` failed with 3 errors. In this tree `make contracts-check` fails as expected while the new files are uncommitted. `make dev`: stack healthy on the new image; through the generated client every route answered as designed (probes 200, stubs 501, 401 without a key, 403 for `API_KEY` on admin routes, 422 for limit=101). No key values in the API logs.
- Outstanding: line 34 of `.env` sets `API_KEY` to the generator command instead of its output, so `uv run --env-file .env` (make migrate, make seed) cannot parse the file. The compose Postgres has no tables, so the live `/v1/companies` returns 500 until `make migrate` and `make seed` run. CI wiring of both checks is part of step 7.

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
