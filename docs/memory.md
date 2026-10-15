# Memory

Persistent project knowledge for future sessions. Keep entries concise and accurate. Never invent history or decisions. Do not duplicate what is already in `context.md`.

Entry format: `- YYYY-MM-DD: <fact or decision>. Reason: <why>.`

## Decisions and Reasoning

From the approved design doc:

- 2026-10-13: Numeric questions are answered from XBRL facts first. Reason: avoids the model reading numbers off text and guessing.
- 2026-10-13: Celery on RabbitMQ. Reason: common Python stack; RabbitMQ has native dead-letter exchanges and queue length limits.
- 2026-10-13: Celery's rate_limit is per worker, so the SEC limit uses a shared Redis token bucket.
- 2026-10-13: On final failure, tasks raise Reject(requeue=False) so messages reach the dead-letter exchange instead of being acked and lost.
- 2026-10-13: FastAPI is code-first, so the exported OpenAPI spec is committed and checked for drift in CI.
- 2026-10-14: Default to free-tier LLMs behind a provider switch: Gemini Flash for answers, Groq for the router (user decision). Reason: no paid API budget. Filings are public, so free-tier training use is acceptable.
- 2026-10-14: Embeddings come from a local model by default. Reason: Anthropic has no embedding model and local embeddings are free; the vector dimension follows the chosen model.
- 2026-10-14: Production foundations are built from the start, and deployment is a hybrid (UI on Vercel, backend on the PC via Tailscale Funnel, browser reaches the API only through Next.js). Reason: same images locally and deployed; API key stays server-side.

From step 1 (scaffolding):

- 2026-10-14: Apps never read `.env` themselves; `docker compose --env-file .env` and `uv run --env-file .env` supply it. Reason: settings come only from env vars, and tests always start from a clean environment.
- 2026-10-14: Each process loads only its own settings class (`DatabaseSettings`, `ApiSettings`, `IngestSettings`); URLs are pydantic `Secret` types and validation errors hide inputs. Reason: least privilege; secrets never appear in reprs or startup errors.
- 2026-10-14: One `infra/Dockerfile` builds a non-root image per service (`--build-arg PACKAGE`), and `.dockerignore` is an allowlist. Reason: the same images run locally and deployed, and `.env` never enters the build context.
- 2026-10-14: Toxiproxy sits behind the compose profile `test`, beside `observability` for monitoring. Reason: a plain `up` starts only what the app needs.
- 2026-10-14: FastAPI operationIds are the route function names. Reason: readable generated clients; renaming them later would be a breaking contract change.
- 2026-10-14: Alembic config lives in `[tool.alembic]` in the root `pyproject.toml`, and revisions use sequential ids (`--rev-id`). Reason: no extra ini file and a readable history.
- 2026-10-14: Integration tests use Testcontainers with image tags read from `infra/docker-compose.yml`, published on 127.0.0.1. Reason: isolated databases that match the deployed versions.
- 2026-10-14: Logging uses structlog through its stdlib bridge (`ProcessorFormatter`), so uvicorn, Celery and Alembic records share the JSON shape. Redaction runs last, after tracebacks are rendered. Reason: one log format everywhere, and credentials never reach a rendered line.
- 2026-10-14: The request id comes from `X-Request-ID` when it matches `[A-Za-z0-9._-]{1,64}`, otherwise from a new uuid4; the response echoes it. Reason: client and server logs correlate, and untrusted header content is never logged.
- 2026-10-14: Restart policies and memory limits live only in `infra/docker-compose.prod.yml`; dev containers do not restart. The caps are first guesses: ingest (1G) needs more once the embedding model runs there. Reason: in dev, a bad config fails once with a clear error instead of looping.
- 2026-10-14: The API key is accepted only in the `X-API-Key` header, never in the URL; `/healthz` and `/readyz` need no key (user requirement). Reason: URLs end up in access logs, proxies and browser history.
- 2026-10-14: `.env` sets `COMPOSE_FILE=infra/docker-compose.yml`. Reason: the compose file lives in `infra/` and `.env` at the root, and plain `docker compose` from the root should work.

From step 2 (contracts):

- 2026-10-14: Two keys in the same `X-API-Key` header (user decision): `API_KEY` for normal routes, `ADMIN_API_KEY` for admin routes (ingest jobs) and everything else. Missing or wrong key: 401; `API_KEY` on an admin route: 403. Both required and must differ. Reason: the plan makes ingestion admin-only (prompts 4 and 10).
- 2026-10-14: Routes call a `Backend` protocol (user decision). `LiveBackend` serves what exists (companies) and raises `NotImplementedYetError` (501) elsewhere; the contract tests swap in an in-memory fake through `app.dependency_overrides`. Reason: every route's success and error shapes are tested through the generated client before the data layer exists.
- 2026-10-14: Problems use `type: about:blank`, the status phrase as `title`, and a `code` extension from the error taxonomy. Validation errors are 422 `validation_failed` with `errors[{detail, pointer}]` and never echo input. Reason: RFC 9457 without inventing problem-type URIs; inputs may hold secrets.
- 2026-10-14: Cursors are unpadded URL-safe base64 of the last item's sort key as JSON (search: score, chunk_id, index_version). They are not signed. Reason: opaque to clients, and a forged cursor can only skip rows.
- 2026-10-14: The SSE route gets its item model from the return annotation, because FastAPI ignores `response_model` for streams. Events carry a `type` discriminator (`delta`, `completed`, `failed`) instead of SSE `event:` names, so the spec types each event. Admission runs in a dependency, so errors before the stream keep their status code.
- 2026-10-14: GraphQL connections use small local `Connection`/`Edge` generics with Relay's shape. Reason: `strawberry.relay` types require `relay.Node` items with global ids.
- 2026-10-14: Named enums (`FormType`, `FiscalPeriod`) are `StrEnum`s in `schemas.py`, shared by REST and GraphQL. Reason: one shared type per client instead of a copy per field; GraphQL uses the member names (`FORM_10K`).
- 2026-10-14: `make contracts-check` treats staged changes as reviewed and fails only on unstaged or untracked changes under `contracts/` and `clients/`. Reason: in CI that equals "committed output is stale"; locally you can stage regenerated files and re-check.

From step 3 (data):

- 2026-10-14: `scripts/seed_real.py`, the SEC client and its on-disk response cache move to step 4 (user decision). Reason: the prompt has seed_real ingest through the real pipeline, which step 4 builds.
- 2026-10-14: Embedding model A is BAAI/bge-small-en-v1.5 (384 dimensions), model B is BAAI/bge-base-en-v1.5 (768) (user decision). Reason: one model family, both run locally and on Cloudflare Workers AI, and the swap changes the dimension.
- 2026-10-14: The reembed task embeds through `filinglens_llm.embed`, a stub that raises `not_implemented` until step 6 (user decision). Reason: no torch dependency before the provider layer exists; tests pass a fake embedder.
- 2026-10-14: The swap revisions 0004-0006 sit in the one Alembic chain, and the models mirror head (after the contract), so `embedding_v2` is the live column and `RETRIEVAL_EMBEDDING_COLUMN` defaults to it. A release that must stop before the contract runs `alembic upgrade 0005`. Reason: `alembic check` compares the models with head, and Alembic cannot keep a revision out of `upgrade head`.
- 2026-10-14: `RETRIEVAL_EMBEDDING_COLUMN` is an API setting validated at startup and passed into every query; flipping it means restarting the API. Reason: AGENTS.md wants every setting from env vars validated at startup.
- 2026-10-14: Vector columns use a small `Vector` UserDefinedType (text format) registered in the Postgres dialect's `ischema_names`, not pgvector-python. Reason: pgvector-python pulls in numpy and is untyped under pyright strict; asyncpg sends unknown types as text, and reflection still reads `vector(n)` for `alembic check`.
- 2026-10-14: `env.py` sets `lock_timeout` (5 s) once per migration run with session-level `SET`, which also covers autocommit blocks; every concurrent index build first drops the index `if_exists`. Reason: one place covers every migration, and a failed `CREATE INDEX CONCURRENTLY` leaves an invalid index that would block a rerun.
- 2026-10-14: `filings` stores the API's `filed_on` (DATE, EDGAR's filing date) instead of the prompt's `filed_at`. Reason: SEC's filing date is a date, and the API already publishes `filed_on`.
- 2026-10-14: Chunks page in reading order by (`char_start`, id), where `char_start` is the offset in the whole filing text. Cursors keep the contract's id-only `ItemKey`, so the backend looks up the cursor chunk's position. Reason: chunk ids are hashes, so id order is not reading order.
- 2026-10-14: `financial_facts` is unique per (accession, taxonomy, concept, unit, period_start, period_end) with `NULLS NOT DISTINCT`. Reason: the upsert key for idempotent fact ingestion; instant facts have no start date. (Replaced on 2026-10-15 by a key with `cik`; see step 4b.)
- 2026-10-14: Integration tests that move between revisions take the `database_url` fixture, a fresh database on the shared container. Reason: a test that stops at an intermediate revision cannot break the next one.
- 2026-10-14: Fake CIKs start at 9,000,000,000. Reason: above every real CIK, so fake rows never collide with real ones and are easy to find.
- 2026-10-14: Dev stays at revision 0003 (model A) through steps 4-6; after the step 6 evals the swap runs for real, with recall@10 measured before and after (user decision). `make migrate REV=0003` stops there, and `.env.example` sets `RETRIEVAL_EMBEDDING_COLUMN=embedding`, while the code and compose defaults stay `embedding_v2` to match head. Reason: a swap measured on real data, not only in tests.
- 2026-10-14: 0006 refuses to run while any chunk lacks `embedding_v2`. Reason: on the dev path, a plain `make migrate` (head) would otherwise drop every model A vector.
- 2026-10-14: Each revision commits in its own transaction (`transaction_per_migration`). Reason: with autocommit blocks in the chain, a failing revision otherwise rolls back the stamp of the one before it, and the rerun rebuilds that revision's index.
- 2026-10-14: The ORM defers `Chunk.embedding_v2` and `embedding_v2_model`. Reason: loading whole chunks then works at 0003, where those columns do not exist.
- 2026-10-14: Postgres gets `shm_size: 256mb` in both compose files, and its prod memory limit rises from 1G to 1.5G (user decision). Reason: parallel HNSW builds keep their graph in `/dev/shm`, and the limit must cover `shm_size`, a 512 MB `maintenance_work_mem`, `shared_buffers` and connections. Compose also sets `PGUSER` and `PGDATABASE`, so `make check-parallel-hnsw` runs psql in the container without credentials or shell-specific quoting.
- 2026-10-14: `scripts/seed_fake.py` loads with psycopg COPY (psycopg added to the dev group, user decision). It drops the HNSW indexes and rebuilds them once from their `pg_indexes` definitions, inside the load's transaction; each company has its own seed, and a rerun skips loaded companies. Reason: per-row HNSW upkeep was the bottleneck, not the insert path; the transaction puts the indexes back if the load fails, and COPY has no ON CONFLICT.

From step 4 (workers):

- 2026-10-14: Step 4 builds discover and fetch only; parse, chunk, XBRL facts and `scripts/seed_real.py` form step 4b, so one seed run yields searchable data (user decision). The 30 golden-set companies live in `evals/golden-companies.csv`, the 6 seeded ones included (user decision); 4b checks each CIK and ticker against SEC's `company_tickers.json` before ingesting. Reason: a focused step for the reliability mechanics, and an editable list.
- 2026-10-14: The job status keeps `partially_failed` for the prompt's `completed_with_errors` (user decision). A job ends `succeeded` without failures, `partially_failed` when a filing succeeded or was skipped beside a failure, and `failed` only when nothing succeeded. Reason: no contract or enum change.
- 2026-10-14: Revision 0007 (`ingest_job_companies`) revises 0003, and 0004 now revises 0007: until the live swap, every new revision slots in before 0004, and dev migrates to the newest one (`make migrate REV=0007`). Reason: dev must not run the swap revisions, and a revision after 0006 would force them.
- 2026-10-14: A job knows it is finished through `ingest_job_companies` (discovery per company) plus its items; every terminal change locks the job row first, then closes the job when nothing is open. Reason: without the lock, two tasks finishing together could each see the other still open, and the job would never close.
- 2026-10-14: The SEC bucket has capacity 1 at 8 req/s on Redis's clock (`TIME` inside the Lua script), so no second can hold 9 grants. A 403 or 429 sets `sec:cool-off` (Retry-After or 60 s, at most 120 s) that every process waits out before its next request. Reason: SEC caps clients at 10 req/s and documents no throttle format; secondary sources report 403s.
- 2026-10-14: Fetch retries go to `fetch.retry`, an unbounded queue, while `fetch` holds 10,000 with reject-publish. Reason: a retry published to a full `fetch` would be nacked and the filing lost, and it would also wait behind the whole backlog.
- 2026-10-14: On a nacked fetch publish, discover queues itself again with a jittered backoff (up to 60 s) and returns. It does not sleep in the task. Items it could not queue stay `pending`, and a rerun queues only those. Reason: a sleeping discover holds a worker slot, and with every slot asleep nothing drains the fetch queue.
- 2026-10-14: Both tasks set `acks_on_failure_or_timeout=False`, so any failure their handler misses is still rejected into the dead-letter queue instead of acked. The handler writes the `dead_letters` row (one per task id) before `Reject`. Reason: no message is ever lost silently.
- 2026-10-14: Raw SEC responses are cached gzipped under their URL path in `SEC_CACHE_DIR` (compose volume `sec-cache`): filing documents for good, submissions JSON for an hour. Reason: fetch's output is the cached document, and repeated discover runs do not hit SEC again.
- 2026-10-14: The API queues discover through Celery's `send_task` with the queue arguments from `filinglens_core.queues` (plain data), and the worker builds its kombu queues from the same data. A retry with the same Idempotency-Key queues discover again while the job is still `queued`. Reason: RabbitMQ refuses a redeclaration with other arguments; the requeue covers a crash between the commit and the publish, and discover is idempotent.
- 2026-10-14: The API rate limiter fails open while Redis is down (logged), but the AI budget fails closed (503). Reason: an outage should not stop reads, and nobody should spend LLM tokens that cannot be counted.
- 2026-10-14: `SEC_USER_AGENT` is required and must contain an email; the `.env.example` placeholder (`@example.`) is refused, and compose stops without it. Verified on sec.gov ("Accessing EDGAR Data"): at most 10 requests a second, and a declared User-Agent with a company name and an admin contact email.

- 2026-10-15: The SEC limiter fails closed (user request). Without Redis the client raises `LimiterUnavailableError` before any request, and fetch and discover send themselves again after a jittered 30 s pause with their retry count unchanged. `attempts` counts tries that ran, so neither a pause nor a try killed mid-request counts. The API's inbound limiter still fails open. Reason: unlimited requests could get the IP blocked by SEC, and a Redis outage is no fault of the filing.
- 2026-10-15: A 403 sets a strike beside its cool-off. A 403 after that cool-off ends (within 60 s, with no success between) is a refusal, not a throttle (user request). The client then stores the reason in `sec:refused`, and every SEC call fails at once with `SecRefusedError` without reaching SEC. The job's remaining filings therefore fail fast, and each failure and dead letter carries the reason (check SEC_USER_AGENT). A success clears the strike, a 429 always only cools off, and a worker restart clears the refusal. Reason: a bad User-Agent would otherwise cool off forever.

From step 4b (parse, chunk, facts):

- 2026-10-15: Parse finds items by their headings. The table of contents is the opening run of item lines in rising item order; it ends at the first step back to an earlier item after at least 4 rows, and each item's section starts at its first heading after that. Sections take the form's own item titles, not the document's. Reason: on the 30 golden-set 10-Ks, page-number and dense-run rules missed contents tables split by part headers (MSFT, PG, KO, XOM, CAT, LMT, UNP, GS, PFE) and dropped CVX's body rows that cite FS- pages, and document titles picked up page headers (BAC).
- 2026-10-15: A filing fails parse only when it has none of its required items (10-K: 1, 1A, 7, 7A, 8; 10-Q: Part I Items 1-3, Part II Item 1A). Missing ones go to `filings.missing_items`, and `seed_real.py` lists them; a heading whose item reads "Not applicable" or "omitted" counts as found (user decision). Reason: one missing item never fails a job, but the gap stays visible.
- 2026-10-15: `parsed` now means sections and chunks stored: chunk sets it, and the job item succeeds then. A job company succeeds once its facts are loaded, so discover queues facts after its last page. discover marks an item `skipped` only for a filing at `parsed` or later; a fetched filing goes through fetch (no download) to parse. Reason: no enum or contract change, and a job closes only when every stage settled.
- 2026-10-15: Parse stores each section's text in `sections.text` (deferred in the ORM), and chunk splits that. Reason: the tasks stay separate, and chunking again later needs no new parse.
- 2026-10-15: Chunks hold at most 384 tokens of BAAI/bge-small-en-v1.5 (model A) and overlap by 64, ending at a line or sentence break in their last quarter. The model's `tokenizer.json` is vendored (Hugging Face commit 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a, MIT) and read with `tokenizers` (user-approved dependency; it brings `huggingface-hub`, which step 6 needs anyway). Reason: exact token counts for the 512-token model, with no download at runtime or in tests.
- 2026-10-15: facts loads each company's whole companyfacts (user decision) in batched inserts with `ON CONFLICT DO NOTHING`. Values, units, periods and forms stay as SEC published them (`10-K/A` and `10-Q/A` included; `form` is a string, not the API's `FormType`). Entries without a fiscal year, or with a fiscal period outside FY and Q1-Q4, are skipped: 3-7% of entries in the survey, from 8-K, 424B2 and DEF 14A filings. Reason: the columns are NOT NULL, and the API's `FiscalPeriod` takes only those values.
- 2026-10-15: `financial_facts` is unique on (cik, taxonomy, concept, unit, period_end, period_start, accession number) with `NULLS NOT DISTINCT` (user decision). Reason: one combined filing (Duke Energy's, say) reports facts for several registrants under one accession number.
- 2026-10-15: Selection rule for step 6's `get_financial_fact` (user decision): for a concept, unit and period, take the value from the latest-filed filing that reports it (`filed_on`, then accession number), so restatements win. Annual periods come from 10-K and 10-K/A, shorter durations from 10-Q and 10-Q/A, instants from any of the four. Query by period dates: a fact's `fiscal_year` and `fiscal_period` belong to the filing that reported it, so a comparative carries the later year. The unique index's leading columns (cik, taxonomy, concept, unit, period_end, period_start) serve the lookup, and the few matching rows sort by `filed_on`.
- 2026-10-15: A filing's fiscal year and period come from its companyfacts entries (the most common fy and fp of its accession number), else from `period_end` and the company's `fiscalYearEnd`; `filings.fiscal_source` records which. Only the facts task writes them. Reason: no race between parse and facts; the fallback is approximate for 52-53 week years.
- 2026-10-15: `seed_real.py` takes each company's latest original 10-K, reading older submissions files for heavy filers such as JPM, and queues one ingest job per company through `LiveBackend` (form 10-K, `since` its filing date). A company with only a 10-K/A stops the run (user decision: the contract's `FormType` has no 10-K/A). Each run uses new Idempotency-Keys, so a rerun goes through discover.
- 2026-10-15: The SEC cache is a bind mount of the repo's `.cache/sec` (gitignored) instead of the `sec-cache` volume, and host runs set `SEC_CACHE_DIR=.cache/sec`. Reason: caches stay on H: (AGENTS.md), and the worker reuses what host runs downloaded. The old `filinglens_sec-cache` volume is unused but still exists; it was left in place.
- 2026-10-15: `SecClient` counts every request it sends in the Redis hash `sec:requests`, by kind (document, submissions, companyfacts, tickers); `seed_real.py` prints the difference over its run. Reason: downloads per run without reading logs.
- 2026-10-15: Dev now runs at revision 0008 (`make migrate REV=0008`); 0004 revises it, so the swap stays last.
- 2026-10-15: SEC now lists XOM under ExxonMobil Holdings Corp (CIK 2115436), which has no 10-K of its own yet; Exxon Mobil Corp (CIK 34088) filed the latest one. The golden set replaced ExxonMobil with ConocoPhillips (COP, CIK 1163165) (user decision). Reason: the ticker check stays strict and needs no exceptions.

From step 5 (tests):

- 2026-10-15: Integration tests keep Testcontainers rather than the compose services (user decision). Reason: throwaway databases, isolated from the dev data.
- 2026-10-15: Tests stay off the network through `network_guard.py`, which wraps `socket.getaddrinfo`: any host but localhost, loopback or 0.0.0.0 raises `NetworkBlockedError` (a `RuntimeError`, so no client retries it). The root conftest installs it in the pytest process, and `run_worker.py` and the rate test's client processes install it too. Reason: AGENTS.md forbids live SEC and provider calls in tests, and a list of blocked hosts would go stale; a single choke point also covers Hugging Face downloads.
- 2026-10-15: Every test without the `integration` or `e2e` marker gets `unit` from the root conftest, and `make test` runs `-m unit`. Reason: no marker to forget on new unit tests.
- 2026-10-15: `citation_error` compares the quote and the chunk text after the same normalization (NFKC, curly quotes to straight ones, whitespace runs collapsed) and stays exact on words, digits and letter case (user decision). Reason: models reflow whitespace and quote marks, but a changed word or number is a wrong citation.
- 2026-10-15: `parse_amount` reads one amount: the scale words and the abbreviations K, M, B or bn, and T, in either case, with or without a space (user decision). Pulling amounts out of answer text ("about $4.2B") is step 6's finder, which hands each to `parse_amount`. Reason: models write $4.2B as often as $4.2 billion; extraction belongs with the answer pipeline.
- 2026-10-15: `reciprocal_rank_fusion` sums exact fractions and sorts by (score descending, id). Reason: mathematically equal scores become equal floats whatever the order of the lists, and the order matches the search cursor's (score, chunk_id).

## Preferences and Instructions

- 2026-10-14: The three portfolio projects run in parallel Claude Code sessions on one PC, sharing Docker. Each project has its own port range and compose project name; never prune or remove another project's Docker resources (user setup).
- 2026-10-13: General coding rules live in `AGENTS.md`. `CLAUDE.md` imports it so Claude Code loads the rules.
- 2026-10-13: Markdown filenames use kebab-case (for example `docs/migrations.md`).

## Solved Problems

None yet.

## Known Issues and Pitfalls

- 2026-10-14: RabbitMQ 4.3 refuses transient non-exclusive queues. Celery needs `control_queue_exclusive=True` and `event_queue_exclusive=True`, or the worker's consumer crash-loops while the broker still looks reachable. That is why the ingest `/readyz` pings the worker through RabbitMQ.
- 2026-10-14: Windows Application Control on this PC blocks some uv console-script launchers (alembic, celery, uvicorn: os error 4551). Run tools as `uv run python -m <tool>`, as the Makefile does.
- 2026-10-14: GNU make (ezwinports) runs recipes with cmd.exe from PowerShell and with sh from Git Bash. Keep recipes shell-neutral.
- 2026-10-14: `uv run --env-file` expands `${VAR}` but not `${VAR:-default}`, so `.env.example` references only variables it defines.
- 2026-10-14: Postgres 18 images keep data under `/var/lib/postgresql`. Mount the volume there, not at `/var/lib/postgresql/data`.
- 2026-10-14: Starlette's TestClient prefers `httpx2` (the pydantic fork) and warns on `httpx`, so the dev group uses `httpx2`. Verified: starlette.dev/testclient recommends it, and PyPI lists the `pydantic` organization (owner Kludex, Starlette's maintainer) for the package. The 2.13.1 wheel has no PEP 740 attestation.
- 2026-10-14: Testcontainers' Ryuk reaper publishes a random port on 0.0.0.0 during `make test-int`; the test containers themselves bind 127.0.0.1. `TESTCONTAINERS_RYUK_DISABLED=true` avoids it, but a crashed run could then leak containers on the shared Docker host.
- 2026-10-14: ariadne-codegen 0.19 pins `graphql-core<3.3` and `ruff<0.16`, which clash with Strawberry (`graphql-core>=3.3`) and the project's ruff. The Makefile runs it in a throwaway env (`uv run --isolated --no-project --exclude-newer ...`), never in the workspace.
- 2026-10-14: `strawberry export-schema` and ariadne-codegen write CRLF on Windows, and `core.autocrlf=true` is set system-wide here. `.gitattributes` forces LF for `contracts/` and `clients/`, so the drift check agrees across machines.
- 2026-10-14: An exception handler for `Exception` makes Starlette re-raise afterwards, and uvicorn then closes the keep-alive connection; the client's next pooled request failed with "Server disconnected". The request-id middleware now answers unexpected errors itself.
- 2026-10-14: `openapi-python-client --overwrite` deletes `clients/python` first, so its config lives in `clients/openapi-python-client.yaml`. The generated clients are editable dev dependencies; `uv run` fails if `clients/python-graphql/filing_lens_graphql_client/` is missing, so regenerate it before syncing.
- 2026-10-14: oasdiff has no Python or npm package and Go is not installed, so it runs from a digest-pinned Docker image and reads the base spec straight from git (`main:contracts/openapi.json`). The Makefile exports `MSYS_NO_PATHCONV=1` so Git Bash does not rewrite `/repo`.
- 2026-10-14: SQLAlchemy 2.1 types `Select` and `Row` with variadic generics: annotate `Select[str, float]`, or `Select[*tuple[Any, ...]]` for any shape (`Select[Any]` means one column). `Result.tuples()` is deprecated, because rows unpack directly.
- 2026-10-14: pyright reads the result of Celery's untyped `shared_task` decorator as `list[str]`. Inside a task use `bind=True` and `self: Task`; outside, `cast(Task, task)`.
- 2026-10-14: In `INSERT ... SELECT :param, ...`, Postgres types the parameters as text, so integer columns fail; use `VALUES (:param, (SELECT ...))`.
- 2026-10-14: The app engine's asyncpg `command_timeout` (30 s) would cancel index builds, so `env.py` gives migrations an hour.
- 2026-10-14: With a few hundred rows the planner prefers a sequential scan to an HNSW index, so the EXPLAIN test sets `enable_seqscan = off`; the plan then shows the index only if the query's shape can use it (checked by breaking the ORDER BY: the test fails with a disabled seq scan). At 100k fake chunks the planner picks the HNSW index unaided: 7 ms for 10 neighbours, index 391 MB.
- 2026-10-14: Inserting into an HNSW index row by row is slow: the first `make seed-fake` (INSERT with the index in place) kept Postgres at one full core for 13 minutes per 100k chunks. With COPY and a single rebuild it takes 233 s at head (768 dimensions, of which the rebuild is about 140 s) and 148 s at 0003 (384); a rerun takes under 1 s.
- 2026-10-14: A parallel HNSW build allocates shared memory of about `maintenance_work_mem`, and Docker's default 64 MB `/dev/shm` makes it fail at once with "could not resize shared memory segment ... No space left on device" (seen with 512 MB and with 200 MB). Compose now sets `shm_size: 256mb`, which fits a 200 MB parallel build (`make check-parallel-hnsw`). The seed still builds serially, because its 100k-vector graph (about 400 MB) is larger than that.
- 2026-10-14: Postgres only plans parallel index workers for tables above `min_parallel_table_scan_size`, unless the table sets `parallel_workers`; the check sets it so 10k vectors are enough. Parallel workers never serve temporary tables.
- 2026-10-14: psycopg sends a query without parameters as is, so `%` in it (such as `LIKE '%USING hnsw%'`) needs no escaping; psycopg's `execute` types queries as `LiteralString`, so running SQL read from the catalog takes a `cast`.
- 2026-10-14: With publisher confirms, Celery's `send_task` and `apply_async` raise a nack as `kombu.exceptions.OperationalError` whose `__cause__` is `amqp.exceptions.MessageNacked`, even with `retry=False`: py-amqp lists `MessageNacked` among its recoverable connection errors, and Celery wraps publishes in `_reraise_as_library_errors`. With `retry=True`, kombu also reconnects and republishes first. kombu's own `Producer.publish` raises the bare `MessageNacked`. The first backpressure test caught discover dead-lettering on a full queue.
- 2026-10-14: kombu's global producer pools are keyed by broker URL and transport options, so every Celery app in a process with the same broker shares connections and their cache of declared queues. A queue deleted behind that cache makes the next publish vanish (unroutable, yet confirmed). Tests purge queues instead of deleting them.
- 2026-10-14: Workers declare only the queues they consume, and an unbound dead letter is dropped, so the worker declares the dead-letter queues itself on `worker_ready`. The replay command declares the work queue before it publishes.
- 2026-10-14: Celery's autoretry backoff has a 1 s floor (`factor=int(max(1.0, retry_backoff))`), so six retries take up to 63 s. `services/ingest/tests/run_worker.py` patches `celery.app.autoretry.get_exponential_backoff_interval` (looked up at call time) to 0, and production code stays untouched.
- 2026-10-14: On Windows, arrivals at a local HTTP server jitter by about one scheduler tick (~16 ms) after the Redis grant. The rate test therefore allows 50 ms; measured, the 9th request after any request came 0.983 s later at worst. Python 3.12's `time.monotonic()` on Windows also ticks every ~15.6 ms, so timing code uses `time.perf_counter()`.
- 2026-10-14: The 413 code comes from Python's HTTP phrase: `request_entity_too_large` on 3.12. Python 3.13 renames the phrase ("Content Too Large"), so an interpreter upgrade changes that code; `test_limits.py` pins it.
- 2026-10-15: Tables are flattened row by row into the filing text (cells joined by " | ", empty cells dropped), so chunks lose table layout. A known limit until a table-aware chunker exists (user request to note it).
- 2026-10-15: Some 10-Ks keep MD&A or the financial statements in a separate financial section (XOM, CVX, JPM, PLD and NVDA in the survey of the golden set), and their Items 7, 7A or 8 only point there. That content still gets chunked, under the last item (15 or 16; JPM's Item 15 holds 1.0M characters), so filtering by Item 7 misses it. PFE and VZ were expected to incorporate items from exhibit 13 but do not in their latest 10-Ks.
- 2026-10-15: companyfacts' `fy` and `fp` describe the filing that reported a value, not the value's period: Apple's fiscal 2023 revenue appears in its fiscal 2025 10-K with fy 2025.
- 2026-10-15: On Windows a connection to a closed 127.0.0.1 port is refused only after about 2 s (measured 2.0 s), so readiness tests with dead dependencies took 6 s each. Tests now point dead dependencies at `0.0.0.0:1`, which fails at once on Windows (invalid address) and is refused at once on Linux.
- 2026-10-15: Without `configure_logging`, structlog's default console renderer formats exceptions with rich, locals included: one logged 500 took 3.8 s. The root conftest's autouse fixture applies the production JSON format to every test.
- 2026-10-15: Starting and stopping uvicorn per test cost about 0.3 s, so the contract tests share one server per module (`_served`), and each test plugs in its own fake backend. The fixtures that run the app themselves (`client`, `live`, `postgres_user`, `serve`) share the one app object, so a module must not use them after a test that used the shared server.
- 2026-10-15: Windows Application Control blocks the Rust extension (`hypothesis/_native.*.pyd`) that hypothesis ships from 6.156.1 on ("An Application Control policy has blocked this file"), so the dev group pins `hypothesis>=6.155.7,<6.156`, the last pure-Python series.
- 2026-10-15: Alembic's `env.py` runs its own event loop (`asyncio.run`), so async tests migrate in a sync fixture (`db` in `test_under_load.py`), never inside the test.

## Rejected Approaches

None yet.

## Lessons Learned

None yet.

## Constraints

None yet.

## Unresolved Questions

- 2026-10-13: Corpus size estimate (200k to 300k chunks for S&P 500 10-Ks) is unmeasured. Measure on a 20-filing sample first. Measured on 2026-10-15 on the 30 golden-set 10-Ks: mean 375 chunks per 10-K (median 314), so about 190k chunks for one 10-K per S&P 500 company. 10-Qs are still unmeasured.
- 2026-10-14: Free-tier rate limits will slow full eval runs. Check each provider's console before a big run. Dollar cost targets apply only on a paid tier.
