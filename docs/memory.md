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

From step 6a (providers, local models, search, answers):

- 2026-10-15: Models pinned (user decisions; ids listed by each key on 2026-10-15): `LLM_PRIMARY=gemini:gemini-3.5-flash-lite` (version 3.5-flash-lite-07-2026), `LLM_ROUTER=groq:openai/gpt-oss-20b`, `LLM_FALLBACK=nvidia:openai/gpt-oss-20b`. Free limits: Gemini Flash-Lite about 500 requests a day and the bigger Flash about 20 (secondary sources: scriptbyai, AI Studio figures of September 2026; Google publishes no table, its rate-limits page points to AI Studio); Groq 1,000 requests a day and 8,000 tokens a minute (this key's response headers); NVIDIA NIM about 40 requests a minute (secondary sources, no official page found), credits shared with Triage Copilot. Reason: Flash's 20 a day cannot run one 100-question eval.
- 2026-10-15: NVIDIA fallback chosen by a test (user rule: one real answer call each, same question, 12 retrieved chunks, our reply format; pick the one that passes, deepseek if both). deepseek-ai/deepseek-v4.1-flash: 53.1 s, first token 50.6 s, 4,490 in / 1,024 out (cap), no Sources block, router JSON schema failed. openai/gpt-oss-20b: 10.3 s, first token 1.66 s, 4,446 in / 556 out, format and router schema passed, 2 of 5 quotes passed `citation_error` (3 paraphrased). Neither passed in full; gpt-oss-20b kept, as its failures go through regeneration and sentence removal.
- 2026-10-16: openai/gpt-oss-120b probed as the NVIDIA fallback (user request; the same answer call, at 16:06 UTC on 2026-10-15). NVIDIA answered 410 Gone: "The model 'openai/gpt-oss-120b' has reached its end of life on 2026-09-03T08:00:00Z and is no longer available", and the key's model list (81 models) no longer has it. gpt-oss-20b stays `LLM_FALLBACK`. Its second run in the same probe: 13.1 s, first token 1.37 s, 4,446 in / 772 out, format and router schema passed (router 1.13 s), 2 of 6 quotes passed `citation_error`, 6 sentences failed the check. The list's other 120B-class models (nvidia/nemotron-3-super-120b-a12b, nvidia/nemotron-3.5-super-vl-120b-a12b) were not probed.
- 2026-10-15: A primary 429, 5xx, timeout, 401/403 or 402 falls back to `LLM_FALLBACK` once, and a failed router call routes with it (user request); each fallback is logged and counted in the day's Redis hash (`fallbacks`). A 402 (credits used up) or a fallback that fails too ends the answer with 503 `ai_unavailable`, no retry. Evals pass `allow_fallback=False`. Reason: a Groq or Gemini outage should not stop answers, and a dead fallback must fail fast.
- 2026-10-15: `AI_ENABLED` defaults to false (it defaulted to true in code, compose and `.env.example`). With AI on, each role's provider needs its key, and an empty key counts as missing.
- 2026-10-15: Reranker (user decision after measuring): TinyBERT-L-2 over the fused top 50 with whole chunks (p95 182 ms on this CPU for 50 real chunks) instead of MiniLM-L-6 over 100 (p95 3,235 ms). `RERANK_MODEL`, `RERANK_CANDIDATES`, `RERANK_MAX_TOKENS` are settings; 6b picks the default on the dev split (todo). All latencies are on this PC's CPU, the production host.
- 2026-10-15: The answer model cites source ids ([F1], [C3]) and quotes each under `Sources:`; readers get [1], [2]... in order of first use, renumbered the same way while streaming and after validation. Reason: Gemini wrote [F1] by itself when asked for [n], and failed validation twice.
- 2026-10-15: Every sentence must cite a source; a chunk citation needs a quote that passes `citation_error`; every amount (money, numbers with a scale word or thousands separators, percentages) must match a cited fact's value or a number in a passing quote within 0.5% at a table scale (x1, x1e3, x1e6, x1e9; percentages also x100), signs ignored. Derived figures (growth rates) therefore fail. A failing draft gets one regeneration, then failing sentences are dropped with a warning; `completed` then replaces the streamed draft.
- 2026-10-15: Refusals: out of scope (router), a ticker FilingLens does not track, a fiscal year later than the company's latest 10-K in its facts (time trap), and a best rerank score under -3.0 (provisional; TinyBERT gave 0.7 to 9.4 on topic, -10.9 off; 6b calibrates). Reason: deterministic refusals cost no answer call.
- 2026-10-15: Filing statuses: chunk sets parsed and queues embed; embed fills `RETRIEVAL_EMBEDDING_COLUMN` (and `<column>_model`), sets indexed when the fiscal year is known, else embedded, and the job item succeeds there; facts indexes embedded filings. A separate `embed` service (`-Q embed,reembed -c 1`) holds the only model copy. Reason: the API lists and searches indexed filings only, and 16 prefork processes would each load torch.
- 2026-10-15: Local models load from `HF_HOME=H:\.cache\huggingface` (machine-wide), pinned by commit in `filinglens_llm.local`; `make models` fetches them, containers mount the cache read-only with `HF_HUB_OFFLINE=1`, and the root conftest sets `HF_HUB_OFFLINE=1`. The Hugging Face cache keeps weights as symlinks into a shared blob store; the read-only bind mount reads them in Linux containers.

From step 6b (golden set, judge, evals):

- 2026-10-16: `LLM_JUDGE=groq:openai/gpt-oss-120b` (user decision), used only by evals for citation precision and faithfulness. Different family from the answer model (Gemini). Limits on Groq (rate-limits page, read 2026-10-15): 30 requests/min, 1,000/day, 8K tokens/min, 200K tokens/day. Production status, with no deprecation listed (Groq deprecations page, read 2026-10-16); $0.15 / $0.60 per 1M tokens paid. Its 200K tokens/day are shared with fallback decision 4's gpt-oss-120b run, so the two run on different days. Reason: fast, holds the JSON schema; qwen3.8-27b is a Groq preview (its predecessor was shut down 2026-09-14), and nemotron on NVIDIA was unprobed.
- 2026-10-16: Eval floors in `evals/thresholds.json` follow the rule of FreightAudit and Triage Copilot (user decision). Accuracy: min(lower 95% bound, target). False refusal, where lower is better: a ceiling of max(upper bound, target). Efficiency (latency, tokens, cost) that meets its target: min(upper x 1.5, target), so a 50% regression fails. Efficiency that already misses its target: upper x 1.5 with no cap, so a known miss doesn't fail every run while the report still marks the target failed. Example: time to first token p95 measured 3.0 s, upper bound 3.5 s, against a 2.0 s target gives a floor of 5.25 s. Cost as billed: floor 0 (since 2026-10-17, on the free setup only; a setup that spends credits gets the efficiency rule). Floors are written only on request and only tighten; loosening one needs a written reason here.
  - Since 2026-10-16 (user decision): `python -m evals.harness --set-floors REPORT` applies the rule to a saved report's measured values, and a run only checks floors. So every floor, TTFT and full-answer latency included, comes from the run's own live numbers. A rerun from the cache has no live latency and could not set those.
- 2026-10-16: Passage gold for golden set v1 is AI-labeled, spot-checked by a non-expert (user decision, made after labeling the 19 passages of x01 by hand).
  - Claude labeled every pooled passage with the same guideline (`evals/golden/v1/ai_labels.jsonl`, each with a one-line reason).
  - The user labels a blind sample of 60 more with `make audit`: fixed seed, at least 20 Claude-gold, spread over the other 29 questions. The sample is frozen in `audit.jsonl`.
  - The user then makes the final call on every passage where their blind label and Claude's differ (the 19 included), after seeing Claude's reason.
  - Final label: the user's where given, otherwise Claude's.
  - The manifest records agreement and Cohen's kappa (bootstrap CI) between the user's blind labels and Claude's, before review.
  - Neither label file is edited by hand.
  - Reason: labeling 540 passages by hand takes about 1.5 hours; the audit measures how far the AI labels can be trusted, and a human settles every disagreement.
  - Result, from the manifest:
    - Blind agreement on 79 passages was 49.4%, Cohen's kappa 0.10 (95% CI -0.07 to 0.26). Claude said gold on 27, the user on 55.
    - Of the 40 disagreements, 34 had the user saying gold where Claude did not (11 of them on absent questions), and 6 the reverse.
    - By sitting: x01's 19 passages agreed 79% (kappa 0.22); the 60-passage sample agreed 40% (kappa -0.02), with the user saying gold on 53.
    - Pace: a median of 3 s per passage in the sample (passages run a median of 262 words). The review took 47 s for 40 decisions.
    - The review settled 37 of the 40 on Claude's label. The 3 settled on the user's label (x01 e9a636de, x02 89cfdd9a, x05 de1c06bf) are gold in the final key.
    - Golden v1 was frozen on 2026-10-16.
  - Wording (user instructions, 2026-10-16):
    - The docs say "AI-labeled, spot-checked by a non-expert", never "human-audited", a careful audit or human-verified.
    - They describe the human check plainly, as a fast spot-check by a non-expert that cannot validate the labels on its own.
    - They give the blind kappa with its CI and the review result, and say that the review showed Claude's reason, so it was not independent.
    - The eval card keeps the sitting numbers: time per passage, 53 of 60 marked gold, and 47 s for the review.
  - Corrections (user decision, 2026-10-16):
    - Prompt: Claude quoted the passage text of the three review calls that had gone the user's way. After reading it, the user set x01 `e9a636de` (Apple's services and segments, not manufacturing) and x05 `de1c06bf` (Tesla's tax-incentive note, which never says a Gigafactory builds vehicles) to not gold, and kept x02 `89cfdd9a` as gold.
    - Records: `labels.jsonl` holds them as rows with `step: "correction"` and a `why`. `blind_labels` skips every row with a step, so the blind numbers did not move.
    - Freeze: V1 was unfrozen and refrozen before any test run. The manifest now records review 37 of 40 to Claude, 2 corrections, and a final key that matches Claude on 39 of the 40 disagreements (152 gold passages).
- 2026-10-16: x15 (Caterpillar's order backlog at the end of 2025) stays, with one chunk added to its pool (user decision).
  - No pool source caught CAT's Item 1 "Order Backlog" paragraph ($51.2 billion at December 31, 2025): none of the three rerankers had it in its top 10, and the phrase source's top 5 went to "dealer inventory" chunks. So the AI labels gave x15 no gold.
  - `ADDED` in `evals/golden.py` appends the chunks of the company that hold the phrase "order backlog". Claude labeled the one it found as gold, and the audit sample includes it.
  - Reason: replacing x15 would drop a real retrieval miss from the eval.
- 2026-10-16: The eval harness (`evals/harness.py`, `evals/calls.py`, `evals/judge.py`) follows the approved 6b plan.
  - Cache key: the sha256 of the question id; the call's role, model, options (Gemini thinking), max tokens and schema; and the hashes of both prompts. Answer calls add the answer path: router and primary ids, the embedder and reranker with their pinned revisions, rerank candidates and max tokens, and the index version (a hash of the indexed chunk ids). Judge keys leave the path out. So a new primary re-asks the router, a new thinking setting re-asks only the primary, and a rerun with another refusal threshold reuses everything.
  - A 429 never reaches the Answerer: it would become 503 there. The call layer raises it as `RateLimited`, which is not a `FilingLensError`; the question then waits outside its 30 s answer timeout and runs again from the cache. The third 429 in a row, or a Retry-After over 120 s, exits 2 (Gemini sends no Retry-After, so the wait is 60 s). A refused key or no credits (`AiUnavailableError`) also exits 2.
  - Run files (`.cache/evals/runs/<config hash>.jsonl`) let a stopped run resume. Errored questions are retried on resume, and the file is deleted once the report is written, so the next run of the same command rebuilds from the cache.
  - Latency counts only questions whose calls were all live. The judge's calls are recorded apart from the answer path's.
  - The judge makes one call per answer that was not refused, with the full text of each cited source and the quote given. Citation precision is the share of (sentence, citation) pairs it marks as supporting; faithfulness is the share of sentences fully supported. Both show as not measured until `make calibrate` gives kappa 0.7 or more, recorded in `evals/calibration/v1/result.json`.
  - Prices in `evals/providers.json` (read 2026-10-16), per 1M tokens:
    - Gemini 3.5 Flash-Lite, paid Standard tier: $0.30 in, $2.50 out (ai.google.dev pricing page).
    - Groq gpt-oss-20b: $0.075 / $0.30.
    - Groq gpt-oss-120b: $0.15 / $0.60.
    - NVIDIA: no per-token price, only trial credits, so a run with an NVIDIA primary has no paid-equivalent cost.
- 2026-10-16: Decision 1, reranker (dev, 14 textual questions, 70 queries for latency; the plan's fixed rule): TinyBERT-L-2 over the fused top 50 with 512 tokens stays the default, so settings, `.env.example` and compose are unchanged.
  - Single runs (reports in `evals/reports/runs/`):

    | Configuration | recall@10 | MRR@10 | nDCG@10 | Rerank p95 |
    | --- | --- | --- | --- | --- |
    | TinyBERT-L-2, top 50 | 0.613 | 0.649 | 0.584 | 217 ms |
    | MiniLM-L-2, top 24, 256 tokens | 0.601 | 0.720 | 0.601 | 194 ms |
    | MiniLM-L-6, top 100 (ineligible, the ceiling) | 0.705 | 0.800 | 0.703 | 3,065 ms |

  - Paired bootstrap, MiniLM-L-2 minus TinyBERT: MRR@10 +0.071 (95% CI -0.060 to +0.208), recall@10 -0.012 (-0.129 to +0.112). Both intervals hold 0, a tie, so the faster one wins.
  - "Faster" was unclear from single runs: p95 favored MiniLM-L-2 by 23 ms, p50 favored TinyBERT. Three alternating passes (210 queries each) settled it:
    - TinyBERT rerank: p50 134 ms (CI 134-135), p95 162 ms (156-167).
    - MiniLM-L-2 rerank: p50 161 ms (161-162), p95 184 ms (173-190).
  - The ceiling against TinyBERT: MRR +0.151 (-0.004 to +0.330), recall +0.092 (+0.007 to +0.185), at about 14 times the rerank time.
  - judged@10 is 1.000 for all three, since the pools hold each configuration's top 10. It matters only for a new embedder or reranker.
- 2026-10-16: Decision 2, refusal threshold (dev): no threshold meets the plan's rule, so `RELEVANCE_MIN` stays -3.0.
  - The run: `make eval SUITE=answer SPLIT=dev ARGS="--min-relevance=-100"` (report `evals/reports/runs/20261016T055608Z-answer-dev-full`). 70 questions, no errors, 12 rate-limit waits and no quota stop.
    - Router: 70 calls, 43.8K tokens in and 4.8K out.
    - Gemini: 53 calls, 164K in, 5.7K out.
    - Judge: 37 calls, 33K in, 7.9K out.
  - Correct refusal is already 18 of 18 with the gate off. False refusal is 15 of 52 (0.288), none of it from the gate, so the rule (most correct refusal with false refusal at most 5%) has no feasible threshold.
  - `--sweep`: correct refusal stays 1.000 at every threshold. False refusal stays 0.288 for any t up to 4.338 (x19, the lowest-scoring answered answerable question) and only rises above it.
  - -3.0 lies in that no-cost range. It gates only u02 (-4.383), which the model refused anyway. Kept: it costs nothing on dev and catches very weak retrievals.
  - The gate cannot separate absent from answerable questions: absent a02 scored 5.217, above five answered textual questions.
  - The false refusals come from the router and the model, not the gate (see the router pitfall below). User decision pending on fixing the router before decisions 3-4.
- 2026-10-16: Decision 3, time to first token (dev full): Gemini thinking stays minimal; the setting is not the lever.
  - Design: minimal, default, minimal in one sitting (A-B-A, 09:00 to 09:25 UTC), because Gemini's latency drifts with the hour (Known Issues). Reports `20261016T090721Z` (3a, every call live, `--tag=d3`), `091644Z` (3b, default thinking, router replies from 3a) and `092456Z` (A2, minimal, `--primary-tag=r2`).
  - 3a, end to end (46 live answers):
    - TTFT p50 4.24 s (95% CI 3.94 to 5.47), p95 9.26 s (6.72 to 17.01).
    - Stage p50: router 0.66 s, retrieval 0.30 s, facts 0.05 s.
    - Gemini's own first token: p50 3.37 s.
  - Gemini's own first token, paired per question:
    - Default against A2: p50 −0.21 s (CI −0.86 to +0.63, n 38).
    - The two minimal passes, 15 minutes apart: −0.46 s (−1.36 to +0.17).
    - So drift is as large as any effect of the setting.
  - Default thinking wrote no extra output tokens (p50 63 against 64), so this model's default looks like minimal. Minimal stays, which needs no change.
  - Gemini 503s: 2, 12 and 7 errors in the three passes (evals run without the fallback).
  - Even at Gemini's best (the 05:56 UTC run, first token p50 0.97 s), TTFT p50 was 1.8 s: router and retrieval take about 1 s before Gemini starts.
- 2026-10-16: Decision 4, fallback, first two candidates (dev ci, each as the primary with a live router; reports `20261016T092724Z` for 4a and `093202Z` for 4b). 4c (Groq gpt-oss-120b) runs on 2026-10-17.
  - 4a, NVIDIA gpt-oss-20b: draft citation pass rate 3 of 7 quotes (0.429), from 3 questions.
    - Regenerations: 5 of 14 drafts.
    - Its own first token: p50 1.18 s (max 2.65 s). End-to-end TTFT p50 2.0 s (14 live answers).
    - False refusal 3 of 15: the router refused x11 and x15, and no sentence held up in x16.
    - No errors.
  - 4b, NVIDIA nemotron-3-super-120b-a12b: pass rate 1 of 1 quote, no regenerations.
    - Its own first token: p50 11.26 s (max 23.07 s), output tokens p50 420 against 4a's 107 (its default reasoning; a reasoning-off setting was not tried).
    - It hit the 30 s answer limit on x06, x11 and x16, 3 of the 4 textual questions.
  - Not too close to call (user rule), so no dev-full runs. The pass rates share one question, so the rule's first step cannot separate them; latency does. Paired, nemotron's first token is +10.1 s slower at p50 (95% CI +3.5 to +14.0, n 13). 4a leads 4b.
  - Fresh router calls add noise: x11 was answered in 3a, refused by the router in 4a, and timed out in 4b.
- 2026-10-16: Decision 4 settled (user decision): NVIDIA gpt-oss-20b (4a) stays `LLM_FALLBACK`, so nothing changes.
  - 4c (Groq gpt-oss-120b) was skipped unrun. A Groq-hosted fallback shares outages with the Groq router, which the fallback also serves, and it spends the gpt-oss-120b allowance shared with FreightAudit and the judge.
  - 4d (NVIDIA-hosted gpt-oss-120b) was proposed as a further candidate and found retired, so it was not an option. One tiny request got 410 ("retired this model"), as on 2026-10-15. The first probe's output was lost to a broken output filter, so two tiny requests went out.
  - The evidence is thin. 4a's draft citation pass rate rests on 7 quotes from 3 questions (3 passed); nemotron's on 1. Nemotron lost on latency, likely because of its default reasoning, which was not tested switched off.
- 2026-10-16: Decision 3's fix (user decision): fix B, the search starts while the router runs. Fix A (hedging the answer call with the fallback) was rejected: the fallback's citations (3 of 7 quotes passed) would make hedged answers worse, and correctness beats latency.
  - **How it works:**
    - `router.guess` reads the tracked companies a question names (by ticker, or by the first word of the name) and its four-digit years.
    - The Answerer starts that search as a task before the router call. It keeps it only when the plan's tickers and years match (`_Early.agrees`), so evidence and answers never change. Otherwise it cancels it and searches the plan's scope.
    - An unused early search still costs CPU (embedding, full text and rerank run in threads), numeric questions included. Stats and eval records carry `early_search`.
  - **Offline check on 3a:** the guess matched the router on 16 of 25 searching questions. All 9 misses were the router leaving tickers empty for a company the question names (x01 Apple, x03 Alphabet, x11 Visa...), which then searched unscoped.
  - **Dev, live** (report `20261016T100134Z`, `--tag=fixb`, 77.5K gpt-oss-20b):
    - The router agreed on 18 of 28 searching questions.
    - On those, paired with 3a, time before Gemini starts went from p50 1,060 to 684 ms. The median change was −268 ms (95% CI −490 to −128, n 16), and the retrieval wait went from 308 to 0 ms.
    - Where the router disagreed (10 questions), nothing changed.
    - End to end, TTFT p50 3.72 s and p95 9.65 s, still bound by Gemini.
- 2026-10-16: Router misses checked before the test run (user request, no quota): no deterministic fill, since questions where the router left out the one company they name are not clearly worse.
  - Three dev runs, each with its own live router replies (`082033Z`, `090721Z`, `100134Z`), with 3, 9 and 5 textual router misses. A miss means the question names exactly one tracked company (`router.guess`) and the router gave no ticker.
  - Retrieval recall@10 as run, misses against the rest: 0.683 against 0.539, 0.614 against 0.833, and 0.840 against 0.462, so better in two samples of three. Answered: 2 of 3 against 7 of 11, 6 of 9 against 4 of 4, and 5 of 5 against 3 of 7.
  - Faithfulness (the judged run only): 9 of 9 sentences against 18 of 19.
  - Paired per question, a search scoped to the named company changes recall@10 in 3 of 15 cases: x06 +0.60, x01 +0.25 (twice), x20 −0.10. The question names the company, so the unscoped search ranks its chunks anyway.
  - The fill would have added the single named company to the plan when the router gave none (dev-tuned, then a dev rerun with `--tag`). It was not built.
- 2026-10-16: Eval reports record the code they measured (user request): the commit, whether the tree has uncommitted changes, and a sha256 over the source files as they stand (`code_version`: tracked and untracked files under services, packages, evals, scripts and infra, plus pyproject.toml and uv.lock, `.gitignore` applied). Data and docs are left out (reports, calibration and golden files, Markdown), so a calibration import between two runs does not change the hash; golden v1 has its own manifest hash. `dirty` checks the same files only (`git status` on that pathspec), so a calibration result or a doc edit written after a commit does not mark a run as measuring uncommitted code. Files are hashed with LF line ends, so a checkout that rewrites line ends (core.autocrlf is on here) keeps the hash. They also record the sha256 of each system prompt and response schema (`prompt_hashes`). Both appear in the JSON, the markdown header and the `eval_runs` row.
- 2026-10-16: Follow-up judge sample (user decision): natural sentences that fail the validator, from 4b first (nemotron, another family than the judge), topped up from 4a, never from 4c (the judge's own model). It is a second sample in `evals/calibration/v1-followup/`, and v1 stays frozen.
  - Drawn: 6 sentences, not about 10. 4b had 2 failing sentences and 4a 5, of which the 2-per-question cap kept 4.
  - Three of them state figures that look derived from cited ones (72% of $75.0 billion as $54.0 billion; an increase of $55.605 billion), so the labels may hold natural negatives this time.
  - Result (2026-10-17): the judge failed 3 of the 4 Claude labeled not supported, all computed figures. It said "yes" to s04 (t07): risks to Chevron's climate aspirations presented as risks to its business. So a natural unsupported sentence can pass the judge.
- 2026-10-17: Test run of golden v1 (numbers in `evals/eval-card.md` and the README). Every miss but TTFT p50 has a named cause:
  - False refusal 0.130: the router sent 3 textual questions out of scope (Known Issues).
  - Citation precision 0.944: one comparison conclusion rated "partly" (c02).
  - Recall@10 0.583 on 6 questions.
  - Floors were written from this report after the user's review (2026-10-17, `--set-floors`). There are 3 retrieval floors and 13 answer floors, under `answer:test:full:gemini:gemini-3.5-flash-lite`. Nothing is tuned on test results: each miss is a known weakness with a v2 idea (README, eval card).
- 2026-10-17: Claude Haiku 5.5 is the answer chain's optional first fallback (user decision). It runs on Anthropic API credits that expire 2026-11-10, through the official `anthropic` SDK (1.15.0).
  - **Chain:** answers go Gemini, then `LLM_ANSWER_FALLBACK` (`anthropic:claude-haiku-5-5`), then NVIDIA. The router falls back to NVIDIA only. The code default (empty) is the free-only chain.
  - **Credits gone (user rule; Anthropic's errors and rate-limits pages agree, read 2026-10-17):**
    - Signals: a 402 `billing_error`; a 400 naming a spend limit; a 429 without `retry-after` (the tier spend cap).
    - The spend-limit 400 reads "You have reached your specified API usage limits", so the match takes "usage limit" too, and also "credit balance".
    - Claude is then off for the rest of the credit period, with one warning line `claude is off for the rest of the credit period`. It is also off from `ANTHROPIC_CREDITS_EXPIRE` (UTC).
    - The flag lives in the process, so a restart learns it again from one refused call.
  - **Rate limits:** a 429 asking for 10 s or less is retried once. A longer one goes to the next model and leaves Claude on.
  - **Request:** thinking off (`{"type": "disabled"}`) at effort low, no sampling parameters, and the shared 1,024-token answer cap (user decision after the first dev run). It is a fallback, so it should be fast, and the primary runs minimal thinking. A refusal (`stop_reason` refusal) fails the call, so the chain moves on.
    - The first dev run used adaptive thinking, which used up the cap (Known Issues).
    - The rerun with thinking off (`--primary-tag=nothink`, router replies cached) had 0 truncated and 0 empty replies.
    - Paired on 54 questions, Claude's own first token went from p95 3.03 s to 1.08 s (95% CI of the difference −3.35 to −1.46 s).
  - **Cost:** `credits_usd` prices each call from its usage at $0.10 / $0.50 per 1M tokens for prompts up to 100K ($0.50 / $2.50 above). It feeds `Usage.cost_usd` and the eval's cost as billed.
  - **Guards at startup:** Claude cannot be `LLM_ROUTER` or `LLM_FALLBACK`; it writes answers only, with no JSON replies, and `LLM_FALLBACK` also routes. It can never be `LLM_JUDGE`, whose reference labels came from Claude.
  - **Evals:** evals pin one model with no fallback, and credits gone end the run with exit 2.
  - **Floors:** the $0 billed floor applies to the free setup only. The floor rule gives billed cost 0 when the run billed nothing, and the efficiency rule otherwise. Answer floors are keyed per primary model (`answer:<split>:<subset>:<provider:model>`), so a Claude run never meets the free setup's floors.
  - Reason: use the credits while they last, without letting a paid model's failure or cost leak into the free setup.
  - Test comparison (user request, 2026-10-17): run on Gemini's exact router replies, with `--router-primary=gemini:gemini-3.5-flash-lite --primary-tag=fair` (`20261017T084716Z-answer-test-full`).
    - Results: numeric 1.000, citation precision 0.958, faithfulness 0.944, false refusal 0.130 (the same 3 router calls).
    - Paired, Haiku's own first token p50 was 0.13 s faster. Credits $0.0145.
    - Findings: n28 hedged over a fact heading, and c12's conclusion was rated "partly".
    - A first comparison (`20261017T082950Z`) asked the router again, because the router's cache key includes the primary. The router routed x13, x14 and x18 as textual there, so separate runs mix router variance into an answer-model comparison. `--router-primary` fixes that.

From step 7 (CI/CD):

- 2026-10-17: The plan was approved with all 8 recommendations plus five user additions (user decision).
  - **Layout:**
    - One `ci.yml` for pull requests, main and manual runs, with publish on main only. Reason: a separate `release.yml` would repeat every job.
    - The required check is `ci-ok`, which fails on any failed or cancelled job. Reason: GitHub counts a skipped job as a passing required check, so an upstream failure must not pass as a skip.
  - **Eval gating:**
    - Evals run only when an eval input changes.
    - Retrieval runs on dev full instead of the ci subset. Reason: it is free, and tighter.
    - The answer suite runs on dev ci with `--no-judge`, so there are 0 gpt-oss-120b tokens on PRs.
    - There is no second answer eval on main. Reason: main cannot read a PR's cache, so it would spend the same quota again.
    - The nightly runs the test split with the judge at 19:00 UTC, only when the inputs' hash moved since the last complete run.
  - **Floors:** CI gates quality, tokens and cost, never latency. Latency stays in the report, marked "not gated" (user addition). Reason: runners are not the production PC.
  - **Exit codes:**
    - Exit 2 is only for a quota or rate limit, and only it says to rerun after the quota resets (user addition).
    - A refused key, credits gone or a retired model exit 4; under `--ci`, so do errored questions, judge errors, setup errors and a setup without floors, each with its reason. Reason: a failure must never pass for a quota problem, FreightAudit's merged-incomplete-exam lesson.
  - **NOT RUN:** a PR without secrets (Dependabot or a fork) shows NOT RUN for the answer eval at the top of the PR comment and the job summary, never as a pass (user addition). There are no Dependabot secrets. Reason: unreviewed dependency code would see them.
  - **Secrets:** only `GEMINI_API_KEY` and `GROQ_API_KEY`, in the answer eval step alone. There is never an Anthropic secret or model, and a lint guard fails on one. `LLM_FALLBACK` points at the router's Groq model in CI only for startup validation.
  - **Trivy (user rule):**
    - Its GitHub Actions and setup-trivy tags, binary 0.69.4 and Docker Hub images 0.69.5 and 0.69.6 were hijacked in March 2026 to steal CI secrets.
    - So it runs from an image pinned by digest, at a version at least 7 days old: 0.75.0, released 2026-10-01. Its digest is the same on Docker Hub, GHCR and ECR, and the tag was never re-pushed.
    - It runs with no token, no secret and no Docker socket; images are scanned from a saved tarball.
    - Trivy replaces pip-audit, which has no severity filter. `--ignore-unfixed` applies.
  - **Corpus asset (user addition):**
    - Its tables are an allowlist: rows only for companies, filings, sections, chunks, financial_facts and alembic_version, plus those tables' own id sequences.
    - Its SQL is scanned for every secret-named value and the SEC contact before it is saved, and its sha256 is pinned in `evals/corpus.py`.
    - The user uploads it publicly as the `corpus-v1` release after reviewing its table list.
  - **Pins:** actions are pinned by commit and tools by digest, each release at least 7 days old when pinned; Dependabot has a 7-day cooldown.
- 2026-10-17: Trivy with dev dependencies found CVE-2026-104852 (HIGH, `@graphql-tools/utils` 11.2.2) in the TS client's codegen. Fixed at the source: `@graphql-codegen/cli` 7.4.3 to 7.4.6 and `client-preset` 6.2.0 to 6.2.3, both released 8 days before, installed with `npm install --before=2026-10-10`. The hoisted utils is now 12.0.3, and the generated clients are unchanged.
- 2026-10-17: The dev floors for CI were written after the user's review. `retrieval:dev:full` comes from `20261017T103956Z`, and `answer:dev:ci:gemini:gemini-3.5-flash-lite` from `20261017T104130Z` (values in the eval card). Answer floors follow the usual rule.
  - Retrieval accuracy floors follow their own rule (user decision): the measured value less one question's share (1/n, n the scored questions), capped at the target. For dev: recall@10 0.613 − 1/14 = 0.542, MRR@10 0.649 − 1/14 = 0.577.
  - Reason:
    - Retrieval calls no model, so the same code on the same corpus gives the same numbers.
    - Its bootstrap interval reflects only which 14 questions the set holds. A floor at the lower bound (recall 0.402) would let a real drop from 0.613 pass.
    - One share still tolerates one near-tie flipping on GitHub's CPUs.
  - Code: `metrics.deterministic_floor`, used by `--set-floors` for the retrieval suite's accuracy metrics. The test-split retrieval floors (0.314 and 0.500) predate it and stay until `--set-floors` runs on a test report again.
- 2026-10-17: The first PR's CI eval failed: correct_refusal 0.800 (4 of 5) against a floor of 0.900. The miss was t07, a time trap: "What risks did Chevron describe in its fiscal 2026 annual report?"
  - Both runs routed it textual for CVX with no fiscal year: the cached 2026-10-16 reply behind the 10:41:30 report, and the live CI run. So the code's time-trap check never fired.
  - In 10:41:30, Gemini's own reply refused. Live in CI, Gemini answered with risks from the FY2025 10-K (`cvx-20251231.htm`, 3 chunk citations), at the same top score (4.026).
  - So it is model variation behind a known router miss (t07's missing year, 2026-10-16). The question is not answerable: no FY2026 10-K exists as of 2026-10-16. No label was changed.
  - The answer path did not change in step 7. Prompt hashes, models, reranker settings, refusal gate, index sha256 and golden manifest are identical. The only answer-path diff (70057d9..bbc9b99) is `evals/calls.py`'s stop message and two stop codes (2 to 4).
- 2026-10-17: Pass/fail metrics take a Wilson score interval, not the percentile bootstrap (user decision): numeric and comparison match, correct and false refusal, router and route accuracy (`harness.BINARY`, `metrics.wilson`).
  - Reason: a bootstrap of n identical results can only resample that result. 5 of 5 gave 1.0 to 1.0, so `floor()` returned min(1.0, 0.9) = 0.9, and any single miss failed.
  - The rule stays min(low, target). `--set-floors` recomputes Wilson from each metric's value and n, so older reports get it too.
  - Pooled pair metrics (coverage, citation precision, faithfulness) keep the cluster bootstrap. Dev ci's coverage range (1.0 to 1.0 over 14 answers) is still collapsed, and its floor stays 0.95.
- 2026-10-17: The ci subset gained 5 should-refuse dev questions, so it holds 10 of 25 (user decision): `harness.CI_EXTRA` = a04, a07, a09, t04, t08.
  - They are the next dev questions in `golden.assign_splits`' seeded rank order (the ranks reproduce the frozen flags exactly), each kind in proportion to dev's should-refuse mix.
  - Golden v1's files are unchanged and still frozen; the test split is untouched.
  - Extra per uncached CI run: about 5.5K gpt-oss-20b and 2 to 4 Gemini calls, with no judge.
- 2026-10-17: Dev ci floors were replaced, which loosens some (user decision). Reason: their ranges had collapsed.
  - They come from one fresh live run of the new subset (`20261017T154912Z`, `--tag=ci-floors-1017 --no-judge`), with `--set-floors ... --replace`, the new code path that may loosen.
  - Numeric 0.92 to 0.676, correct refusal 0.90 to 0.722 (10 of 10), false-refusal ceiling 0.333 to 0.379. Tokens and cost tightened, and live latency floors were added (PC only).
  - Test floors replaced the same day (user decision): computed by code from the saved exam report, with no new run (`--set-floors evals/reports/2026-10-17.json --replace`).
    - Numeric 0.92 to 0.758, correct refusal 0.90 to 0.646, false refusal 0.261 to 0.321.
    - Retrieval recall@10 0.314 to 0.416 and MRR@10 0.500 to 0.667, under the retrieval rule.
    - Reason: one rule applies everywhere, and floors are guards derived from measured results, so this is not tuning.
    - `retrieval:dev:full` was re-derived from its own report, unchanged. No other floor keys exist.
  - The CI floors are a tripwire for large drops, not a precise measure: the numeric floor of 0.676 still lets 6 of 8 pass. The nightly run and the exam give the precise numbers.

From the GraphQL guard fix (before step 8):

- 2026-10-18: GraphQL `answer` takes REST's answer guards through the same code (user decision: fixed first, on its own branch and PR from main, before step 8 builds). `answer_limits_for` hands the resolver `answer_limits` bound to its request, as a dependency, so tests swap it the way they swap `answer_limits`. `timed_answer` holds the 30 s limit for REST and GraphQL. REST keeps its dependency order. Reason: GraphQL answers skipped the 10-a-minute bucket, the daily budget (which fails closed) and the time limit, so with AI on they could spend past `DAILY_AI_TOKEN_BUDGET`.
- 2026-10-18: An answer is in flight from its admission (user decision, same fix). `Answerer.admit(request)` takes the slot and returns `Admitted`, which gives it back at the last event, an error, a cancellation or `aclose()`. The stream route's request-scoped yield dependency closes it after the response. Reason: a stream counted itself only at its first event, so streams opened together could pass `LLM_MAX_INFLIGHT`; and an async generator that never starts never runs its `finally`, so the slot needs an owner outside the generator.

From step 8 (monitoring; design in `docs/monitoring.md`):

- 2026-10-18: Telemetry is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set (user-approved plan). Library code uses only the OpenTelemetry API, which records nothing until `configure_telemetry` installs the SDK, so tests and evals pay nothing. Each process is its own `service.instance.id`, because prefork children pushing the same series would overwrite each other's cumulative counts. Reason: one switch, no cost when off, correct counts per process.
- 2026-10-18: Our own Celery propagation instead of `opentelemetry-instrumentation-celery` (design critique, user OK). Its 0.66b1 leaves the producer span of `send_task` (task unknown on that side) and of a publish that fails (discover's nack on a full fetch queue) open. Ours: `before_task_publish` injects `traceparent` with no span, `task_prerun`/`task_postrun` open and close a consumer span `run/<task>`, `task_failure` sets the error type only. The package was dropped. Reason: no span left open or current; one dependency fewer.
- 2026-10-18: FastAPI's native telemetry runs with `operation_spans: False` (ruling, session 2). With operation spans on, a REST answer runs inside a `fastapi.endpoint` span, so `trace.get_current_span()` in `Answerer.events` would put the answer's outcome on that span instead of the request's. Cost if wrong: one flag. `logs: False` keeps validation inputs out of telemetry; `auto_configure: False` keeps `FASTAPI_OTEL_AUTO_CONFIGURE` from adding a second exporter.
- 2026-10-18: Spans that would live across a `yield` are never made current: answer stages are built when each ends, from `_Run.lap`, and provider stream spans are started and ended without attaching. Search and SEC spans are current, because they live inside plain calls. No span records an exception or a status description (error type only). Reason: SQL errors quote their parameters (the search text), and provider messages can echo prompts.
- 2026-10-18: Metrics come from one registry (`metrics.SPECS`), with units only `s`, `{...}` or none, and labels only from fixed sets. The counters that alerts read are created at 0 for every known label value at process start. The drift test applies the exporter's naming to SPECS and fails on any other `filinglens_*` or `gen_ai_*` name in the dashboards and alerts. Reason: increase() sees the first event after a restart, and a renamed metric cannot silently empty a panel or an alert.
- 2026-10-18: 13 alert rules, each with a firing and a quiet promtool case, and no delivery until step 10 (user decisions and conditions). Ratio rules need a minimum count in their window (LlmProviderErrors at least 4 calls: user condition). TelemetryMissing exists because every alert on the services' metrics would otherwise resolve quietly when telemetry stops.
- 2026-10-18: Query strings keep names only, and a part without `=` or a name over 24 characters becomes `_` (final review). Reason: `parse_qsl` reads a bare part as a name, so `?what+did+apple+say`, or a key pasted without `=`, reached spans and access lines; keys are at least 32 characters.
- 2026-10-18: CitationValidationDegraded divides regenerations by drafts (`filinglens_answer_stage_duration_seconds_count{stage="generate"}`), not by answered answers (final review). Reason: a regeneration can end in a refusal, so the old ratio could fire with no answered draft rewritten, or pass 1; drafts are the unit of the 2-of-53 baseline.
- 2026-10-18: The metric label allowlist is checked once the whole test session ends, over every series any test recorded (root conftest), not in one test (final review). Reason: a test sees only what ran before it.
- 2026-10-18: The end-to-end trace test lives in `services/ingest/tests/test_pipeline.py`, not a new `test_trace.py` (ruling, session 2). Reason: under `--import-mode=importlib` a new module cannot import that file's fake SEC, worker launcher and helpers, and copying them would duplicate about 100 lines. Search telemetry is tested in the integration `test_search.py`, since `search()` needs Postgres and the local models.
- 2026-10-18: The nightly's cron moved from `0 19 * * *` to `17 19 * * *` (19:17 UTC, 03:17 Taipei), replacing the 19:00 UTC of the step 7 decisions; `workflow_dispatch` stays (user decision).
  - Why: `nightly-eval.yml` has never run. GitHub's API showed no runs at 04:37 Taipei, after the 03:00 schedule, though the workflow had been on main since 00:07 Taipei (59ed9fe). Likely cause, not confirmed: GitHub delays or drops scheduled runs on minute 0 under load.
  - What we did: changed the cron and its comment, ran `make actionlint` (no findings), and added a todo item: after the merge, start one run by hand, then check that the next scheduled run happens.
  - Best option: a one-line change, and the manual run tells a broken workflow apart from a missed schedule. A manual run always runs the eval, because the gate skips unchanged inputs on scheduled runs only, so it spends a full nightly's quota.

From the nightly x18 fix (2026-10-18; branch `fix-dangling-citation-markers`, user-approved plan):

- 2026-10-18: Validation fails a sentence that holds a bracketed marker with a digit that is no source id, such as `[12]` or `[D1]` (`validate.STRAY`, checked first in `check_sentence`). The existing regeneration names the marker ("[12] is not one of the sources"), and a sentence that still carries it is dropped. A bracket without a digit, such as `[sic]`, is not flagged (a test row, user addition).
  - What happened: the first manual nightly run (39068994474) exited 4 on "x18 (judge): sentence 1: judged sources [1, 2], cited [1, 2, 12]". Gemini wrote `[12]` for C12. `MARKER` never saw it, so the answer showed a citation number with no citation behind it, and the judge prompt cited a source it did not list.
  - Why here: every entry point validates through `drafting.check`, so one check covers REST, the stream, GraphQL, smoke, record-fixtures and evals.
  - Not a judge retry: the judge cannot rate a source it was never shown. The live replay on the recorded twin (one gpt-oss-120b call) showed the other outcome: it rated the unseen source 12 as not supporting, and `parse` accepted it.
  - Not a harness or judge change: the judge's prompt and schema are frozen with its calibration.
- 2026-10-18: The nightly's report copy lists modified tracked files too (`git ls-files --others --modified`; user: same branch as the validator fix).
  - What happened: run 39068994474's artifact held only the verdict. The full test run is named `evals/reports/<date>.json` by the runner's date. Started at 21:02Z on 10-17, it replaced the committed `2026-10-17.json` in the checkout, and `--others` alone skips a tracked file.
  - What we did: added `--modified`, with a one-line comment. A throwaway repo showed that the new flags list the replaced report and still leave ignored files out. `ci.yml` keeps its line, since CI writes only new `runs/` reports.
- 2026-10-18: The eval never sends the judge a sentence that cites a number with no source (user request). `judge.user_prompt` raises JudgeError first ("sentence 2: given sources [2, 3], cited [2, 3, 12]"), and `AnswerSuite.judged` records it as the question's judge error. So `--ci` exits 4 and no judge call is spent.
  - Why: the live twin replay showed that the judge can rate a source it was never shown, and that `parse` accepts the rating, which would silently skew citation precision. The validator fix keeps such answers out of the API; this keeps the eval honest if a marker arrives another way.
  - Where: `user_prompt` is where the harness and calibrate both build the judge's prompt. Its text for every other answer, `judge.SYSTEM` and `judge.SCHEMA` are unchanged, so the calibration stands.
  - Test: `test_a_number_without_a_source_errors_before_any_judge_call`, on the textual recording's `[12]`. It failed before the change (a judge call was made).

From the step 9 plan (2026-10-18; approved plan: `C:\Users\kwonhyuk\.claude\plans\pasted-content-id-3f93-add-this-cheerful-spring.md`, revision 2):

- 2026-10-18: The financial-section bug (todo.md, formerly "before step 9") is deferred to the next corpus: golden v2, or before step 10 if production is built by a fresh ingest (user decision).
  - What happened: planning step 9 had to say whether to fix it first. An agent re-parsed and re-chunked the 30 cached 10-Ks offline with the repo's parser (the dev Postgres was stopped, so no SQL ran). The result matched the seeded data: 11,263 chunks, and all 90 golden pool candidates of JPM, CVX, NVDA and PLD reproduced exactly.
  - Why defer:
    - A code-only fix changes nothing step 9 shows, because the UI shows the dev database.
    - Re-parsing dev removes 14 of golden v1's gold chunk ids (x09, x10, x19), because chunk ids hash the item. Every local eval would then exit 3 until golden v2.
    - Re-parsing also changes the index hash, so every cached router and primary reply would be void. The answer and judge prompts show `Item {item}`, so judge calls would go live too.
    - CI and the nightly restore corpus-v1, and `services/ingest` is not an eval input, so they gain nothing from an early fix.
    - The fix itself needs a data-model decision. A section is one range, unique per (filing, item); all four filings already have pointer sections 7, 7A and 8; and JPM's market-risk part sits inside its MD&A. So correct labels probably mean a migration.
  - What we did: todo.md holds the findings. README and context.md name the four filings. The step 9 demo export refuses any cited chunk inside the four sections, and the UI shows the item as stored.
- 2026-10-18: Correction to the 2026-10-15 entry on separate financial sections (Known Issues). The cached filings show:
  - 4 filings, not 5. XOM is not in the corpus; COP replaced it.
  - JPM (`0001628280-26-008131`) keeps MD&A, market risk and the statements under Item 15: 813 of its 938 chunks.
  - CVX (`0000093410-26-000078`) keeps them under **Item 14**, not 15 or 16: 275 chunks.
  - NVDA (`0001045810-26-000021`) and PLD (`0001193125-26-051453`) have real Items 7 and 7A. Only their Item 8 content sits in Item 15 (84 chunks) and Item 16 (201 chunks).
  - In all, 1,373 chunks, 12.2% of the corpus.
  - Why the parser does it: the financial section's headings ("Management's discussion and analysis", "Consolidated...", "Notes to...") never start with "Item", so they stay in whichever item heading comes before them.
- 2026-10-18: Step 9 ships as three pull requests, each from main after the one before merges (user decisions):
  - **A:** GraphQL over GET off, the unused WebSocket route off, and the Retry-After description fixed.
  - **B1:** the API lookups by id and links (the step's "resolvers"), the contracts, and the `clients/ts` fixes.
  - **B2:** the web, BFF, sign-in, demo snapshot, Playwright and axe, and the CI web job.
  - Why split (user): each diff stays reviewable, the API change is verified on its own, and a fresh session can take B2.
  - Other decisions:
    - `/demo` is public and linked from the login page.
    - The demo answers are 8 records from the exam report `evals/reports/2026-10-17.json`, so no model call is made.
    - The Playwright suite runs against a mock API that replays the demo snapshot.
    - Dependencies approved: `@playwright/test` and `@axe-core/playwright` (web devDependencies, exact pins released at least 7 days before).
- 2026-10-18: GraphQL takes POST only (PR A). User rule: GET stays only if something uses it.
  - What happened: Strawberry's `GraphQLRouter` registers GET, POST and WebSocket routes. A GET could run `answer` and spend model quota, and the WebSocket route was mounted with no Subscription type.
  - Why off:
    - nothing sends GraphQL over GET: both generated clients POST, there is no GraphiQL page (`graphql_ide=None`), and web, evals, scripts and tests send none;
    - grep found no WebSocket or subscription use.
  - What we did:
    - `main.py` keeps only the router's POST route (`graphql_router`), so a GET gets 405 from routing before the key check, the rate limit or a resolver.
    - Tests: a GET of `answer` spends nothing (no backend call, no answer token) and a POST works; the router has one POST route and no WebSocket route.
    - Best option: one filter covers both routes, with no Strawberry setting that would leave the route mounted.
- 2026-10-18: The 503 Retry-After rules were written from the code (PR A).
  - What happened: the API description and the 503 response doc said every 503 carries Retry-After, but `ai_unavailable` has none when AI is switched off, or when the last model refused the key, has no credits or was retired.
  - What we did:
    - Read every 503 raise site (budget.check, LiveBackend, providers.failure with `_final`, Answerer.admit, search paging, the ingest publish).
    - Rewrote the description and the doc.
    - Added `test_a_503_carries_retry_after_only_when_waiting_helps`: 12 rows, each raised by the production code and sent through the REST route.
  - Why it matters: the BFF reads "no Retry-After" as "switched off, show the saved answers".
- 2026-10-18: The GraphQL lookups by id (PR B1) take 0 to 20 ids, not the plan's 1 to 20. Each id is 1 to 64 characters.
  - What happened: building `Sources`, one query asks for chunks and facts together, and an answer may cite only one kind. With a lower bound of 1, the BFF would need two queries or `@include`.
  - What we did:
    - an empty list returns an empty list without a lookup;
    - more than 20 ids, or an id of 0 or over 64 characters, gives `invalid_input`;
    - an id that cannot exist is simply not found;
    - the links (`Chunk.section`, `Chunk.filing`, `Filing.company`, `FinancialFact.company`) use the pre-joined rows on the citation path, and one lookup per item elsewhere (a `ponytail:` comment names the DataLoader upgrade).
  - Best option: one query per answer, and no new error case for the UI.
- 2026-10-18: The API description's "a broker that refused a job" now reads "refused a job or could not be reached".
  - What happened: the user asked whether any 503 comes from a dependency being down, since the new text dropped "a dependency is down".
  - The answer:
    - Redis down for the budget check gives `ai_unavailable` with Retry-After 30;
    - RabbitMQ refusing or unreachable on an ingest publish gives `overloaded` with Retry-After 5;
    - `/readyz` answers 503 when Postgres, RabbitMQ or Redis is unreachable;
    - Postgres down on data routes is a 500.
  - What we did: sharpened the broker phrase in PR B1.
- 2026-10-18: The answer above, checked against the code when B1 was finished (the handoff had marked it not confirmed):
  - `budget.py:62-65` turns a `RedisError` into `ai_unavailable` with Retry-After 30.
  - `backend.py:332-335` turns kombu's `OperationalError` or an `OSError` on the job publish into `overloaded` with Retry-After 5. That covers a broker that refuses the job and one that cannot be reached.
  - `main.py:183`: `/readyz` answers 503.
  - No code in `services/api/src` maps a database error, so Postgres down on a data route is the catch-all 500.
- 2026-10-18: The `clients/ts` error and call shape for B2's BFF (PR B1; plan B2.1 and B2.2). B2 sorts a failure into offline (network error, timeout, 5xx, GraphQL `internal`), misconfigured (401 or 403) or a problem with its code.
  - **`ApiError`** holds `status`, `code`, the detail as its `message`, `retryAfterS` and `requestId`.
  - **`readApiError(response, requestId?)`:**
    - A problem body gives its `code` and `detail`.
    - Anything else, such as a proxy's page, a body that is not JSON under a JSON type, or a problem without a detail, gives code `unexpected_response` or detail `HTTP <status>`.
    - Retry-After is read as delta-seconds only. The API never sends a date, and a date gives no value.
    - The request id comes from the reply's `X-Request-ID` (the API echoes it), else from the one sent.
  - **`executeGraphql`:**
    - Its fifth parameter is `CallOptions {signal, timeoutMs, requestId}`; it used to be `timeoutMs`, and nothing called it yet.
    - A GraphQL error throws `ApiError` with status 200 and the first error's `extensions.code`. An error without one, such as a query validation error, gives `unexpected_response`.
  - **Abort and timeout:** a caller's abort rejects with `AbortError` and the timeout with `TimeoutError` (`AbortSignal.any`). So B2 can tell a browser that went away from a stalled API.
  - **Request ids:** every call sends `X-Request-ID`, a uuid4 when the caller gives none. It fits the API's pattern `[A-Za-z0-9._-]{1,64}`.
  - Reason: one error type that carries everything B2's classification and its log line need, and no new error case for the UI.
- 2026-10-18: `clients/ts` imports end in `.ts` (`allowImportingTsExtensions`), so `node --test` loads it with Node's type stripping (PR B1).
  - **For B2:** web's tsconfig must allow `.ts` imports too, or TypeScript reports TS5097 in the `clients/ts` files it checks.
  - **`@types/node`** (for `node:test` in `index.test.ts`) comes from the lock's transitive dev copy (26.6.5). It was not added as a direct dependency.
  - **The dependency move:** moving `@graphql-typed-document-node/core` 3.2.0 to dependencies made npm drop `dev: true` from `graphql` 16.14.2, its peer. B2's `npm ci --omit=dev` in `clients/ts` therefore installs graphql too.
- 2026-10-18: Correction to the plan's eval check ("From `services/api` the harness imports only answering, `limits.ANSWER_TIMEOUT_S`, schemas"). Importing those three loads `filinglens_api.backend` and `problems` too, because `limits.py` imports `Backend` from `backend`. Listed from `sys.modules` after the harness's three imports.
  - What it means: a change to `backend.py` is safe for the eval only while the harness calls none of the changed code. B1's changes there (`_fact`, `ChunkSource`, `FactSource`, the lookups) are never called by it. `graph.py` and `main.py` are never loaded.
- 2026-10-18: B1's final review (fresh subagent, verdict "with fixes", no Critical) led to one fix and two rulings.
  - **Fixed, the REST client throws `ApiError`:** `createApiClient` now throws `ApiError` from inside its fetch for any reply that is not ok.
    - What happened: openapi-fetch reads an error reply's body itself (`let error = await response.text()`), so `readApiError` on the response returned `unexpected_response` for a real 503 problem.
    - Best option: both entry points now fail the same way, which is what B2's classification needs.
  - **Ruling, ids per call:** `MAX_IDS` stays 20, as the plan says.
    - What happened: an answer can cite more than 20 facts, one per company and year with no cap (`answering.py:348-354`), while chunks stop at 12. A 21st fact id fails the whole `Sources` query, because both root fields are non-null.
    - What we did: the `IDS` description now says "per call", and B2's BFF sends fact ids in batches of 20.
    - Why: the fact count has no hard bound, so B2 must batch at any cap.
  - **Ruling, fan-out deferred to step 10:** B1's links make the schema cyclic, and off the citation path each link is one backend query per item. The reviewer's 222-byte query made 10,101 `get_chunks` calls.
    - Why defer: nothing reaches the API before step 10, and only the BFF holds the key, sending fixed documents. The plan already puts GraphQL depth limits in step 10.
    - The step 10 note now names a depth limit of 6 (the reviewer measured it as the smallest that passes every operation), an alias limit and a DataLoader.
- 2026-10-18: User decisions on B1, after the review:
  - `main.py`'s description change stays in B1.
  - The GraphQL depth and alias limits go in now, not in step 10.
  - An id with a NUL is refused as `invalid_input`.
- 2026-10-18: GraphQL limits in B1 (`graph.py`).
  - **The limits:** `QueryDepthLimiter(max_depth=6)` and `MaxAliasesLimiter(max_alias_count=0)`. Both are validation rules, so a query past them is refused before any resolver runs.
  - **Depth 6:** the user's number. Strawberry counts a root field as depth 0, and Coverage and Filings put their leaves at depth 6. Coverage is the deepest query B2's web needs; `Sources` reaches depth 3.
  - **No aliases:** the same rule as for depth, the smallest value every client operation passes. No operation uses an alias, and each alias would multiply what a query may look up.
  - **Factories:** the limiters are passed as `lambda: ...`, because Strawberry 0.334.4 warns that passing extension instances is deprecated.
  - **What stays open:** within depth 6, a cited chunk's filing still reaches up to 100 listed chunks and facts. So one request can still make roughly 6,000 per-item lookups: about 4,000 `get_chunks` and 2,000 `get_company` (an estimate from 20 ids, `first: 100`, and two lookups per chunk). Step 10's DataLoader closes that.
  - **The links test:** it now reaches the links off the citation path under a cited chunk's filing, since its old path nested to depth 8.
- 2026-10-18: `_ids` refuses an id that holds a NUL (`"\x00"`), with the message "ids takes at most 20 ids, each 1 to 64 characters with no NUL."
  - Why: Postgres refuses a NUL in a text parameter, so a NUL chunk id came back as a masked `internal`, which B2 would read as offline.
  - Pinned: an id with another control character (`"\x01"`) is still looked up and simply not found.
  - Open: `concept` in `Filing.facts` still lets a NUL reach Postgres (step 10 note).

From PR B2 (2026-10-19, branch `step-9-web-b2`):

- 2026-10-19: Dependabot's npm entry ignores typescript's major updates (user decision; `.github/dependabot.yml`).
  - What happened: Dependabot's npm group pull request #3 failed CI. It bumps typescript 5.9.3 to 7.0.2, and openapi-typescript 7.13.0 (a `clients/ts` devDependency, its newest version) accepts only `typescript ^5.x`, so `npm ci` stops with ERESOLVE in the contracts job. Source: the user's reading of the CI run; the peer range was confirmed in `clients/ts/node_modules/openapi-typescript/package.json`.
  - What we did: the npm entry gained `ignore: [{dependency-name: typescript, update-types: ["version-update:semver-major"]}]`, with a comment saying why and when to lift it. The file still parses (checked with PyYAML).
  - Why this option: it fixes the cause where Dependabot proposes the bump. `--legacy-peer-deps` or `--force` would type-check the clients with a TypeScript the generator does not support (user rule: neither). Minor and patch updates of typescript still come, for web and `clients/ts` alike, so both stay on one TypeScript.
  - Lift it once an openapi-typescript release accepts typescript 7.
  - Not confirmed: how Dependabot treats the open #3 once the rule is on main. The user checks it after the merge, and closes it if it still holds typescript 7.
- 2026-10-19: Rulings made while building B2 (no user decision needed; each costs little if wrong):
  - **No `@filinglens/client` path alias** (the plan named one). `node --test` cannot resolve tsconfig paths, and `lib/errors.ts` needs `ApiError` under it, so web imports `../../clients/ts/index.ts` everywhere: one import style.
  - **One module for three guards:** `lib/guards.ts` holds `next=`, the origin rule and the limiter.
  - **Password bounds:** `parsePhc` takes m 19456 (OWASP's floor) to 1048576 KiB, t 2 to 10, p 1 to 16, a salt of 8+ bytes (RFC 9106's floor) and a hash of 16 to 64 bytes; `hash-password` writes m=65536, t=3, p=4 (RFC 9106's second recommended option) and asks for 12+ characters.
  - **The test vector:** the argon2 reference implementation's PHC string for "password" and "somesalt", which exercises our parsing and verification. RFC 9106's own vector (section 5.3) needs a secret and associated data that sign-in never uses. Node's `crypto.argon2Sync` matched it once in a scratch run (tag `0d640df5...e659`).
  - **The Ask button is `aria-disabled` while an answer runs, not `disabled`:** a disabled button drops the keyboard user's focus, and the plan says focus never moves.
  - **Card and link names:** GraphQL's `FORM_10K` reads "10-K" (`formLabel`). A fact's link names its period end, because its fiscal year is the reporting filing's: Tesla's 2024 net income, cited from the FY2025 10-K, carries fiscal year 2025.
  - **Cursors:** the demo coverage cursor is the last company's CIK, and the mock API's cursor is the base64url of an index, so a cursor neither knows goes to the first page.
  - **The export:** it overrides `rate_limit` (an operator tool, so no Redis), and sends the whole `clients/operations.graphql` with an `operationName`, so it runs the web's exact operations.
  - **Versions:** `@playwright/test` 1.64.0, not 1.64.1 (released 5 days before), uses the cached headless shell, revision 1248. `@axe-core/playwright` 4.13.0, since 4.14.0 was 4 days old. `npm install --before=2026-10-12` kept every resolved package at least 7 days old (axe-core 4.13.0).
  - **Playwright workers: 4.** With the default (half the logical cores), one run here failed on `net::ERR_NO_BUFFER_SPACE`. Three runs in a row then passed with 4 (the calibration knob: raise it if a bigger machine allows).
- 2026-10-19: The BFF's origin rule compares `Origin`'s host with the `Host` header, not with the request URL.
  - What happened: on Playwright's first run, `POST /api/sources` with `Origin: http://127.0.0.1:3102` got 403, and signing out raised a CSP `form-action` report, so 3 specs failed. Browser fetches had passed through `Sec-Fetch-Site: same-origin`.
  - Why (confirmed with curl on a running build): Next 16.3.8 builds a route handler's request URL on localhost. `/logout`'s redirect went to `http://localhost:3102/login`, another origin to the browser, so CSP blocked the redirect, and `request.nextUrl.origin` never equalled the page's origin. The proxy's own redirects carried the right host.
  - What we did, test first: `isSameOrigin(headers)` passes `Sec-Fetch-Site: same-origin`, or an `Origin` whose host equals `Host` (new rows: another host, no Host). `/logout` answers with a relative `Location: /login`. Best option: the Host header is what the browser asked for, here and behind Vercel, and a cross-site page cannot change it.
- 2026-10-19: B2's final review (a fresh subagent, verdict "ready with fixes", no Critical). One fix pass, each fix tested first:
  - **Limiter race (Important):** the limiter counted a failure only after argon2, so parallel sign-ins all passed the check: 50 at once got 50 guesses and queued 50 argon2 jobs. `attempt(key)` now checks and counts in one synchronous step before argon2, and a success resets. Test: 10 synchronous attempts let only 5 through (red: `attempt` did not exist).
  - **Node version (Important):** `crypto.argon2` is new in Node 24.7, so the README's "Node 22.18+" could not sign in or hash a password. README now says 24.7+, and `web/package.json` has `engines.node >=24.7` (Vercel reads it in step 10). Not testable by a red run; the lockfile changed only its root entry.
  - **Configuration error untested (Important):** the mock answers 401 for the cursor `e2e-rejected` and the question `e2e: rejected`, and a GraphQL `rate_limited` for `e2e-error`. `config.spec.ts` checks the configuration-error page (request id, URL unchanged, axe, 390 px), Ask's key message, and `error.tsx` (axe, 390 px). Red check: a build whose coverage page sent a rejected key to the demo failed the first spec.
  - **Re-graded Minor to Important, the sign-in form:** `disabled={pending}` dropped keyboard focus to `<body>`, and a repeated "Wrong password." left the live region's text unchanged, so screen readers heard nothing. The button is `aria-disabled` with a pending guard, and each attempt renders a new message node. Why re-graded: the plan's accessibility rules (focus never moves; errors announced), and a screen reader user got silence on a second failure. Test (red: focus fell to `<body>`): keyboard submits keep focus on the button and replace the message node; the lockout file now runs in order.
  - **Re-graded Minor to Important, sign-out from the offline demo:** while the API is offline every live page lands on the demo, whose header offered only "Sign in", so a signed-in visitor could not sign out. In production the backend sits on a PC that is often off, so this is the normal state. The demo header now shows Sign out with a session. Test (red: no button): sign out from `/demo?offline=1`.
  - **Deferred minors (todo.md, B2 review minors):** the proxy accepts an empty-key token when `SESSION_SECRET` is missing (the startup check stops such a server first); leaving Ask keeps the answer stream running; a failed sources lookup is silent, and a late network error relabels a finished answer; a browser that leaves is logged as `failure: offline`; the snapshot's line endings are not pinned (`newline="\n"` or `.gitattributes`).
  - **Ruled, the reviewer's "declined to judge" list (22 lines):** each stands as the plan designed it or as step 10 covers it: stateless sessions with no revocation, the per-instance limiter and `x-real-ip` on Vercel, one local bucket, Host-header trust, no HSTS locally, "switched off" wording for every 503 without Retry-After, offline meaning `internal` or a non-API reply rather than every 5xx (documented), reflow checked at 390 px. Cost if wrong: small changes in step 10.
- 2026-10-19: One Playwright run showed "Internal Server Error" right after sign-in (the setup project), so 48 specs did not run.
  - Why: not confirmed. The web servers' output was not piped then, and it did not come back in 6 later runs.
  - What we did: `stdout: "pipe"` on both web servers, so their JSON lines appear in the run's output (CI's included) if it returns.
- 2026-10-19: Correction to the entry above: that run did pipe the web servers' stderr, since Playwright pipes a web server's stderr by default (`stderr: "pipe"`; only `stdout` defaults to `"ignore"`, per its `test.d.ts`). The run's whole output went to a scratch log (`pw.log`), only its summary lines were read, and a later run overwrote the file. So Next's own error lines may have been there, unread. Lesson: when a run fails, read its whole log before another run overwrites it. todo.md's watch item says what the output shows now.
- 2026-10-19: Two of B2's review minors fixed before shipping (user decision; the other three moved to B3, todo.md). Each test first:
  - **Proxy secret:** `verifySession` returns false when the secret is missing or shorter than `MIN_SECRET` (32), which `lib/settings.ts` now exports, so the startup check and the gate share one minimum. `proxy.ts` passes `process.env.SESSION_SECRET` as is, no longer `?? ""`. Why it mattered: anyone can compute an HMAC under an empty key, so with the variable missing, a forged cookie would have passed the gate (the startup check stops such a server first, and the pages fail closed). Test: an empty secret, a 31-character one and `undefined` sign no one in (red: `actual: true`).
  - **Ruling:** the guard sits in `verifySession`, which the proxy calls, not in `proxy.ts` itself as the user's wording put it. Why: `node --test` cannot import `proxy.ts` (`next` has no exports map, so Node's ESM resolver does not find `next/server`: `ERR_MODULE_NOT_FOUND`), and e2e cannot reach it, since the startup check exits before the proxy runs. Both callers (`proxy.ts`, `lib/server.ts`) go through `verifySession`. Cost if wrong: one line moved into `proxy.ts`, untested.
  - **Snapshot line endings:** `write_snapshot` in `scripts/export_demo.py` writes with `newline="\n"`, and `.gitattributes` keeps `web/demo/**` LF (`text eol=lf`). Test: a written snapshot holds LF only (red on Windows: `b'{\r\n...'`).
    - Why CRLF before: `Path.write_text` without `newline` writes the platform's line ending. Why `.gitattributes` too: this PC has `core.autocrlf=true`, which would check the file out with CRLF again.
  - **The snapshot file** needed only its line endings changed: all 1,132 lines ended in CRLF. No re-export, no database. A scratch script parsed the file, wrote it through the fixed `write_snapshot` to a trial file, and checked the result equals the old bytes with each CRLF turned to LF. Only then did it write `web/demo/snapshot.json` the same way: 46,989 bytes to 45,857, sha256 `341e2e2c...` to `7a8d0311...`.
    - Why this way: it runs the project's own writer, as a generator run would, instead of an ad-hoc edit. The byte check proves that nothing but the line endings changed.

From the Dependabot follow-ups (2026-10-19, branch `fix/dependabot-follow-ups`):

- 2026-10-19: Dependabot ignores the python image's new minors and majors and `@types/node` 25 and up, and `clients/ts` takes graphql 17.0.2 (user decisions; `.github/dependabot.yml`, `clients/ts/package.json`).
  - **Python image (docker entry, `/infra`):** `update-types: ["version-update:semver-major", "version-update:semver-minor"]` for `python`. Why (user): a move to a new Python changes `.python-version`, the uv lock, CI and the image together, so a Dependabot PR that moves only the image, like #2 (Python 3.14), is the wrong unit. Patch releases of 3.12 still come, and so do digest refreshes of the pinned tag.
    - **Ruling, how the rule ignores:** `update-types`, not a fixed range such as `versions: [">=3.13"]`. `update-types` counts from the image's current tag, so the planned move needs no edit here and the new Python's patches keep coming. A fixed range would need an edit in that move and, if forgotten, would block the new Python's own patches. So the comment's "when to lift it" is: only if new Pythons should come as Dependabot PRs again. Cost if wrong: a one-line change.
    - Not confirmed: that Dependabot reads the minor of a suffixed, digest-pinned tag (`3.12.15-slim-trixie@sha256:...`) as expected. #2 closing after the merge confirms it.
  - **`@types/node` (npm entry):** `versions: [">=25"]`, because the app runs on Node 24 (CI's `node-version: 24`, web's `engines` `>=24.7`). The range names the runtime's major, so 24.x minors and patches still come. Lift it when the runtime moves. It applies to web's direct `@types/node` (24.19.2). With no `allow` option, version updates touch only direct dependencies, so `clients/ts`'s transitive copy (26.6.5, through `@types/ws`) is not covered and stays a B1 minor (todo.md).
  - **graphql 17.0.2 in `clients/ts`:** taken, so the npm entry has no graphql rule.
    - Support: every graphql peer range in `clients/ts/package-lock.json` accepts `^17.0.0`: `@graphql-codegen/cli` 7.4.6, `client-preset` 6.2.3 and the other codegen packages, every `@graphql-tools/*`, graphql-config, graphql-tag, graphql-ws (`^17`), `@ardatan/relay-compiler` (`*`) and `@graphql-typed-document-node/core` 3.2.0. No package depends on graphql directly, so the lock keeps one copy. 17.0.2's engines accept Node 24 (`^22.0.0 || ^24.0.0 || ^25.0.0 || >=26.0.0`), and it was released on 2026-07-03, past the 7-day rule.
    - Install: `npm --prefix clients/ts install graphql@17.0.2 --save-exact --before=2026-10-12`. No ERESOLVE, and the lock changed only graphql's own entry (version, tarball, integrity, engines).
    - Checks: `make contracts-check` changed no generated file's content. It listed the two package files (unstaged) and three ariadne files that differed only in CRLF line endings (2026-10-14 pitfall). `npm --prefix clients/ts test` passed 18. The web job's install path (`npm ci --omit=dev` in `clients/ts`) installs graphql 17.0.2, and web's typecheck and 77 units pass.
    - Runtime: `clients/ts` sends string documents (`TypedDocumentString`), so nothing imports graphql at runtime. It is installed with the runtime packages only as the peer of `@graphql-typed-document-node/core` (2026-10-18 entry).
  - **After the merge (user):** #2 should close, and #11 close or be replaced; next 16.4.0 can come back on its own. Not confirmed: when Dependabot rechecks open PRs after a config change. The user reports what happened (todo.md).
  - **Lesson, restoring CRLF-only generated files:** `git checkout HEAD -- <paths>` skips files whose index entries git already counts as clean, so it rewrote only the 3 of 12 that `git status` listed. Touching the others first made git rewrite them too. Check the result with `cmp` against `git show HEAD:<path>`.

From PR B3 (2026-10-19, branch `step-9-web-b3`):

- 2026-10-19: B3 fixed B2's three deferred review minors (user decision), each test first.
  - **Leaving Ask:** Ask keeps the running question's AbortController in a ref. A `useEffect` cleanup aborts it when Ask unmounts, and each new question aborts the one before. Both fetches (`/api/answers`, `/api/sources`) take its signal. An aborted request shows nothing and leaves `busy` alone, so a newer question keeps it.
    - Why a cleanup is enough: without `cacheComponents`, as here, a Link navigation unmounts the page. With it, Next hides pages in `<Activity>`, which also runs effect cleanups (`next/dist/docs/01-app/02-guides/preserving-ui-state.md`).
    - The abort travels on: the browser's abort closes the BFF's request, Next aborts `request.signal` with `ResponseAborted`, and the API fetch, which takes that signal, closes the API's stream.
    - **Test:** the mock API records a stream the web closed before it finished (`res` closes before `writableFinished`), by question, and answers `GET /e2e/cut?question=...` (with the key). The spec asks a unique `e2e: slow <uuid>` (about 3 s of draft), leaves through the header's Coverage link, and polls the mock. Red: never cut, since the stream ran to its end.
    - **Pitfall:** Chromium, as Playwright sees it, reports every `/api/answers` stream that ends as `requestfailed` with `net::ERR_ABORTED`, even one that finished on a page left open (a temporary spec showed it at 3,334 ms, the stream's natural end). So the first version of the test, which waited for ERR_ABORTED, passed without the fix. Request events cannot tell an abort from a finished stream, so the check moved to the mock. The temporary spec was deleted.
    - **Ruling, no test for the abort before a new question:** the busy guard turns away a second question while one streams, and React re-renders between two user events. Only two `requestSubmit()` calls in one task reach Ask together (React 19 flushes between events only to restore controlled inputs). A test built on that would rest on React's batching, and the first request can be cancelled before it reaches the network, where neither Playwright nor the mock sees it. Kept as asked, as defence in depth. Cost if wrong: one more spec.
  - **Sources failure:** `showSources(done, signal)` holds its own try. An error reply or a network error keeps the answer, shows "Sources could not be loaded." under the Sources heading (`data-testid="sources-error"`, the bare `note` class, like the degraded note), and appends it to the status line. The stream's catch-all ("The web server could not be reached.") can no longer catch a sources failure.
    - **Ruling, the status line too:** B2.4's rule is one polite status line that announces the result, so the note is announced there as well as shown. Cost if wrong: one string.
    - **Tests:** `page.route` fulfils `/api/sources` with a 503, or aborts it. Each must show the note, keep "Source 1" on its card and pass axe (red: no note). A guard, green before and after, aborts `/api/answers` and expects the catch-all with its demo link, so the stream keeps it.
  - **Log label:** `failureLabel(error, failure)` in `lib/errors.ts`. `AbortError` (the caller's abort) and `ResponseAborted` (Next aborts a route's `request.signal` with it when the browser disconnects; `next-request.js`) give `client_aborted` at info. Anything else keeps `failure.kind` at warn. `call()` in `lib/server.ts` logs with it.
    - **Ruling:** the decision sits in `lib/errors.ts`, because `node --test` cannot import `lib/server.ts` (`server-only`, `next/headers`). Cost if wrong: two lines moved back, untested.
    - **Test:** the two aborts give `client_aborted` at info, and a timeout and a network error stay `offline` at warn (red: `offline` at warn for the aborts). No run shows the label: the e2e suite never aborts before the API answers.

From the design round (2026-10-19, branch `step-9-design`):

- 2026-10-19: The web app's own visual design, "paper and ink" (user request; `docs/design.md` holds the direction, `web/app/globals.css` the whole of it). `_design-reference` was not opened, listed or searched: the user compares this design with one made separately. Every search stayed inside the repo.
  - **Why this direction:** analysts read an answer, then check it against the filing. So the answer reads like a research note (serif, 19 px). Citations are pills that lead to their cards, and each card reads like an exhibit with the filing's words muted and the cited words in full ink under a highlighter. Before, the default look made the answer and the page chrome alike, and a long passage buried its quote.
  - **System fonts only:** no download or layout shift, the CSP's `font-src 'self'` stays as it is, and it follows FreightAudit's lesson of fonts swapping mid-screenshot. Screenshots therefore show each system's fonts (Windows here).
  - **Two columns from 64rem**, with the answer column `position: sticky`: each passage sits beside the sentence that cites it. The DOM order is unchanged, so the keyboard spec's focus order holds. Known limit: a column taller than the window stays partly hidden while pinned; the longest saved answer fits 800 px.
  - **Contrast:** the light and dark tokens were computed with the WCAG formula before any CSS was written. The lowest text pair in use is 5.22:1 (labels and notes on the light paper), and the lowest border or ring is 4.06:1 (field borders on the paper). axe passes on all 54 screenshots as well as in the suite.
  - **Citation pills stay inline**, in the sans face, smaller and bolder than the serif text. axe's `link-in-text-block` passes on the change of font, size or weight, and WCAG 2.5.8 exempts a target inline in a sentence.
  - **Markup, wrappers and class names only:** `answer-main` around the answer column; "Source n" in its own span inside the card heading, so the heading's text is unchanged (`sourceLabel` now feeds both it and the `[n]` link's name); `value` and `accession` on two fact rows; `ticker` and `cik` in the coverage table; `offline` on the demo banner; `ask-form` and `result` in Ask; the demo's sections renamed from `answer` to `saved`, since `answer` is now the layout grid.
  - **Ruling, "Sources" lines up with "Answer":** on Ask from 64rem, `.result .sources` moves up by the label's line height and the gap below it (`calc(-1.55 * 0.8125rem - 1rem)`, commented in the CSS). Cost if wrong: a few pixels out of line if the label's size changes.
  - **Ruling, `[n]` keeps its brackets inside the pill:** copying an answer keeps its markers. Cost if wrong: a change of taste.
  - **Screenshots:** `npm run screens` (`playwright.screens.config.ts` reuses the suite's servers and sign-in; `e2e/screens.ts` holds 18 screens in light, dark at 1280 by 800, and phone at 390 by 844) runs axe on each screen, then writes `docs/screenshots/ui/<screen>-<variant>.png`. `SCREENS_DIR` sends them elsewhere: the "before" set went to the scratchpad.
    - **Ruling, `offline` is shot at the top only:** below its banner it is the demo page, already shot in full as `demo`. That cut the set from 13 MB to 8.6 MB, since the two long pages took about 1.4 MB a shot. Cost if wrong: three more full-page shots.
  - **Pitfall:** a full-page screenshot shows a sticky column where it sits before any scroll, so the left column looks empty beside long sources. On screen it stays in view.
  - **No side stripes (the impeccable design hook):** at the end of the round, the hook flagged `.note`'s 3 px left border as a "side-tab", "the most recognizable tell of AI-generated UIs". It was a real problem by the direction's own rule (no decoration), and three more elements carried the same stripe without being flagged. So the stripes went: the banners and boxes keep a tint and a hairline in their own color, a note gets the draft's dashed outline (dashed now always means incomplete), and the jumped-to card a full blue outline. Nothing was suppressed. The passage's thin quote rule stays: a rule beside a quotation is typography, not a card's tab.

From the mockup style round (2026-10-19, branch `step-9-mockup-style`):

- 2026-10-19: The user compared the design round with the separately made mockup and chose the mockup's style, with one change: a bigger sources panel (user request). The mockup was opened read only, from `_design-reference/filinglens/mockup` (12 screenshots and README.md), once the user allowed it, and nothing from it was copied into the repo. The header's mark is a new drawing of the same idea (a filing under a magnifier), an SVG mask in the CSS.
  - **Sources beside the whole column, not inside the answer:** the user wants the panel half the width and the window's full height. Inside the answer section, as in the design round, it would start below the question box, about 400 px down, so its lower half would sit below the window at first. So `SourceList` became the answer section's sibling, in a grid beside the column (`div.ask`). The DOM order, the headings and the focus order are unchanged; only the region nesting moved, and Answer and Sources are now sibling regions. One test followed: the refusal test now looks for "Sources" on the whole page, or it would pass for nothing.
  - **Ruling, the panel's height:** on Ask it is always the window's height less 32 px (`height`), as asked. On the demo it is as tall as its sources need, up to that (`max-height`), since eight full-height panels would leave the page mostly empty. Cost if wrong: one CSS line.
  - **Ruling, the right half stays empty before the first answer:** one column that splits when sources arrive would change the question box's width with every question, since each new question empties the result. Cost if wrong: one `:has()` rule.
  - **The quote into view:** a citation keeps its normal jump (URL, `:target`, focus; the keyboard spec relies on it). A document click listener (`components/quote-in-view.tsx`) waits one frame, then moves only the panel's `scrollTop` to centre the `mark` when it is out of view. Not `mark.scrollIntoView()`: that also scrolls the page, which is mid smooth scroll after the jump, and the two scrolls would fight. On a phone the panel does not scroll, so nothing changes there.
    - **Test:** a 1280 by 360 window, so x02's first quote starts below the card's first screen, checks that the panel fills the window and that the quote is inside it. Red on the old layout (the panel taller than the window), red again on the new layout without the listener (the quote out of view), then green.
  - **Figures:** `splitFigures` puts the highlighter on numbers with a $ before them, or a %, "percent", a scale or USD after them. Bare years, dates and item numbers stay plain. Its unit test came first (red: no such export).
  - **Ruling, citation brackets at zero size:** the mockup shows only the number. `[` and `]` stay in the DOM at `font-size: 0`, so copied text still reads "[1]". Cost if wrong: two spans.
  - **Pitfall, visually hidden text inside an inline link:** the first try hid the brackets with `.visually-hidden` (absolute, 1 px, clipped). Playwright then aimed at a 1 by 1 px box, the hidden span's, and the paragraph took the click (`<p tabindex="-1" id="answer-text" class="answer-text">…</p> intercepts pointer events`; the numeric spec timed out). The trace showed the 1 px box. A probe page showed the same spans also make `innerText` read "[", "1" and "]" on three lines. Zero-size spans fixed both.
  - **Contrast:** the mockup's palette was measured with the WCAG formula. The lowest text pair is 5.01:1 (labels on the tinted card, light), the lowest border 3.52:1 (the pager on the light page). The mockup's pale field borders (about 1.5:1) were darkened to `#7b847f` to keep 3:1.
  - **The demo's white band** is a `border-image` with a `100vmax` outset: painted outside the box, it never adds sideways scroll, which the phone spec checks.
  - **Candidates:** what the mockup has and the app lacks went to todo.md with sizes and API needs, checked against `contracts/schema.graphql`, `clients/ts/openapi.d.ts` and `packages/db`. For example, `Filing.sections` and `periodEnd` exist, no table keeps questions, and ingest jobs have no list route.
- 2026-10-19: Fix before shipping (user request): at the top of Ask the panel's last 100 px or so sat below the window. Cause, measured: the panel was the window's height less 32 px, but on the first screen it starts 127.5 px down (the 56 px header, main's 24 px top padding, the title's 27.5 px line and the 20 px gap), so its bottom edge sat 95.5 px below the window until the page had scrolled far enough for `top: 1rem` to apply. The height ruling above reasoned from where the panel sticks, not from where it starts.
  - **Ruling, the panel sticks where it starts:** `top: var(--panel-top)`, the sum of those four, and a height of the window less that and 16 px. It never moves, and its bottom edge sits 16 px above the window's from the first screen. Not chosen: sticking at 16 px with the shorter height, which leaves a gap below the panel once the page scrolls; or a panel that grows as the page scrolls, which needs a scroll-driven animation or script. Cost if wrong: once the page scrolls, the panel is 111.5 px shorter than the old full-height one.
  - **Pitfall:** the sum ties the panel to the header's height, main's top padding, the title's line and the gap. Change one and the panel test's 16 px check fails, which is the signal to change the sum.
  - **Test:** the panel test now runs in a 1024 by 360 window, the narrowest two-column width, and checks the gap below the panel on the first screen, before the click: red at -95.5 px, then 16. After the click it checks that the panel is on screen; "fills the window" went, since the panel is now shorter than the window by its top.
  - **Screenshots, only those that change:** the set went to the scratchpad (`SCREENS_DIR`) and was compared pixel by pixel with `docs/screenshots/ui` (sharp, already installed with Next). Unchanged screens came out byte-identical. Two screens differ on every run whatever the change: `ask-draft` (how much draft has streamed) and `config-error` (a random request id). Leave those unless the change touches them.

From the first mockup features (2026-10-20, branch `mockup-features-1`):

- 2026-10-20: The user asked for the mockup's small features with no API change, showing only what the app really knows, each test first, with axe passing and the reading and keyboard order unchanged. Five of the 15 candidates were taken: Copy answer with sources, New question, the answer's timings, the demo header's coverage line and the Indexed pill. A detail that needs data the API does not give was left out and noted in todo.md.
  - **Discrepancy, reported to the user:** their examples named the source details, the Filings search and the status pills, which todo.md had sized as needing API work. Checked in the code: GraphQL `companies` takes only `first` and `after`, and REST `/v1/companies` only `limit` and `cursor`, so nothing searches across pages. `LiveBackend.list_filings` keeps `status == INDEXED`, so "Indexed" is the one status the app knows. `Filing.periodEnd` exists, but `Sources` does not select it and the snapshot lacks it.
  - **Ruling, no Filings search:** a search across pages needs an API filter, or the web paging through every company on each search, and a filter over the 20 shown would mislead. Cost if wrong: one PR that adds the filter.
  - **Ruling, no source details:** the fiscal year end needs `periodEnd` in `Sources`, `make codegen`, and `make demo-export` against the dev Postgres. `filinglens-postgres-1` had exited (code 255) about 10 minutes before it was checked (about 13:15 UTC, cause not confirmed), during Triage Copilot's exam, so it stayed stopped. "How it was found" needs API work, and drawing a passage's table as a table is medium: ragged rows, `$` in its own cell, and quotes that cross cells. Cost if wrong: a follow-up PR once the user gives a go for the dev Postgres.
  - **Ruling, no source pager:** small and no API work, but one source at a time takes the others out of the reading and keyboard order, which the user asked to keep. Cost if wrong: one more small PR.
  - **Ruling, the coverage line on the demo header only:** the API gives no count, so the live header has none. The demo counts the snapshot's companies and listed filings, with "+" if any company's older filings went unlisted. The mockup's "latest" is left out, since nothing records that a filing is its company's latest. Cost if wrong: one line.
  - **Ruling, Copy only for an answer that cites:** a refusal shows only New question, so no button copies a reason under an empty Sources list. Cost if wrong: one condition.
  - **Ruling, copy feedback in the status line:** B2.4's single polite status line announces results. Cost if wrong: one string.
  - **Timings:** the browser's `performance.now()` from the question's send; first words at the first `delta`, complete once the stream with `completed` has ended. The mockup's "every number checked" is left out: it needs the number check.
  - **New question, test first for the busy reset:** with the sources lookup held (`page.route` that never answers), New question left `busy` set, because an aborted question leaves busy alone (B3), and the next Ask was ignored; its button still read "Answering…" (red). `startOver` now aborts the lookup and clears busy itself.
  - **Pitfall, the clipboard under Playwright's Chromium on Windows:** `navigator.clipboard.readText()` hands back CRLF line ends for text written with LF, so the copy spec folds CRLF. The headless shell keeps its own clipboard: right after the copy spec, the Windows clipboard did not start with the copied answer. That was checked twice as a yes or no in PowerShell, never printing what the clipboard held.
  - **The demo header's pair:** the line and its button sit in `div.site-end`, which wraps as one. A scratch probe showed that from 641 px to about 690 px wide the pair wraps below the tabs and the header looks cramped; nothing overlaps (design.md, known limits).
  - **Pitfall, a scratch Playwright config:** in the scratchpad it could not import `@playwright/test` (`ERR_MODULE_NOT_FOUND`), since no `node_modules` sits above that folder. Importing `web/node_modules/@playwright/test/index.mjs` by absolute path in the config and the spec, and giving each web server `cwd` set to `web`, fixed it.

From the source cards' fiscal year end (2026-10-20, branch `source-fiscal-year`):

- 2026-10-20: A passage's source card shows its filing's period under the heading, as the mockup does: "Fiscal year ended December 31, 2025" (user request, after mockup features 1 merged as #17). `Sources` selects the chunk's `filing { periodEnd }`, a field the API already had, so no API change; `make codegen` and a new snapshot followed.
  - **Container go (user, 2026-10-20):** `filinglens-postgres-1` for `make demo-export`, started and stopped by exact name; Triage Copilot's exam is over. Port 5433 was free, and the container had exited (255) 56 minutes before. After `docker start`, `pg_isready` answered on the 4th check; the export ran; `docker stop` left it exited (0) with the port free.
  - **The date:** `periodEnd` is SEC's period of report (`reportDate`, stored as `filings.period_end` by discover), so for a 10-K it is the fiscal year end. `periodEnded` writes "Fiscal year ended" for FY and "Quarter ended" otherwise, with `Intl.DateTimeFormat("en-US", { dateStyle: "long", timeZone: "UTC" })` on the date at UTC midnight, so the server-rendered demo and any browser agree. Its unit test pins a year end on December 31 and a 10-Q row the snapshot does not have.
  - **Ruling, fact cards unchanged:** `FinancialFact` has no link to its filing, so its filing's year end would need an API change. Its Period row already names the value's own period. Cost if wrong: one more field and line once the API links a fact to its filing.
  - **The snapshot's other changes, checked for the user's review:** a scratch script set `periodEnd` aside and compared the rest field by field. Only `commit` (a2037af to e1059d7, the export's HEAD; the `Sources` change was not yet committed) and `recorded_at` changed. Answers, citations, warnings, usage, companies, filings, chunks and facts are identical. All 7 cited chunks gained `periodEnd`, 4 filings: LLY, AMZN and TSLA 2025-12-31, NVDA 2026-01-25. Each matches the date stamped in its filing's file name (`lly-20251231.htm`, `nvda-20260125.htm`). LF only, 46,116 bytes.
  - **Pitfall, CRLF after codegen goes beyond what `git status` lists:** the first `make codegen` showed 15 changed files. 5 had content changes, and 10 differed in CRLF only. But `clients/python/` had also been rewritten with CRLF, and git, with `eol=lf` in `.gitattributes`, counted those as clean and did not list them. Comparing every tracked file under `contracts/` and `clients/` with `git show HEAD:<path>` found 60 that differed in line endings only. All 60 went back to HEAD's bytes (touch, then `git checkout HEAD --`, then `cmp`, as the 2026-10-19 lesson says).
  - **Instead of `make contracts-check`**, which fails on any uncommitted change under `contracts/` or `clients/`, codegen ran a second time: its CR-insensitive diff equalled the first run's, so a fresh codegen on CI reproduces the committed files.

From the step 10 plan (made 2026-10-20, approved 2026-10-21; plan file `C:\Users\kwonhyuk\.claude\plans\pasted-content-id-ee81-source-fiscal-validated-dolphin.md`):

- 2026-10-20: The API's Funnel runs in a `tailscale` sidecar container in the prod stack, as FreightAudit runs its own (user decision).
  - **What FilingLens gets:**
    - its own node (`filinglens`) and tag (`tag:filinglens`);
    - its own external state volume (`filinglens-prod-tailscale-state`);
    - FreightAudit's image pin;
    - Funnel on 443, proxying to `http://api:4100`.
  - **What happened:** planning found Tailscale not installed on this PC. The user chose the sidecar over the Windows app, and allowed a read-only look at FreightAudit's `infra/docker-compose.prod.yml` and `infra/tailscale/serve.json` as the pattern, never its `.env` files.
  - **Reason:** nothing is machine-wide, each project gets its own node and port 443, and the Funnel config lives in the repo.
- 2026-10-20: Other decisions (user):
  - the GraphQL DataLoader ships before go-live (PR 10b);
  - Alertmanager comes after go-live;
  - the GHCR packages `filinglens-api` and `filinglens-ingest` go public, which GitHub never reverses.
- 2026-10-21: The plan's approval brought three changes (user):
  - **Free providers only in production:** `LLM_ANSWER_FALLBACK` stays empty and `ANTHROPIC_API_KEY` stays out of `.env.prod` (standing rule: no Anthropic key on the public deployment). The prod override also forces both empty, so a stray `.env.prod` line cannot reach the api.
  - **Gemini key first:** AI goes on only after FilingLens's Gemini key has its own Google project, with billing off (the user's step B28).
  - **Egress proxy:** FreightAudit's egress proxy is the first Pending item after go-live. context.md's Known Limitations states the gap until then.
- 2026-10-20: Rulings in the plan (no user decision needed; each is cheap to change):
  - **Prod stack:**
    - It is its own compose project, `filinglens-prod`, with `.env.prod`, so it never shares the dev stack's containers or volumes.
    - It runs CI's GHCR images by `sha-` tag, never `latest`, and publishes no host port.
    - Postgres, Redis and RabbitMQ sit on an internal `data` network that the tailscale container is not on.
    - The workers sit behind an `ingest` profile, since serving needs only the api.
  - **Database:**
    - Prod restores `corpus-v1` once, by exact container name: about 11 s, 0 SEC requests. That is the data golden v1, the README and the demo describe.
    - A fresh ingest would first need the financial-section labelling work, a prod migration path and the workers.
  - **Dev `.env` passwords stay:**
    - Postgres and RabbitMQ read their passwords only when their volume is first created, so new values in `.env` would lock dev out.
    - Production gets new values in `.env.prod`.
    - This replaced the pending item "Replace the example passwords in `.env`".
  - **Budget:** `DAILY_AI_TOKEN_BUDGET=300000` is recommended for prod, about 55 textual answers a day.
    - It leaves room in Groq gpt-oss-20b's 200K a day for CI.
    - Each stack counts in its own Redis, so dev and prod are capped apart.
  - **Node on Vercel:** `engines.node` becomes `^24.7.0`. Vercel maps a `>=` range to the newest major it offers, and the 24.7 floor (`crypto.argon2`) has to stay.
  - **Region:** `hkg1`, the Vercel region nearest Taiwan.
- 2026-10-20: The plan's review corrected the hardening design. A fresh agent checked it against FastAPI 0.143.0, Strawberry 0.334.4 and graphql-core 3.3.0:
  - **Introspection:** it goes off through `strawberry.extensions.DisableIntrospection`, passed as the class.
  - **Coercion errors:** they are found by shape, not text: no `path`, plus either a `GraphQLError` as `original_error` (variables) or a value node that is not a variable (literals).
  - **Error logging:** Strawberry's `process_errors` runs before `ErrorCodes`, so the log override works out the code itself. It keeps `exc_info` for `internal`.
  - **`/readyz` cache:** its state is made in `lifespan`, since the tests share one app across event loops.
  - **NUL:** a NUL reaches Postgres from `q`, `question` and cursors too, not only from `concept`.
  - **SQL errors:** SQLAlchemy quotes the parameters in its errors, so `make_engine` gets `hide_parameters=True`.

From PR 10a (2026-10-21, branch `step-10-api-hardening`):

- 2026-10-21: One NUL rule for every string that reaches Postgres. `schemas.NoNul` is a `str` with an `AfterValidator`, so the JSON schema and the contracts do not change. It covers REST `q`, `AnswerRequest.question` and the string fields of every cursor key. GraphQL `concept` checks inline, like `_ids`. Reason: Postgres refuses a NUL in text, which came back as a 500 (REST) or `internal` (GraphQL); `\x01` still passes (pin rows).
- 2026-10-21: A GraphQL bad value is found by shape (`graph._bad_value`), not by its text. It matches a `GraphQLError` as `original_error` (variable coercion, or an argument coerced at execution), or a value node that is not a variable (literal coercion).
  - `error_code` serves both `ErrorCodes` and the log override.
  - Validation errors (unknown field, undefined variable, the depth, alias and introspection rules) keep their message and have no code.
- 2026-10-21: Strawberry's taxonomy 5xx errors (`upstream_error`, `ai_unavailable`) now log at warning with code and path. Before, they logged at error with a traceback. Only `internal` keeps error level and its traceback. Nothing in the repo reads `strawberry.execution`.
- 2026-10-21: The final review (a fresh agent, verdict "ready with fixes", no Critical) found one Important issue and five Minor ones; all were fixed test first:
  - **Important:** `/readyz` stamped its cache before the round. A round longer than 5 s (three 2 s time-outs in an outage) was stale on arrival, so every queued caller ran its own round. The stamp is now taken at the end.
  - **Minor:** keyless Origin rows pin the dependency order; every cursor key field has a NUL row; argument errors found at execution are bad values too (the `path` guard went); `CompanyKey.cik` is bounded (`Cik`, against BIGINT); GraphQL `fiscalYear` takes 1993-2100 (against SMALLINT); the `monotonic` patch lost `raising=False`.
  - Its mutation runs: removing each feature failed the tests named for it.
  - **Not verifiable offline:** that Vercel's Node `fetch` sends no `Origin`. undici adds none, and `web/lib/server.ts` forwards no headers. Step B24, the phone test, covers it: every BFF call would get 403 otherwise.
- 2026-10-21: Pitfall: asyncpg's own `DataError` quotes up to 40 characters of a bound value, which `hide_parameters` does not cover. So input bounds belong at validation (the review's CIK and fiscal-year rows).

From PR 10b (2026-10-21, branch `step-10-dataloader`):

- 2026-10-21: The GraphQL links off the citation path load through two DataLoaders (`strawberry.dataloader`), made per request in `graph.get_context`: `chunk_sources` batches `Backend.get_chunks`, and `companies` batches `Backend.get_companies`.
  - Each load function lines the rows up by key and gives a missing key its own `NotFoundError`, with the old messages. The rows pre-joined on the citation path still skip the loaders.
  - **Effect:** the links on one page make one lookup by id, each id once. For the 2026-10-18 worst query (20 cited chunks, `first: 100`), that is at most one per listed page, about 60, against thousands before. The figure uses the same counting and was not measured.
  - **Not changed:** page queries. Each parent still runs its own `list_sections`, `list_chunks`, `list_facts` or `Company.filings` query (the next entry).
  - **Shield:** each link awaits `asyncio.shield(loader.load(key))`.
    - Why: the loader hands every link on a key the same future. graphql-core 3.3 cancels a failed field's siblings, and cancelling a task cancels the future it awaits.
    - Without the shield, a sibling's error cancelled the shared future for links elsewhere in the query. Their `CancelledError` is a BaseException, which no layer catches, so a GraphQL error became an HTTP 500, and the real error went unlogged.
    - The final review found it by reading the code; a test row per shield gave 500 without it (3 runs of 3).
  - **Ruling:** `get_companies` replaces `get_company` rather than joining it, since `_company` was its only caller. Like `get_chunks`, it returns rows once each in the order given and leaves unknown keys out.
- 2026-10-21: Open, the user decides (the final review): page queries still run once per parent.
  - `{ filings(first: 100) { edges { node { sections { chunks(first: 100) { edges { cursor } } } } } } }` passes the depth limit of 6. On corpus-v1 (30 filings, 677 sections), it makes 1 + 30 + 677 = 708 page queries, each reading up to 101 chunk rows with their text.
  - It is not a regression. The key is server-only, and the web never sends such a query.
  - Options: cap a nested `first`, batch `Section.chunks`, or leave it.
  - **Decided, and done by 10c** (2026-10-24, merged as #28): the user chose the nested `first` cap, 20 inside a list and 100 on the outermost list (PR 10c below). The numbers with the loaders and the cap together are in the 10b merge entry below.
- 2026-10-21: Pitfall: the fake backend answers without suspending. So B1's tests never saw `section` and `filing` make two lookups for one chunk: the first resolver set `Chunk.source` before the second started. A real backend waits on I/O, so both start first.
  - The call-count spy now yields once (`asyncio.sleep(0)`) before the fake answers. With it, main's code made 7 lookups for the fake's 3-chunk page (1, plus 2 per chunk). Without it, main's code made 4.
  - The loaders make 2.
- 2026-10-21: Lesson: graphql-core 3.3 cancels sibling resolvers at the first error (`gather_with_cancel`), and every link field is non-null. So a missing row nulls `data` and leaves exactly one error.
  - The test of the loaders' lining up checks that error's message, code and path.
  - A scratch mutation, loaders that pad the results instead, put the error on another item and failed both rows.
  - The same cancellation reaches the loaders' shared futures, hence the shield (above).
- 2026-10-21: Mutation runs, from scratch pytest plugins in the scratchpad, with no repo change. Each failed the tests named for it:
  - padded loaders: both missing-row rows;
  - one shield removed at a time: only that shield's row;
  - one loader for the whole process: the per-request pin;
  - a failed lookup swallowed as `not_found`: the masked-error pin.

From PR 10c (2026-10-24, branch `step-10-deploy-config` from main at 7979cdb):

- 2026-10-24: The nested `first` cap (user: "Include the nested 'first' cap on GraphQL lists that was planned for 10c, test first"). It is the first of the three options 10b's final review left open: cap a nested `first`, batch `Section.chunks`, or leave it. That entry sits in 10b's memory.md, on its unmerged branch.
  - **Rule:** a connection with a list index on its path (`info.path`) takes `first` 1 to 20; the outermost list keeps 1 to 100. Past that, `invalid_input` ("first must be between 1 and 20 inside another list."), before its page is read.
  - **Why 20 (ruling, cheap to change):** it is the default page size, so a nested list that leaves `first` out still passes. The web asks for 5 inside a list (Coverage, and the Filings operation's defaults). 10 would refuse the default and need a schema change.
  - **Ceiling:** it bounds the rows each nested page reads, not the number of page queries. 10b's worst query, `filings(first: 100) { … sections { chunks(first: 100) … } }`, made 708 page queries of up to 101 rows on corpus-v1 (about 71,500 rows). That query is now refused; with `chunks(first: 20)` it passes and reads at most 21 rows a page (about 14,900). The query count stays 708. Upgrade path: batch `Section.chunks` into one query per parent list.
  - **Reach:** the read-under-load integration test asked for `chunks(first: 50)` inside `filings`, now 20. Nothing else in the repo asks for more than 20 inside a list.
- 2026-10-24: Rulings in the prod override (no user decision needed; each cheap to change):
  - **Claude first:** nothing is forced. The 2026-10-21 approval ruling "the prod override also forces both empty" (`LLM_ANSWER_FALLBACK`, `ANTHROPIC_API_KEY`) is superseded by Claude first (user, 2026-10-21, merged as #22). Models and keys come from `.env.prod` alone.
  - **Required in prod:** `IMAGE_TAG` and `RETRIEVAL_EMBEDDING_COLUMN` (`${VAR:?…; see docs/deploy.md}`). The column's code default, `embedding_v2`, would fail every search on corpus-v1 (plan, Review Focus 2), so compose now stops first.
  - **From FreightAudit's prod file** (read again, read-only, under the 2026-10-20 permission "as the pattern", never its `.env` files): the `x-kept` and `x-hardened` anchors, the tailscale service with its environment, socket, health check and pinned image, the external state volume, and `serve.json`'s shape. Not taken: its egress proxy (first after go-live), its `IMAGE_REPO` variable and its `migrate` service (prod restores `corpus-v1` instead).
  - **Monitoring in prod:** the observability services keep their limits but stay off. They sit on `default`, so RabbitMQ's metrics on `data` and the `embed` worker would be out of their reach; wiring them waits for the Alertmanager item.
- 2026-10-24: Pitfall: compose passes a container only what its `environment:` lists, so every `ApiSettings` field needs its line in the api's compose environment.
  - **What happened:** Claude first added `CLAUDE_DAILY_TOKEN_BUDGET` to the settings, `.env.example` and the plan's variable table, but not to compose. In a container, the default 1,500,000 always applied, whatever `.env` or `.env.prod` said.
  - **Found:** while checking the variable table against the code (user: "check the variable table ... match"), by comparing `ApiSettings.model_fields` with the rendered prod config. It was the only field missing; `OLLAMA_URL` and `OTEL_SERVICE_NAME` stay out on purpose.
  - **What we did, in order:** rendered the prod config with a dummy env file that sets 1234567 (red: no such variable in the api's environment); added one line to the api's environment in `infra/docker-compose.yml`, which covers dev and prod; rendered again (green). Kept in 10c, not a PR of its own: the step's own table names the variable. The user can still split it out.
  - **Not added:** a lasting test. PyYAML is only a transitive dependency, and a new dependency needs the user's approval. The 10c check script (activity-log.md) does the audit by `docker compose config`.
- 2026-10-24: Container go for 10c (user, asked once every other check had passed): Testcontainers for one `make test-int` run. FreightAudit's ten running containers were the same before and after. Any other container needs a new go.
- 2026-10-24: 10b is not on main. Its commit 305b123 sits on `step-10-dataloader` (pushed), and main's `graph.py` still has the two `ponytail:` one-lookup comments. 10c was built from main as the user asked. The plan puts the DataLoader before go-live, so deploy.md's steps 5 to 23 wait for 10a, 10b and 10c. Expect conflicts when 10b takes main: `graph.py` (both touch the resolvers) and `test_contract.py` (both add tests at the end; keep both).

From the 10b merge (2026-10-24, main at 8e638a2 merged into `step-10-dataloader`, uncommitted):

- 2026-10-24: Main merged into 10b (user: "Merge main into the 10b branch so it can ship"; `git merge main --no-commit`; the user's ship concludes it).
  - **Text conflicts:** four docs only, each resolved by keeping both sides, entries in date order. `graph.py` and `test_contract.py` merged cleanly: the loaders and the cap touch different lines. The 10c entry above expected a conflict there.
  - **The conflict git could not see:** four of 10b's test rows asked for `first: 100` inside a list (under `chunks(ids: …)`), which 10c's cap refuses. The merged contract tests failed exactly those 4. They now ask for 20; the fake lists at most 3 rows, so each row's lookups stay the same.
- 2026-10-24: 10b's worst queries, measured with the loaders and the cap together, on corpus-v1's rows (the dev Postgres: revision 0008, 30 indexed filings, 677 sections, 11,263 chunks).
  - **How:** a scratch script outside the repo ran each query in process through the real schema and `graph.get_context` (the per-request DataLoaders), over a `LiveBackend` subclass that counted every SQL statement and the rows it returned, by backend method. "Before the cap" set `graph.NESTED_FIRST` to 100 in that process only. Three runs: page queries and rows were the same each time; lookups by id varied.
  - **Q1, 10b's review query:** `{ filings(first: 100) { edges { node { sections { chunks(first: N) { edges { cursor } } } } } } }`.

    | Run | Page queries | Lookups by id | Rows read |
    | --- | --- | --- | --- |
    | before the cap, N = 100 | 708 (1 + 30 + 677) | 0 | 9,081 (30 + 677 + 8,374) |
    | cap, N = 100 | 6, then refused (`invalid_input`) | 0 | 145 |
    | cap, N = 20, the most it allows | 708 | 0 | 4,413 (30 + 677 + 3,706) |

  - **Q2, links under a list:** 20 cited chunks from 20 filings, each filing's `chunks(first: N)` with `section` and `filing`, and `facts(first: N)` with `company` (the 2026-10-18 worst shape).

    | Run | Page queries | Lookups by id | Rows read |
    | --- | --- | --- | --- |
    | before the cap, N = 100 | 40 | 24 to 29 | 6,080 (2,020 + 2,020 + 2,020 + 20) |
    | cap, N = 100 | 0, refused | 1 (the cited ids) | 20 |
    | cap, N = 20 | 40 | 28 to 33 | 1,280 (420 + 420 + 420 + 20) |

    The rows are chunk pages, fact pages, chunk lookups (the cited ids plus each listed chunk once) and companies.
  - **Corrections:** 10b's "each reading up to 101 chunk rows" and 10c's "about 71,500" and "about 14,900" were upper bounds from the page size. Measured, Q1's chunk pages read 8,374 rows before the cap and 3,706 with it: most sections hold fewer chunks than a page. 10b's unmeasured "about 60" lookups by id came out at 24 to 33, the cited-ids lookup included.
  - **Why the lookups vary:** a loader batches the links that wait in the same event-loop turn. Pages finish at different times, so the same query makes a different number of batches. Each id is still looked up once per request.
  - **What the cap leaves:** page queries still run once per parent (708 for Q1). Batching `Section.chunks` is the upgrade path.
- 2026-10-24: Container go for the 10b merge (user): Testcontainers for one `make test-int`, and `filinglens-postgres-1` by exact name for the measurement, with two conditions: the script stays outside the repo (it is in the scratchpad), and the container ends as found (it was stopped, so it was stopped again). Port 5433 was free first; afterwards only closed connections (`TIME_WAIT`) remained on it.

From the landing page (2026-10-25, branch `landing-page` from main at 41ac308, uncommitted):

- 2026-10-25: The public landing page (user: "Build FilingLens's public landing page from the approved mockup"). The user's decisions on the plan: "Open the demo" goes to `/demo`; the fact count stays out; the sample answer is n01; "Keep all your mockup corrections. The GitHub repo is public."
  - **Routes:** `/` is public, calls no API and holds no key; Ask moved to `/ask`, behind sign-in as before; sign-in's default page is now `/ask` (was `/`). "Try the live demo" links to `/ask`, so the gate sends a signed-out visitor to `/login?next=%2Fask` and back.
  - **Where each figure comes from, at build time:** the ten table rows (target, result, met or not) from the official report's Markdown, `evals/reports/2026-10-17.md`; the date, the 30 questions, the models, the judge's kappa and labeler, recall's n, the 11,263 passages and the reranker's 50 from its JSON; the 30 companies, the 8 saved answers and n01 from `web/demo/snapshot.json`. The snapshot holds no passage or fact count, so the passages come from the report's index. Left out, with no source: the fact count (856,438 is only in the docs) and SEC's "10 requests per second".
  - **Targets from the Markdown (ruling):** the report's JSON holds each metric's value and pass or fail, but no target; the harness writes the targets (`TARGETS` in `evals/harness.py`) only into the Markdown. So the page imports the Markdown as text (Turbopack's `type: "text"` rule for `*.md`, Next 16.2 or later, typed by `markdown.d.ts`). A report without one of the ten rows fails the build, naming the row.
  - **Live models (ruling):** a fixed sentence from `docs/deploy.md`: Claude Haiku 5.5 first, within its daily budget and while its prepaid credits last, then Gemini 3.5 Flash-Lite, then gpt-oss-20b on NVIDIA. The setting lives in `.env.prod`, which the build never reads. The page says the table measures the free models, not Claude.
  - **Drift tests:** `e2e/landing.spec.ts` reads the newest `evals/reports/<date>.json`, its Markdown and the snapshot from disk and checks each figure on the rendered page, so a figure typed into the page, or a newer report the page does not import, fails it. `lib/landing.test.ts` pins the formats.
- 2026-10-25: The mockup's copy corrected where it claims more than the code does (user: "Keep all your mockup corrections"):
  - "every number is checked against the filing's own XBRL data": the validator checks each amount against the fact or the quoted passage its sentence cites (`check_sentence` in `packages/llm`), not against all of a filing's XBRL data.
  - "removed before you see it": Ask shows the draft first, marked as not yet checked, and the checked answer replaces it.
  - "latest 10-K": nothing records that a filing is its company's latest (design.md, mockup features 1).
  - "15 saved sample answers": the snapshot holds 8.
  - "checked on every pull request": CI's eval runs only when an eval input changed (README, CI).
  - "End-to-end latency, p95": the report's "Full answer p95" is timed in the eval process, not through the web, so the row says "Full answer latency".
  - The stack gains Redis and Claude.
- 2026-10-25: Pitfall: `next build` type-checks every TypeScript file in `web/`, tests included. A spec that imports a module not written yet fails the build, so the old app cannot be built for a red Playwright run. Here the pure helper came first (`lib/landing.ts`, its unit tests red, then green), then the old app's build and the red landing spec.
- 2026-10-25: Pitfall: a class name that already means something. `.result` is Ask's answer card (border, background, grid), so the first landing table drew a box round each result cell. Renamed `.measured`; a search of all markup for the landing's new class names then found none in use elsewhere.
- 2026-10-25: "Try the live demo" is a plain `<a>`, not `next/link`: a full page load, so the gate's redirect is the one a typed `/ask` gets. Whether a client-side navigation would keep the same `next` was not tested (not confirmed either way).

From mockup features 2 (2026-10-25, branch `mockup-features-2` from main at b93a8d2, API and web together, uncommitted):

- 2026-10-25: Ask closer to the mockup with five candidates (user: "Bring Ask closer to the approved mockup"). The user's decisions: the mockup's 2/3 + 1/3 split, reversing the 2026-10-19 half-width panel; a sample question only fills the box; `totals` counts companies with an indexed filing; passage-quoted amounts stay in the table, its title adapting; the chips come with the completed answer; the demo follows the split; PR 0 (#30) first and apart; then "Build PR 1 and PR 2 together on one branch".
  - **Contract (expand-only):** `Answer.reading`, `Answer.checks`, GraphQL `totals`. Inside `completed`, since a new stream event would break today's web, which treats unknown types as failed.
  - **Eval inputs touched** (`packages/llm/src`, `services/api/src`), so CI's eval runs. Keys unchanged: the five prompt hashes equal `evals/reports/2026-10-17.json`'s (computed with the snapshot's 30 tracked companies and the report's as-of date), and `check_sentence`, `find_amounts`, `numbers_in` and `amounts_match` are untouched.
  - **Rulings (no user decision needed):** the table's Figure column names a fact by its label and period end, since a fact's fiscal year is its filing's (Tesla's 2024 value would read "fiscal 2025"); `source_value` is normalized, so a float value from GraphQL prints no ".0"; the demo export runs the pipeline's own `drafting.check` over each saved answer (`[n]` markers back to `[Fn]`/`[Cn]` aliases), and a sentence that no longer holds stops the export; `answering.reading_of` is public so the export reads saved routings the same way; four metric keys get labels ("Diluted EPS", "Basic EPS", "Stockholders' equity", "Long-term debt"), the rest read as their words.
- 2026-10-25: Pitfall: a sideways-scrolling table with nothing focusable inside fails axe's `scrollable-region-focusable` on a phone (WCAG 2.1.1). The e2e axe runs are at desktop width, where the checks table fits, so only the phone screenshots' axe check caught it. Fixed with `role="region"`, a name and `tabIndex={0}` on the table's scroll box, test first (a 390 px axe test on c12).
- 2026-10-25: Lesson: the new Playwright spec was written after the components, so it never ran red by itself. A temporary mutation (no chips, no checks table, halves again) failed 4 of its 6 tests (the 2 left: the header line and the samples, not mutated), then was reverted and checked gone. Write the spec before the components next time.

From the egress proxy (2026-10-25, branch `egress-proxy` from main at c5282a1, uncommitted):

- 2026-10-25: Production's egress proxy, as FreightAudit runs it (user, todo.md since 2026-10-21; plan approved 2026-10-25): the api and the tailscale container reach the internet only through squid, with the model providers production uses (Anthropic, Groq, Gemini, NVIDIA) and Tailscale's hosts, and nothing else; FilingLens's own CI-built image, pinned by its sha tag; tests first.
  - **The user's answers to the plan's questions:** tailscaled's log upload off (`--no-logs-no-support`), so `log.tailscale.com` is not allowed; the ingest workers stay on `default` for now, with a todo item; the proxy shares the api's `IMAGE_TAG`; a 256 MB limit; the deploy-order rule goes into this PR's deploy.md.
  - **One exception to "control and relay hosts":** `acme-v02.api.letsencrypt.org` stays allowed. Funnel's certificate is issued and renewed on the node, so without it the certificate would expire.
  - **Rulings (mine):**
    - `infra/squid/` holds the Dockerfile (FreightAudit's recipe) and `squid.conf`; the image is `filinglens-squid`; ports 3128 `api` and 3129 `tailscale`.
    - `outbound` is 10.231.232.0/28, beside FreightAudit's 10.231.231.0/28 and outside Docker's default pools: api .2, tailscale .3, others .8 to .15. The test network is 10.231.233.0/28.
    - `NO_PROXY` lists every internal service the api might call over HTTP, plus the loopbacks.
    - The healthcheck is FreightAudit's (bash `/dev/tcp` on both ports), its access-log noise accepted.
    - `squid.conf` is mounted from the checkout, so an allowlist change needs a restart, not an image, and keeps the checkout's line endings: FreightAudit's file is CRLF in its Windows checkout and works, since squid splits words on `\r` too.
    - Dependabot ignores ubuntu's minor and major updates, since the build names its release (noble-security); digest updates still come.
  - **No app code changed:** each provider client already reads the proxy settings. Groq, NVIDIA and Gemini share one `httpx.AsyncClient` (`main.py`, `trust_env` on by default), which google-genai uses as given, and aiohttp is not installed. The Anthropic SDK (1.15, on `httpx2`) builds its own proxy transports from `HTTPS_PROXY` and `NO_PROXY` (`anthropic/_utils/_httpx.py`). Read in the installed sources on 2026-10-25.
  - **The tests are hermetic.** The live check runs the image on an internal network with no route out, and every name a probe asks for is mapped in the proxy's `/etc/hosts`: allowed names to 203.0.113.10 (public, unreachable), `host.docker.internal` and one relay-like name to `host-gateway`. So squid sends no DNS query and reaches nothing: an allowed request gets its 503 (no route), any other its 403. Why not real tunnels: tests never reach a provider, and the outcome must not depend on the network.
- 2026-10-25: Mistake (mine): my report for #31 did not say that the API had to reach the PC right after the merge. Vercel shipped #31's web, whose `ping()` asks for `totals`, while the PC still ran `sha-41ac308` (read-only `docker inspect --format`, while planning the egress proxy). A GraphQL validation error carries no `extensions.code`, so the web reads it as offline (`web/lib/errors.ts`), and Ask and Coverage would land on the offline demo. Seen from the code, not on the site. The plan told the user to deploy `sha-c5282a1` first; just after the egress branch was created, the api container ran `sha-c5282a1`, started 43 seconds before. What we did: deploy.md's step 23 now says a merge that changes the API goes to the PC right away, and a report for a PR that changes the API says so too.
- 2026-10-25: Pitfall: `docker compose config --no-interpolate --format json` prints some services' `environment` as `KEY=value` strings and others as a mapping. Here the api's (its base merges two YAML anchors) came as a list and tailscale's as a mapping, so the compose test reads both forms.
- 2026-10-25: Pitfall: a ripgrep-based search (Claude Code's Grep tool) finds nothing in `.venv`, because uv writes `.venv/.gitignore` with `*`. While planning, a search for `trust_env` in the installed `httpx2` came back empty and almost read as "no proxy support". What we did: grep by path in Bash. A search of installed packages needs `--no-ignore` or a direct path.

From the alert delivery (2026-10-25, branch `alertmanager` from main at 12502f3, uncommitted):

- 2026-10-25: Alertmanager for production (user, todo.md since 2026-10-20; plan approved 2026-10-25). The alert rules go to a Discord webhook and to email through Gmail SMTP with an app password. The webhook, the password and both addresses stay out of the repo. Alertmanager reaches only `discord.com:443` and `smtp.gmail.com:587`, inside the egress design. Tests came first, with fakes.
  - **The user's answers to the plan's questions:**
    - The worker rules wait for work: TelemetryMissing counts ingest and embed only while their queues have a consumer or ready work, and WorkerNotConsuming fires only while its queue holds ready messages. Production runs no workers, so both would otherwise fire for ever.
    - `keep_firing_for: 10m` on every rule, since Alertmanager alone spaces a flapping alert's messages only by `group_interval`.
    - Grafana is production's only published UI (127.0.0.1:3111), so Prometheus and Jaeger have no route out.
  - **Why a relay:** Alertmanager sends no SMTP through a proxy; its email notifier dials with a plain `net.Dialer` (v0.34.1 source). socat in our squid image takes Alertmanager's connections, from its address alone (`range`), and opens each as a CONNECT to `smtp.gmail.com:587` on squid's own port 3131. squid lets 587 through that port only. STARTTLS runs end to end, with `tls_config.server_name: smtp.gmail.com`.
  - **Why an entrypoint:** Alertmanager's config has no environment expansion, and `smtp_auth_username` is a plain string, so the Gmail address must be written into the config.
    - `entrypoint.sh` (busybox sh) writes the webhook and the password to tmpfs files (`webhook_url_file`, `smtp_auth_password_file`), puts the addresses over placeholders in a copy of the config, unsets the four and execs.
    - Compose passes them as `${VAR:-}`. Compose checks required variables before it applies profiles, so `:?` would stop every production command until all four existed.
  - **Prometheus's target:** `prometheus.yml` reads Alertmanager's address from `prometheus-alertmanagers.yml`, which only the prod override mounts. Prometheus's file discovery logs nothing for a listed file that does not exist, so development sends nothing and logs nothing. A static target would log a failed send every minute while an alert fires there.
  - **Rulings (mine):**
    - Ports 3130 (alertmanager) and 3131 (smtp_relay). `alerting` is 10.231.232.16/28, with Alertmanager at .18 and the relay at .19; the relay listens on 2525.
    - socat runs with `-T60`, so a stuck SMTP session cannot hold back the group's Discord message: Alertmanager waits for every channel of a receiver.
    - Alertmanager v0.34.1 is pinned by digest, in compose and in the Makefile.
    - Grouping is by rule: 30 s, 10 min, 12 h. Email gets firing messages only; Discord gets firing and resolved. Times are in UTC. One variable holds both the sender and the SMTP login.
    - Grafana's port is fixed at 3111: deploy.md keeps host ports out of `.env.prod`, and `.env.example` sets dev's `GRAFANA_PORT=3101`.
    - The relay has no healthcheck: a TCP probe from 127.0.0.1 would log a range refusal every time.
- 2026-10-25: Mistake (mine), caught by the design review before the code was written. The approved plan put Alertmanager on `outbound`, beside the api and tailscale. Alertmanager's API has no login, so a compromised api could have silenced every alert or posted fake ones with a phishing runbook link, which the user's own Gmail would then send. What we did: an internal `alerting` network holds only Alertmanager, the relay and the egress proxy, and `outbound` is unchanged; a compose test pins both networks' members. It went in as a small fix, reported to the user, since it restores the plan's own rule that no client reaches another's way out.
- 2026-10-25: The design review's other findings, applied:
  - There are 14 rules, not 13: monitoring.md's table had left out ClaudeKeyOrModelRejected, and todo.md said 13.
  - The delivery test posts the grouped pair in one request without a start time. Alertmanager flushes a group at once when an alert started more than `group_wait` ago, which would race the second alert.
  - The delivery test mounts the repo's directory and overlays one test file. On Linux, pytest's temporary directories belong to the runner alone, and Alertmanager runs as nobody.
  - A unit test refuses a CR in the mounted files, since `.gitattributes` acts only when git writes a file.
  - Left as a todo: an alert when delivery fails.
- 2026-10-25: Pitfall: socat 1.8.0.0 refuses `range=10.231.232.18/32` on `TCP-LISTEN` ("syntax error in range ... of unspecified address family: use <addr>:<mask>"); `TCP4-LISTEN` takes it. Seen in the relay test's first green run.
- 2026-10-25: Pitfall: `docker compose config --no-interpolate` prints a short-syntax port that holds a variable as the string, but a literal one (`127.0.0.1:3111:3000`) in long syntax. The test reads the long form.
- 2026-10-25: Pitfall: a container on internal networks only cannot publish a port, so Grafana keeps `default` for 127.0.0.1:3111.

From the answer-quality round (2026-10-26; plan `C:\Users\kwonhyuk\.claude\plans\cozy-pondering-pinwheel.md`):

- 2026-10-26: The round's plan was approved with the user's answers and changes:
  - **Golden v2:** v1's 100 questions re-keyed, all in dev (this analysis read v1's test answers, so v1's test is no longer held out), plus about 55 new test questions. Labels as v1's: Claude labels every passage, the user spot-checks a blind sample of about 50 in a test block; README and landing page keep "AI-written, spot-checked"; the labeling cost is estimated before it runs.
  - **Arithmetic:** calculation sources (PR 4). **Production corpus:** corpus-v2 restored later, at a time the user picks. **Ticker fill:** adopted, reversing the 2026-10-16 "no fill", because first-words speculation needs the plan to match code's reading and t10 and a03 were refused by the wrong rule.
  - **Order:** the sweep, PR 0 and PR 1 on one branch and one PR; then PR 4, PR 5, PR 6, PR 7; PR 2 (first words sooner) only if time remains; PR 3 only if the sweep wins. Development by about 2026-10-31.
  - **Stop rule:** stop and report only if an estimate grows, a hook refuses, anything needs a key, or a prompt hash changes where the plan says it should not.
- 2026-10-26: The reranker stays TinyBERT-L-2 over 50 at 512 tokens: none of 10 other settings beat its dev recall@10 of 0.613 (activity-log.md). Recall@10 at 0.90 needs a slower reranker, model B or a GPU, outside this round.
- 2026-10-26: v2's test questions were written in free phrasing and hashed (sha256 `bf12aaa6...4224c`, activity-log.md) before any PR 1 code, so no fix was tuned on them.
- 2026-10-26: The router's second look takes its forecast and advice wording from dev's o01 and o02 only ("stock price", "share price", "go up", "should I", buying or selling shares). Why: wording drawn from v2's test questions would tune on test. Cost: an advice question phrased otherwise gets one more router call, and the router decides again.
- 2026-10-26: The fill never applies when the router names another company or routes out of scope. Why: `guess` reads a name's first word, so "Bank of New York Mellon" reads as BAC and "Johnson Controls" as JNJ; the router lists such a company under `other_companies`, and the untracked-company refusal must still fire.
- 2026-10-26: A sentence that fails only through citations it does not need keeps its other citations (`validate.pruned`), with a warning. Why: x06 cited C5 and C9, C9's quote held, and the answer was refused twice for C5. A bracket with no source letter (`[12]`) is not pruned; it still sends the draft back.
- 2026-10-26: Pitfall: validation's 0.5% amount tolerance rejects ordinary rounding. In E2, Haiku wrote "$4.1 billion" for 4,121,000,000 (0.51% off) twice, and n24 was refused. Before the heading fix it had hedged but kept $4.121 billion. A fix that makes a model answer more plainly can expose this. Not changed in PR 1: how much rounding an answer may carry is the user's decision (todo.md).
- 2026-10-26: Pitfall: a plan estimate from per-question token averages ran low twice. E1's judge used 60K gpt-oss-120b tokens on dev full, not 49K (52 judged answers, longer Haiku answers), and E1b used 72K router tokens, not 65K. A judged dev-full Claude run needs about 60K judge tokens.

From PR 4 and PR 5 (2026-10-27, one branch `calculations-item-labels` from main at d05884a, uncommitted):

- 2026-10-27: The user's rounding rule for n24: an amount passes when it equals its source rounded at the amount's own last stated digit ("$4.1 billion" for 4,121,000,000 passes, "$4.2 billion" fails).
  - **Rulings (mine):** it adds to the 0.5% tolerance and applies in validation only, so nothing that passed before fails. A half rounds either way. The eval's exact match keeps 0.5%, so v1's figures stay comparable. Cost if wrong: n24-style answers count as inexact in exact match.
  - Consequence to know: a whole-unit figure passes too ("$4 billion" for 4,121,000,000), as does any number a quote's table scale lands near ("$1 billion" against a quoted 0.6 read in billions).
  - How: `parse_amount` multiplies by Decimal powers (`1E9`), so `Decimal("4.1") * Decimal("1E9")` keeps the last stated digit in the exponent (4.1E+9); `rounded()` compares at that step.
- 2026-10-27: Calculation sources (K1), as the approved plan says, with these rulings (mine):
  - K1 only on the comparison route with exactly two facts of one unit. Cost if wrong: a numeric answer over two years still has its computed difference sent back.
  - One company's two years run from the earlier, two companies from the lower, so K1's difference is "the second minus the first" and a peer comparison's is never negative. The change in percent only when both values are above 0.
  - Rise and fall words are checked only for one company's two years. "Higher" or "lower" between two companies depends on the sentence's subject, so a wrong "higher" there passes validation, with both figures still stated and checked.
  - `Citation.calculation` holds `inputs` only (the facts' citation numbers, ascending); its lines are the citation's `quote`, as a fact's value line is. The plan said "input citation numbers and text"; a `text` field would repeat the quote. Cost if wrong: one more field, expand-only.
  - The eval harness never rebuilds K1: `load_sources` gives it an empty row for coverage, and the judge reads the answer's citation. `calibrate.py` would read a K1 sentence as failing, since its row has no calculation; no calibration runs this round.
- 2026-10-27: E5 finding: 8 of 10 comparison drafts went back for a second draft (E2: 2). The model put the difference in a second sentence citing [F1][F2][K1] without the two figures, which rule 4's check refuses; c06 cited [K1] alone. Every regeneration held, and precision, coverage and faithfulness rose. A prompt line ("the difference in the same sentence as both figures") would likely cut these, but it changes the answer prompt after E5 measured it, so it waits for the user (todo.md).
- 2026-10-27: E5 finding, not from this PR: c13's reply wrote its Sources block inline ("... [F1][F2][K1]. Sources: [F1] "..."; ..."). `SOURCES_HEADING` wants the heading alone on its line, so the list stayed in the answer, and its amounts passed validation. A weakness for its own PR (the user's rule), in todo.md.
- 2026-10-27: Item labels, as the approved plan says, with these rulings (mine):
  - A pointer is an Item 7 or 8 shorter than 2,000 characters. The four filings' pointers are 157 to 983 characters; a real Item 7 or 8 is far longer. 7A is never relabeled: JPM's and CVX's point into MD&A, and NVDA's and PLD's are real.
  - The opening lines must match whole: "Management's discussion and analysis" for 7; "Report of Independent Registered Public Accounting Firm" or "Management's Responsibility for Financial Statements" for 8, searched after 7's start. So contents rows ("...analysis:", "...Firm (PCAOB ID: 238)") never open a section, and CVX's "Consolidated Statement of Income" inside MD&A does not either.
  - One range per item: the last moved item runs to the end of the item that held it. So Item 8 also holds what follows the notes there: JPM's supplementary pages, glossary and signatures; NVDA's Schedule II and exhibit index; PLD's Schedule III, exhibit list and signatures.
  - A displaced pointer (7 and 8 for JPM and CVX, 8 for NVDA and PLD) keeps no range; its few lines name pages and are no longer chunked.
  - Checked on the real filings: JPM 7 runs 403,071 characters and 8 598,549; CVX 7 99,274 and 8 232,431; NVDA 8 106,569; PLD 8 238,846. The 26 other cached 10-Ks keep every range (`section-ranges.json`, pinned from main's parser before the change).
- 2026-10-27: The final whole-branch review (a fresh reviewer, Opus) found nothing Critical; the fix pass, each red then green:
  - **K1's figures backed amounts of the other kind** (Important): its change of 6.43 passed "$6.4 billion" at the billions scale, and its difference of 0.52 passed "52%". Now the difference backs only an amount, and the change only a percent, each as stated with no table scale (`Calculation.holds`, `held`). E5's 20 amounts in K1 sentences all still pass, checked offline.
  - **A loss that "grew" failed the direction check** (re-graded Important: a correct answer sent back or dropped). Rise and fall words are now checked only between values above 0, where a change was computed.
  - **Quarter labels** (re-graded Important: the card would read "Fiscal 2025" for a Q2 value): K1 names the quarter, "Fiscal 2025 Q2".
  - **Reparse's docstring** overstated "before that filing changes": a failure after the sections are replaced leaves the filing for a rerun.
  - Not changed, and why: "higher" or "lower" between two companies stays unchecked (the ruling above). The rounding rule's wide window for one-digit amounts against a quote's numbers (a quoted "1.6%" backs "$2 billion" at the billions scale) comes from the user's rule plus quote numbers that carry no kind; it stays as the noted consequence.
- 2026-10-27: Pitfall: Windows Application Control blocked the venv's `python.exe` (uv's launcher, unchanged since 2026-10-14), so `uv run python` and every `make` target that runs Python failed with "os error 4551". It worked on 2026-10-26. Cause not confirmed. What worked, in this order:
  1. The base interpreter run as the venv: `__PYVENV_LAUNCHER__=<repo>\.venv\Scripts\python.exe` plus `C:\Users\kwonhyuk\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe -m <tool>`.
  2. For `make eval`, a scratch launcher that loads `.env` with python-dotenv (existing variables win), since `uv run --env-file` queries the blocked launcher even with `--no-project`.
  3. The pipeline tests that start workers with `sys.executable`, with `sys.executable` set to the base interpreter and `__PYVENV_LAUNCHER__` exported.
  - `uv run --isolated` for ariadne-codegen and the venv's `ruff.exe` ran normally.
  - Later the same day (PR 6's session) `uv run python` and every `make` target used ran with no workaround. Cause of either state not confirmed.

From PR 6, first part (2026-10-27, branch `golden-v2` from main at a2b71ec, uncommitted):

- 2026-10-27: Golden v2's build, as the approved plan says, with these rulings (mine):
  - **Carried labels:** v1's final label (the user's where given, otherwise Claude's) moves to each v1 passage whose text survives the re-parse, matched by filing and the text's sha256 (the nearest offset when a text repeats). They sit in their own file, `carried.jsonl` (`from: "v1"`, `v1_chunk_id`, `labeler` human or claude), so v2's `ai_labels.jsonl` and `labels.jsonl` hold only v2's own labeling and audit, and v2's agreement numbers never mix in v1's. Cost if wrong: one more file in the manifest.
  - **v1's pools:** the kept passages, the chunks overlapping a passage whose text changed (labeled again), and what v1's pool sources find on the re-parsed corpus, so each pooled configuration's top 10 stays labeled. Cost: 18 more passages to label.
  - **Questions:** v1's 100 come from v1's frozen file, and the build stops if a rebuild from the database differs from them. v1's split code (DEV, CI, `assign_splits`) is gone, since v2 splits by rule.
  - **Re-parse on the host,** not in the ingest container as reparse's docstring says: the ingest image dates from 2026-10-17, before PR 5's parser, so it would have parsed with the old one.
  - **Labelers:** six Claude subagents in this session (claude-opus-5-5), each a batch of whole questions, with v1's guideline and reason style; no API call, $0 of credits. The plan said "this session"; six labelers kept its context small. Cost: variance between labelers (next entry).
  - **The blind sample:** 50, only from passages Claude labeled for v2 (never a carried one); `AUDIT_MIN_GOLD` stays 20. It drew 28 Claude-gold of 50 (v1: 23 of 60), because the draw takes one Claude-gold passage per question first and 31 questions take part. Cost if wrong: a redraw before the user starts (delete `audit.jsonl`).
  - **`VERSION` is v2 from now,** since `make audit` reads v2's files. Until the freeze every eval exits 3 and `test_the_ci_subset_holds_ten_should_refuse_dev_questions` fails (it loads the frozen set), so CI's eval fails on this branch until the freeze and E8.
- 2026-10-27: Finding: the six labelers drew the line differently for a passage that states the topic but not the question's qualifier. Gold: x21-03/10/16 (Apple's competition in general, "smartphone" not named), x26-02 (capital spending on AWS's technology infrastructure, AI not named), x37-07/08/10/17 (Lilly's capacity expansion, incretins not named). Not gold: x25-01/15 (Verizon's FWA connections, growth not stated), x31-15 (the acquisition not named), x42-14 (F-35 and C-130 without "Aeronautics"). Each question had one labeler, so each is consistent in itself. Not overridden: an override is one more Claude reading of the same text, and the spot check and review settle the passages the sample holds. Lesson: a brief for several labelers states the qualifier rule outright.
- 2026-10-28: Pitfall: Windows Smart App Control is on and blocks the unsigned launchers in `.venv\Scripts` (os error 4551). Triage Copilot's `alembic.exe` was blocked on the night of 2026-10-27. The venv's `python.exe` runs. So every Python tool starts as `uv run python -m <tool>` with the same arguments, which runs the same on CI's Linux.
  - **Checked in this repo (user's request):**
    - Every make target already went through Python (since 2026-10-14, the entry below).
    - The scripts spawn only git, docker compose or `sys.executable`.
    - The pre-commit config documents `uv run python -m pre_commit install`, and its git hook runs `.venv\Scripts\python.exe -mpre_commit`.
  - **Changed:** only `docs/migrations.md` named bare `alembic` commands (4). They now read `uv run --env-file .env python -m alembic ...`.
  - **No `__main__.py` needed:** the workspace defines no console scripts of its own, and `filinglens_api` already has one, which the api container runs.
  - **Not launchers:** `ruff.exe` is ruff's own binary (`python -m ruff` starts it too) and ran. The compose `celery` commands run in Linux containers.
  - **Here the launcher ran:** in this repo the venv's `alembic.exe --help` still exited 0 on 2026-10-28. Smart App Control decides per file; why it blocked Triage Copilot's and not this one is not confirmed.
- 2026-10-28: One rule for v2's new labels (user decision, before the spot check). It supersedes the "Not overridden" ruling above.
  - **v1's written rule** says nothing about qualifiers. It reads the same in all three places: `label.py` (KEYS), `eval-card.md` ("The guideline") and the step 6b plan: "A passage is gold if by itself it states all or part of the answer"; for an absent question, gold only if it answers the question.
  - **The user's strict rule** covers what v1's leaves open: a passage is gold only when it answers the question as asked, qualifier included. The passage itself must establish the qualifier, never outside knowledge.
  - **How (rulings, mine):** one labeler (a single Claude subagent in this session, no API call) checked all 180 gold labels in the 28 questions that had any. The strict rule can only turn gold into not gold, so not-gold labels already follow it. Each question with a failing gold label was labeled again in full.
    - 22 questions followed the rule.
    - 6 were labeled again: x21 7 to 4, x22 11 to 10, x26 4 to 3, x35 8 to 6, x37 5 to 1, x44 6 to 5. 12 passages went to not gold and none to gold.
    - The re-labeled rows replace theirs in `ai_labels.jsonl`, before any audit. Claude's v2 gold is now 168, and v2 holds 318 gold in all with the 150 carried. The 538 carried labels are unchanged.
    - The old blind sample was deleted and drawn again from the final labels.
  - **The calls the labeler found hardest:**
    - x37-11 is x37's only gold now ("current and prospective products", between the Mounjaro launch and incretin volume); read as generic, x37 would have no gold.
    - x44-08 went to not gold: the portfolio "excludes non-industrial properties", and industrial is not logistics.
    - x35-17 and x35-20 went to not gold: the Apple Card and GM card moves, with no consumer wording.
    - x22-05 went to not gold: it names the OpenAI alliance but not the investment.
  - The user's note named "x10, x16". They read the earlier "x21-03/10/16", which means x21-03, x21-10 and x21-16. x16 has no new v2 label; x10's 9 were checked like the rest and followed the rule.
- 2026-10-27: Finding: most chunks of the four moved sections kept their text (36 of v1's pooled passages now under new ids), although every new section starts elsewhere. Likely cause, not confirmed: the chunker ends a piece at a line break, so pieces cut from another start reach the same breaks and line up again.
- 2026-10-27: Pitfall: openapi-python-client runs ruff as a post-hook and only says "ruff is not in PATH" when it cannot. Without it every generated file comes out unformatted. Put `.venv/Scripts` on PATH for the generator. Its files are then CRLF on Windows and show as modified; `.gitattributes` makes git store them as LF, so `git diff` lists only the real changes. Restoring the content-identical ones keeps `git status` honest.

From PR 6, second part (2026-10-31, branch `golden-v2`, uncommitted):

- 2026-10-31: No human spot check in v2 (user decision). The judge model (`LLM_JUDGE`, gpt-oss-120b, another model family than Claude) labels the 50-passage blind sample instead, through `make audit`'s path, so the agreement numbers come out as v1's did. The docs say "AI-labeled, cross-checked blind by a second model; no human spot check in v2", never human-checked.
  - **Rulings (mine):**
    - The model's labels go to `labels.jsonl` through `save_label`, with `labeler` (the model's id) and its reason, so `blind_labels` and `audit_stats` compute them as they did the user's. `final_labels` skips them: a model's label only measures agreement, and Claude's stands on every disagreement. Cost if wrong: if the judge's calls should win, 5 passages flip (x26, x31, x35 and x38 to not gold, x43 to gold).
    - No review of the disagreements. In v1 the review was a human's final call; another model's call would be one more AI reading. `freeze` asks for a review only when the blind labeler is human.
    - The prompt holds the audit screen's rule (`KEYS`: the eval card's guideline with the qualifier clause) and only what the blind screen shows: the question and its kind, the ticker, the item, the passage and the screen's question. The eval card's "so an absent question should end with none" is left out, since the screen never told the user the expected outcome.
    - `audit_stats` names `human_gold` `blind_gold` and adds `blind_labeler`; v1's frozen manifest keeps `human_gold`.
    - `CROSS_MAX_TOKENS` is 1,024: the reply is two fields after gpt-oss's low reasoning. Replies sit in the eval cache under the role `label`.
  - **Result:** agreement 90.0% (45 of 50), Cohen's kappa 0.80 (95% CI 0.62 to 0.96); Claude said gold on 28, the judge on 25. In 4 disagreements Claude said gold (x26, x31, x35, x38), in 1 the judge did (x43). The sample's 3 absent-question passages all agreed.
  - **Spent:** 50 calls, 30,914 tokens in and 4,474 out (estimate 36K to 46K), 14:30 to 14:34 UTC, with 41 short 429 waits (Groq's tokens a minute); none stopped the run.
  - **Reading:** two models agreeing under one written rule, not accuracy. The kappa is far above v1's human spot check (0.10), whose sitting ran at 3 s a passage. x38 shows the qualifier rule cutting both ways: Claude's reviewer kept it gold, and the judge read the passage as not naming 2025.
- 2026-10-31: The harness for v2, as the plan lists it, each part test first (red, then green):
  - `CALIBRATION` is v1's file, since v2 keeps the judge's prompt, schema and model. A test pins the prompt and schema hashes to those v1's official report recorded (`633151ba...`, `36dbdb93...`), so a judge change fails it and needs a new calibration. `calibrate.py`'s `ROOT` follows `CALIBRATION`, so `make calibrate` now opens v1's sample; no calibration runs this round.
  - Floor keys carry the golden version (`v2:retrieval:dev:full`). v1's four keys were renamed `v1:...`, their values unchanged. Why: `--set-floors` only tightens, so without the version v2's floors would have started from v1's, measured on other questions.
  - `previous()` matches the golden version and also takes an earlier `all` report, which holds every suite, so E10's `--claude-primary` run finds E9 as its `versus`. The plan said "an answer run"; a retrieval run takes an `all` report too, since that report holds the retrieval metrics.
- 2026-10-31: corpus-v2: `make corpus-dump` from the re-parsed dev database (revision 0008; 30 companies, 30 filings, 677 sections, 11,257 chunks, 856,438 facts) gave `.cache/corpus/corpus-v2.dump`, 46.5 MB, sha256 `34b9abeb0bae2fed8e6430f63cafc1b789ed570b48adbad100b25e00f8dbcea2`, with no secret value in its SQL. The user uploads it as the release asset `corpus-v2` before this PR's CI runs, since CI's eval and migrations jobs restore it. `corpus-v1` stays published: production runs it until corpus-v2 moves there (PR 7, at the user's time).
- 2026-10-31: The carried labels under the qualifier rule (read only, the user's request; nothing changed). One fresh Claude subagent checked the 150 carried gold labels with the brief Claude's 180 had: 10 would fail, 8 of them Claude's v1 labels and 2 the human's (x14 4, x05 2, x02, x09, x19 and x20 1 each). Two of x14's depend on reading "most significant" as a qualifier. Consequence to know: v2's gold holds two standards, Claude's 168 under the qualifier rule and the 150 carried under v1's rule, about 7% of which the rule would drop. Its verdicts were kept in the session's scratchpad only.
  - Order: the freeze ran before this count finished. The count is read only and changes nothing, so it ran in parallel; the user's order put it first.
  - User decision (after the report): the carried labels stay as they are. The eval card (at the top of its v2 section) and the README (golden v2's block) say plainly that about 10 of the 150 carried gold would fail the strict qualifier rule, so v2's gold mixes two labelling standards.
- 2026-10-31: E8 and v2's dev floors, on the free models CI uses (the run's `LLM_PRIMARY`, `LLM_ROUTER` and `LLM_JUDGE` set to CI's values, which win over `.env` under `uv run --env-file`):
  - Answer, dev ci, `--tag=v2-floors --no-judge` (`20261031T144658Z`): numeric 1.000 (8), comparison 1.000 (3), coverage 1.000 (14), correct refusal 1.000 (10), false refusal 0.067 (x15), router accuracy 0.720 (route 1.000), TTFT p50 1.61 s. Spent: router 25 calls (24 live), 27,662 tokens; Gemini 21 calls (20 live), 74,657 tokens; one Gemini 429 waited 60 s; $0.
  - Retrieval, dev full (`20261031T145959Z`): recall@10 0.595, MRR@10 0.742, retrieval p95 328 ms.
  - `--set-floors` from both: `v2:answer:dev:ci:gemini:gemini-3.5-flash-lite` and `v2:retrieval:dev:full`, which CI gates.
- 2026-10-31: Mistake: the harness's retrieval note was hard-coded with v1's wording, so E8's first retrieval report (`20261031T145742Z`) called v2's gold "spot-checked by a non-expert". Fixed test first: `GOLD_LABELS` gives each golden version its wording. That report and its floors were removed, the suite ran again (accuracy identical, p95 328 against 348 ms), and the floors come from the second report. Lesson: text that describes a golden set belongs to its version.

From PR 7, Claude first everywhere (2026-10-31, the same branch `golden-v2`, uncommitted; the user's second task, one report and one commit message for both):

- 2026-10-31: Claude first everywhere (user decision): every model role tries Claude Haiku 5.5 first, then today's free chain; the judge stays off Claude; CI stays free-only. Today's roles before the change: the router Groq gpt-oss-20b then NVIDIA (Claude barred); answers Claude, Gemini, NVIDIA in production (since 2026-10-21) and Gemini, NVIDIA in dev and CI; the judge gpt-oss-120b; embeddings and reranker local.
  - **Rulings (mine):** `LLM_ROUTER_FALLBACK` mirrors `LLM_ANSWER_FALLBACK` (one setting per role's free model), rather than one switch that heads both chains, so production's answer settings from 2026-10-21 stay valid and the user adds two lines to `.env.prod`. `LLM_ROUTER_FALLBACK` and `LLM_FALLBACK` cannot be Claude, since Claude's stops hand every call to them. Code defaults, `.env.example` and CI stay free-only. Cost if wrong: one more variable than a single switch.
  - `--claude-first` replaced `--claude-primary` (Claude answered on the free run's routes): with Claude routing in production, the headline measures production's chain. Its full test run takes `evals/reports/<UTC day>-claude-first`, and it never sets floors.
- 2026-10-31: Pitfall: Claude's structured outputs refuse a nullable enum. The router's `"type": ["string", "null"]` with `"enum": [..., null]` drew a 400: "output_config.format.schema: Invalid schema: Enum value 'FY' does not match declared type '['string', 'null']'". Fixed in the provider (`claude_schema`: anyOf an enum and null), not in `router.schema`, whose hash keys every cached free-router reply. Found by the live check (two 400s, billed nothing), test first.
- 2026-10-31: Pitfall: `write_report` named an official report by this PC's local date (UTC+8), so a run after 16:00 UTC took the next day's name (`2026-11-01-claude-first`) while its timestamps said 2026-10-31. It now takes `created_at`'s UTC day (test first), and that report was renamed to `2026-10-31-claude-first`.
- 2026-10-31: Mistake: the landing page's `resultRows` let a Claude-first report's side-by-side table (the free run's values under the same row labels) overwrite its own rows, so the first table showed the free run's values as targets and "Not measured" everywhere. The e2e could not see it, since it compares the page with the same function. The screenshot showed it; fixed test first (the first table with a label wins). Lesson: look at the screenshot before trusting a spec that shares the code it checks.
- 2026-10-31: The official v2 runs (the eval card has the numbers): Claude first is the headline (false refusal 4.4%, router accuracy 0.982), slower than the free chain (time to first token p50 2.11 s against 1.47 s); the free-only run gives v2's test floors.
  - **Spent:** the routing check, 1,970 tokens in and 62 out (estimate about 1.5K), after two 400s that billed nothing. The Claude-first run: 120 Claude calls, 524,353 tokens in and 27,140 out, about $0.066 of credits (the second estimate said about $0.05, at most $0.08); its judge used 72,201 gpt-oss-120b tokens (estimate 61K). The free-only run's judge used 60,971 (first estimate 52K). Today's judge total: about 168.6K, under FilingLens's 175K.
  - The estimates grew twice. The user was asked again after the routing check, before the Claude run (the user's rule: ask again when an estimate grows, even on a free tier); the judge's second growth showed only during the run.

From Recent questions (2026-11-01, branch `recent-questions` from main at 0bfb840, uncommitted; plan approved the same day):

- 2026-11-01: Recent questions, the session part of History (user decisions, asked before the build):
  - **Redis at rest:** accepted and documented (deploy.md, Recent questions). Stored answers leave memory at their TTL or at sign-out; Redis's default snapshots can keep a live key on disk for up to about an hour more.
  - **Limits:** a replayed answer still passes `answer_limits` (10 a minute per key, AI on, the budget), though it calls no model. Reason: one rule for every answer the stream gives.
  - **Old cookies:** the session cookie moved to v2 (`v2.<sid>.<expiry>.<mac>`, a random 128-bit sid), and v1 stops verifying at deploy, so everyone signs in once more. Reason: v1 held no id, so two sign-ins in one second had the same token, and no v1 branch is kept.
  - **My defaults, approved:** degraded answers (the reranker timed out) are not stored, so a repeat tries again; the question on screen is left out of the list, so it never repeats right under its own answer.
- 2026-11-01: Rulings (mine, small, listed in the report): the list and the delete answer 503 `transient` with `Retry-After: 5` while Redis is down, and the API's description and 503 doc say so; the normalisation reuses `filinglens_llm.validate.STRAIGHT_QUOTES` (U+2018 to U+201F) instead of four quote marks of its own; times read "2:02 PM" (en-US, the browser's zone), like the app's other dates, where the plan wrote "14:02"; the list also leaves out a repeat asked in other words (by its stored time); `RecentAnswers` takes a clock (`now`), as `Answerer` takes `today`, so tests order answers.
- 2026-11-01: Pitfall: a second parameter named other than `body` in `stream_answer` makes FastAPI embed both bodies (`{"body": {...}}`), a breaking contract change. The route re-declares `body: AnswerRequest`, the dependency's name, so FastAPI dedups it, and the header the same way (one `X-Session-ID` in the spec).
- 2026-11-01: Pitfall: no wrapper generator around the answer's events. A wrapper that never started would skip `aclose()` when the client leaves before the first event, and the in-flight slot would leak (`test_limits.py`'s in-flight test, now run with and without a session). The store write sits in the route's loop instead, between the deadline block and the `yield`, so a slow Redis cannot turn a validated answer into `failed` (`test_a_slow_store_never_turns_a_finished_answer_into_a_failure`).
- 2026-11-01: Pitfall: Redis's error replies can quote the command's arguments ("unknown command, with args beginning with: ..."), and here those hold the question. The store logs the error's type only; its test's fake Redis raises exactly such a reply.
- 2026-11-01: Pitfall: Playwright treats `aria-disabled="true"` as disabled, so `click()` waits until it goes. The spec that checks the list does nothing while an answer streams first waited out the answer and then clicked; it clicks with `force: true`.
- 2026-11-01: Pitfall: a `\u2018` escape written through the file tools lands in the file as the character itself, which ruff's RUF001 flags. The store reuses `STRAIGHT_QUOTES`, and the tests' curly quote and full-width digits carry `noqa: RUF001`, as `answer.py`'s quote marks do.
- 2026-11-01: Mistake: the store's code was written before its tests, against the plan's tests-first order, so no test had a red run. Made up for by mutation, each change reverted at once: dropping the refused-and-degraded guard failed 2 tests, a key without companies and years failed 2, and logging `str(exc)` failed both log-privacy tests. Logging `repr(exc)` failed only the type test: redis-py 8's `repr()` of a `RedisError` prints `server:RedisError`, never the message.
- 2026-11-01: Production Grafana's first-start hang (the user's report: `/apis/...` and `/api/folders` over 5 minutes, "failed to resolve user: context canceled", right after background plugin installs). Cause, measured on dev's Grafana 13.2.4 with fresh first starts:
  - **Memory:** production's 256M is too small for Grafana 13.2. Uncapped, it held about 260 MB of anonymous memory and about 400 MB in all. At 256M with no install, the cgroup hit its limit 9,968 times in 213 s, with 516,177 file refaults and 61,337 major faults: thrashing on its own code and its 13 bundled datasource processes'.
  - **Installs:** every first start installs 17 plugins from grafana.com in the background, the Drilldown and Advisor apps and newer copies of 13 bundled datasources (Prometheus and Jaeger included), restarting their processes; memory reached 255.1 of 256 MiB during them. Production keeps no Grafana volume, so each recreate is a first start.
  - **Fix (config only):** `GF_PLUGINS_PREINSTALL_DISABLED=true` in the base compose, production's limit 512M. Run D (both): no install, 252 to 261 MiB, `max 0`, 12 major faults.
  - Light requests answered within 0.21 s in every dev run, even at the limit; the hang needed production's real browsing. Usage reporting and update checks were already off.
  - The "Consumers per work queue" panel (service health and ingest dashboards) shows No data in production because no work queue exists there: RabbitMQ reports per existing queue, and only the worker or a job's first publish declares them. Documented in monitoring.md, not changed: a "no value" text would also cover a broken scrape.
- 2026-11-01: corpus-v2's production runbook (deploy.md) was rehearsed on a scratch database, `restore_drill`, inside dev's Postgres (started by exact name, stopped again after): corpus-v1 as the stand-in, then `pg_dump` (3 s), `pg_restore --single-transaction --clean --if-exists` of corpus-v2 (11 s) and of the backup (11 s), each followed by the counts, the known answers and the item labels. `--clean` over an existing corpus at the same revision works in one transaction, so a failure leaves the old data.
- 2026-11-01: Pitfall: Git Bash rewrites a `/tmp/...` argument of `docker exec` into `H:/.tmp/...` (MSYS path conversion), so the drill's first `pg_restore` could not open its file and nothing changed. `MSYS_NO_PATHCONV=1`, with host paths written `H:/...`, fixed it. PowerShell, which the runbook uses, has no such rewrite.
- 2026-11-01: Compose's `up -d --no-deps grafana` also created the project's empty `prometheus-data` volume. Its removal by name was refused by the session's safety check; it stays, empty, for the user to remove or for monitoring's next start to use.

From landing round 1 (2026-11-02, branch `landing-round-1` from main at 58baddd, uncommitted):

- 2026-11-02: Landing round 1: header, hero and logo (user: "FL landing, round 1 of 2"). The first paste held 21st.dev's hero4 ("Bag\Ui") code under the name Prompt Bond, and two files it named were missing (`_tmp/21st/h5-hero.png`, `_tmp/logos/fl-logo-sheet.png`). Prompt Bond's source sits behind a 21st API key (its registry answered 403; the public page shows only the demo wrapper), so work stopped there and the user was asked. Their answer: hero4 is for the header only, Prompt Bond's prompt pasted in full, and the logo comes from `filing-lens-logo.png` (variant #6, cropped).
- 2026-11-02: Decisions taken without the user, listed in the report:
  - No Tailwind, shadcn, clsx, tailwind-merge or lucide-react, and no `components/ui/`: FilingLens styles with plain CSS tokens and keeps components in `web/components/`, so Prompt Bond's Tailwind classes became CSS and its icons inline Lucide's geometry.
  - Packages pinned at releases at least two weeks old: motion 14.3.0 (14.9.0 was three days old), three 0.186.1 (0.187.0 likewise), @react-three/fiber 9.8.2, @shadergradient/react 2.4.20.
  - The story is x12, two cited passages; n01, the old hero, cites an XBRL fact and has no passage to slide in.
  - System fonts stay (design.md): Prompt Bond's fonts come from cdn.21st.dev, which `font-src 'self'` blocks. The headline uses Segoe UI Variable Display, a variable system face on Windows 11, so the pointer's weights still work there.
  - The still is the story's end, in HTML; the moving story starts from the question after the load. Phones get no WebGL at all, the membrane included.
  - The hero's two calls to action and its offline note went; the header has Sign in and "Open the demo".
- 2026-11-02: Pitfall: `--mark` is already the highlighter's colour token, so the logo keeps `--logo` (the `.result` lesson again: search a name before using it).
- 2026-11-02: Pitfall: the CSP's `style-src` has a nonce and no `'unsafe-inline'`, so a style attribute in server HTML or an injected `<style>` is blocked. Prompt Bond relies on both (a hoisted `<style>`, inline font weights). Its CSS moved to `hero-live.css`, the still carries no style attribute, and only scripts set styles (CSSOM, which the CSP allows). The e2e CSP guard catches a regression.
- 2026-11-02: Pitfall: the app headers' phone rule `.brand { flex: 1 1 100% }` (the name on its own row) made the landing header 476 px wide at 390. The e2e phone check caught it; `.landing-head .brand { flex: none }` fixed it.
- 2026-11-02: Pitfall: headless Chromium has WebGL only with `--enable-unsafe-swiftshader`, and only in software. The moving story then crawled (each frame counts at most 40 ms of story time), and four workers running it starved the machine, so unrelated tests timed out. The landing spec now runs with reduced motion except its one moving-story test; Playwright takes `launchOptions` only at a file's top level. Screenshots of the moving hero use headless Edge (`channel: "msedge"`), which draws on the GPU; the story then ran in about 20 s.
- 2026-11-02: Pitfall: WebGL work starting right after the load event held the first paint past it (desktop FCP 500 ms, in software WebGL). Prompt Bond's own field waits two frames before mounting, so the loader now waits two frames after the load event, then idle time (FCP 312 ms).
- 2026-11-02: ShaderGradient fetches HDR maps from `ruucm.github.io` only for `lightType: "env"`; Prompt Bond's `"3d"` uses an ambient light, so nothing is fetched from another site. An e2e test checks every request's origin.
- 2026-11-02: FilingLens's Gemini key has been in its own Google project since 2026-10-31 (user), so it no longer shares Triage Copilot's quota (deploy.md step 28).
- 2026-11-02: Mistake, found by CI: 3 web e2e tests timed out on GitHub's runners (axe on `/` in light and dark; Pause in the WebGL test). Cause, measured locally: Playwright's bundled headless shell draws WebGL in SwiftShader on every machine, with or without `--disable-gpu`, and `failIfMajorPerformanceCaveat: true` does not refuse it. So the moving hero ran in software everywhere the suite ran, fast enough on this PC and too slow on CI. The earlier "it passes locally on a real GPU" was not true of the e2e browser; only the Edge screenshots used the GPU.
  - Fix at the source (user's direction, no longer timeouts and no CI-only switch in the app): the hero probes WebGL with `failIfMajorPerformanceCaveat: true` and reads the renderer's name; a software one (SwiftShader, llvmpipe, softpipe, Windows' basic driver; `lib/motion.ts`, unit-tested) keeps the still, as phones do, and the hero says which it chose in `data-motion`.
  - Tests: a11y runs with reduced motion, so it never depends on the moving hero. The WebGL test reads the renderer and asserts what it calls for: the still and no three.js on software, the moving story on a graphics card. `E2E_CHANNEL=msedge` runs the suite in headless Edge on the GPU, where the moving branch runs; the bundled shell runs the still branch, as CI does.
  - Lesson: check which renderer a test browser really has before trusting a performance-sensitive test that passes locally.

## Preferences and Instructions

- 2026-10-14: The three portfolio projects run in parallel Claude Code sessions on one PC, sharing Docker. Each project has its own port range and compose project name; never prune or remove another project's Docker resources (user setup).
- 2026-10-13: General coding rules live in `AGENTS.md`. `CLAUDE.md` imports it so Claude Code loads the rules.
- 2026-10-13: Markdown filenames use kebab-case (for example `docs/migrations.md`).
- 2026-10-17: Never read the user's GitHub token or Git Credential Manager, even for a read-only call (user). Artifact and job-log downloads need authentication (401 and 403 without it), so the user downloads such files and gives a path. Runs, jobs and PR comments are public.
- 2026-10-18: When a cost estimate grows before a live model call, ask the user first, even on the free tier (user). This followed the twin judge replay: its estimate grew from about 1.8k to about 3.5k tokens, and the call went ahead after only saying so.
- 2026-10-18: Shipping (user rule, stated 2026-10-18, "since 16:00 today"; also in AGENTS.md, Git):
  - Claude Code never commits, pushes, opens or merges pull requests, and never runs gh (the GitHub CLI) for anything, read-only commands included.
  - The user ships with the ship command (`H:\Projects\projects\_tools\ship.ps1`). It commits, pushes, opens the pull request, waits for every check and merges only when all pass.
  - When you need a CI or pull request result, ask the user.
- 2026-10-18: Before a PR is reported ready, show that CI's eval makes no model call (user rule, step 9 plan). Either:
  - its diff touches no `EVAL_INPUTS` path, so the eval is skipped; or
  - it touches only code the answer suite never runs, so every cache key is the one main's last eval saved. The user then confirms the repo's `eval-calls-*` Actions cache still exists.
  - If any miss is possible, stop and give the estimate first. A cold dev ci run is about 28K gpt-oss-20b tokens and about 20 Gemini requests.
- 2026-10-18: Weaknesses found while planning get their own PR before the step, like bugs (user, step 9 plan). An unused route is turned off rather than tested, unless something uses it.
- 2026-10-21: A vulnerability that CI's scans report is fixed at the source, in its own PR from main, never with an ignore file or allowlist (user). First case, branch `certifi-bump`: CI's vuln-scan failed on PR #22 with one CRITICAL in `uv.lock`, certifi 2026.7.22, GHSA-6q48-6c7w-9gw2 (emSign roots with compromised intermediate keys), fixed in 2026.10.19.
  - **Steps, in order:**
    1. branch from main at aca22a6, which an anonymous fetch showed as GitHub's main;
    2. `uv lock --upgrade-package certifi`, then the lock's header set back to `revision = 3` (the pitfall below);
    3. `uv lock --check`, then `uv sync`;
    4. `make vuln-scan`; a control scan of an old image; both images rebuilt and scanned;
    5. `make lint`, `make test`.
  - **Why from main:** the advisory is in main's lock, so every PR's vuln-scan fails until main has the fix.
  - **Pitfall, the lock's header:** uv 0.12.23 (pinned on the PC, in the Dockerfile and in CI) writes `revision = 5` whenever it writes a lock. Main's lock was at revision 3, last written by Dependabot (#4).
    - The header went back to 3 by hand, so the diff is certifi's three lines.
    - uv 0.12.23 reads a revision-3 lock as current: `uv lock --check` passed, and `uv sync` changed only certifi.
  - **Control:** the local Trivy database knew the advisory. The 4-day-old `filinglens-api:ci` image showed exactly this CRITICAL, and the images rebuilt from the branch showed none.
  - **Age:** 2026.10.19 was uploaded on 2026-10-20, inside Dependabot's 7-day cooldown for uv. It was taken at the user's request, as a security fix. Its wheel's PEP 740 attestation names `certifi/python-certifi`, workflow `release.yml`.
- 2026-10-24: Second scan fix, branch `next-security` (same rule as above: fix at the source, no ignore entries). Trivy found next 16.3.8 (2 CRITICAL, 1 HIGH), and in `uv.lock` filelock 4.1.1 and virtualenv 21.14.7 (4 HIGH, dev-only). All fixed by upgrading (activity-log.md).
  - **Does FL's web use the affected features?** No for the two RCEs: no `next/image`, no `images` config (so no SVG image optimization), no `"use cache"` or `cacheComponents`. Yes for the DoS: `web/app/login/actions.ts` is a Server Action. Not confirmed: whether the default `/_next/image` route was reachable; it needs SVG enabled, which is not set.
  - **Pitfalls:** `make vuln-scan` stops at the first failing lockfile, so run the web and `clients/ts` scans by hand to see every finding. `uv lock --upgrade-package` rewrites the header to `revision = 5` again; set it back to 3 until main moves.
- 2026-11-01: Third scan fix, on branch `golden-v2` (the user's call this time, rather than its own PR from main; same rule otherwise: fix at the source, no ignore entries). CI's security job found 5 HIGH in `uv.lock`: graphql-core 3.3.0 (CVE-2026-119286, fixed in 3.3.1) and pyasn1 0.6.4 (CVE-2026-119194 to 119197, fixed in 0.6.5). Both fixed by upgrading (activity-log.md).
  - **Release age (user):** respect the project's release-age setting, and stop and report if it blocks a version. uv has no `exclude-newer`, so the setting is Dependabot's 7-day cooldown for uv. Both fixes were inside it (uploaded 2026-10-25 and 2026-10-27, UTC). The work stopped; the user then took both as a security exception, as with certifi.
  - **How the age was checked:** PyPI's JSON API gives each file's `upload_time_iso_8601`. `uv lock --upgrade-package ... --dry-run` shows what uv would take: the newest release, not necessarily the fixed one, so check that version's age.
  - **Provenance:** graphql-core 3.3.1 carries PEP 740 attestations (`graphql-python/graphql-core`, `publish.yml`). pyasn1 0.6.3 to 0.6.5 carry none; upstream has the `v0.6.5` tag.
- 2026-10-18: UI accessibility is checked by axe on every page plus keyboard-only and phone-width specs (user). Reason: axe misses focus order and keyboard-only flows.
- 2026-10-18: Container go for step 9 (user), also during Triage Copilot's exam window, since neither use makes a model call:
  - Uses: Testcontainers for `make test-int`, and FilingLens's own dev Postgres (`filinglens-postgres-1`) for `make demo-export`.
  - Conditions: check ports first; start and stop only FilingLens's own containers, by exact name; never touch FreightAudit's or Triage Copilot's containers or volumes; never stop Docker.
  - Model calls stay off. Any other container needs a new go.
- 2026-10-21: No Anthropic key on the public deployment: production runs free providers only (the user's standing rule, stated at the step 10 plan's approval). Claude stays a dev and eval option while its credits last.
- 2026-10-21: Correction to the eval check above (2026-10-18). "Every cache key is main's" covers code only. A question that searches takes its prompt's passages from the search, so it can still miss when the search ran differently on the runner.
  - Since `rerank-deadline`, the answer suite's searches never degrade. A miss is then a variant CI's cache never answered (Solved Problems, 2026-10-21).
  - Before a PR is reported ready, give the estimate for those misses.
- 2026-10-21: Anthropic spend (user). The organization's monthly limit is $50, shared by FreightAudit, FilingLens and Triage Copilot. FilingLens's share is $15 until 2026-11-10, when the credits expire. FilingLens's daily Claude budget is sized from the $15, not the $50.
- 2026-10-21: Claude first in production (user, branch `claude-first`, before 10c). It supersedes the rule above that kept any Anthropic key off the public deployment.
  - **Chain:**
    - production sets `LLM_PRIMARY=anthropic:claude-haiku-5-5` and `LLM_ANSWER_FALLBACK=gemini:gemini-3.5-flash-lite`, then NVIDIA;
    - no setting was renamed.
  - **Off for good, in every process** (`budget.ClaudeLedger`; Redis `ai:claude:off`, no expiry):
    - credits gone (a 402, or a 400 naming a spend limit or the credit balance);
    - a rejected key or model (401, 403, 404), with a log error and the `ClaudeKeyOrModelRejected` alert;
    - from `ANTHROPIC_CREDITS_EXPIRE`.
    - Turning Claude back on means deleting that key and restarting the api.
  - **One answer only:**
    - a 429, with or without `Retry-After`; this replaced the old reading of a 429 without it as a spend cap;
    - the daily budget used up (`ai:claude:<date>`, `CLAUDE_DAILY_TOKEN_BUDGET` 1,500,000, at most $0.75);
    - a ledger that cannot be read (fail closed).
  - **Limits:** `CLAUDE_MAX_TOKENS` 1,052 per call. A prompt over 100,000 UTF-8 bytes never goes to Claude: a token holds at least one byte, so such a prompt stays under `LONG_PROMPT` tokens.
  - **Budgets:** Claude's tokens leave the free counter (`ai:usage:<date>`), so the free budget keeps counting the router and the free models.
  - **Evals share Claude's ledger:** it lives on the API's Redis database, not db 15. The prod stack has its own Redis with no host port, so prod and the local evals still count apart.
  - **Evals:** the official run refuses a Claude `LLM_PRIMARY`. `--claude-primary` is a labelled local run: it reuses the official routes, is reported beside the official run, is never floored and is refused under `--ci` or `CI`.
- 2026-10-21: Claude's two daily budgets stay separate, and prod's Redis gets no host port (user, answering the question `claude-first` left open before shipping).
  - **The question:** the evals keep Claude's ledger in the Redis database of `.env`'s `REDIS_URL`, the dev api's (`claude_redis` in `evals/harness.py`). Prod's Redis publishes no host port, so prod counts its own day. One budget for both would need prod's Redis on a host port.
  - **Decision:** two budgets, each `CLAUDE_DAILY_TOKEN_BUDGET` 1,500,000 tokens (at most $0.75):
    - prod's, in its own Redis;
    - dev's, shared by the dev api and the local `--claude-primary` runs.
    - Prod's Redis keeps no host port, as plan point 2 has it for every data store.
  - **Why (user):**
    - prod's worst case is $0.75 a day, about $15 to 2026-11-10, FilingLens's share;
    - local `--claude-primary` evals are rare, and only the user starts them;
    - the Anthropic organization's $50 monthly limit is the hard stop.
  - **Cost of the choice:** on a day with a local Claude run, the two budgets together can spend up to $1.50.
  - **What we did, in order:** recorded it here, in the step 10 plan (Context, and the `CLAUDE_DAILY_TOKEN_BUDGET` row), todo, context, README and the activity log; then ran `make lint`. No code changed, since the code already counts apart.

## Solved Problems

- 2026-11-01: Two answer-path log lines carried model-written text (found while planning Recent questions; fixed first on `answer-log-privacy`, under the bug-fix-first rule).
  - **Problem:**
    - `answering.py`'s "answer failed validation, regenerating" logged `problems=checked.problems`. Each problem quotes the draft sentence it found (`answer.py:160`), for example `"Apple paid its suppliers $999.9 billion [C1].": the amount … is not in the sources it cites`.
    - "router reply broke the rules, asking again" logged the router's problems, which name the tickers the model chose.
    - No test captured the answer path's logs, so nothing pinned that questions and answers stay out of them.
  - **Fix:**
    - Both lines log the count (`problems=len(...)`). The problems still go to the model in its retry prompt.
    - The redaction regex also covers `session`, `session_id` and `X-Session-ID`, as defence in depth for Recent questions' header. `sessions=3`, a count, stays visible.
  - **Tests:**
    - `test_a_regeneration_logs_how_many_sentences_failed_but_not_the_question_or_draft` and `test_a_router_retry_logs_how_many_rules_broke_but_not_the_tickers` (capsys plus `configure_logging("api")`).
    - `test_session_ids_are_redacted_like_credentials`.
    - All three failed first, on the draft sentence, `APPL` and the session id in the output, then passed.
  - **Lesson:** a problem list written for the model quotes user or model text. Log its length, never its items.

- 2026-10-25: Ask sent a session that ended mid-question to `/login?next=/`, which became the landing page with #29 (found while planning mockup features 2; fixed first on `ask-sign-in-return`, under the bug-fix-first rule).
  - **Cause, my mistake in #29:** moving Ask to `/ask`, I searched for quoted `"/"` paths (`["'`]/["'`?]`). That missed `"/login?next=/"`, whose last slash follows `=`, not a quote. Ask still worked; only the return after signing in again was lost.
  - **Fix:** `ask.tsx` sends a 401 from `/api/answers` to `/login?next=%2Fask`, the proxy's own form.
  - **Test:** `auth.spec.ts`: on Ask, clear the cookies and ask; the BFF answers 401; the URL must be `/login?next=%2Fask`, and signing in must land on Ask. Red first (`next=/`), then green.
  - **Audit** (grep of `next=`, `location.assign` and `redirect(` under `web/`): the proxy keeps the page's own path; `requireSession` and a plain sign-in default to `/ask`; logout goes to `/login`; the 404 and landing links point at `/ask`. No other `next=/`.
  - **Left as is (reported):** a 401 from `/api/sources`, for a session that ends between an answer and its sources lookup (milliseconds apart; sessions last 8 hours), shows "Sources could not be loaded." rather than a sign-in.
  - **Lesson:** when a route moves, search for its path inside other strings too (`next=/`, `href="/"`, `assign("/`), not only for the quoted path.

- 2026-10-21: `--claude-primary` took its routes from `.env`'s `LLM_PRIMARY` (found in the docs pass on `claude-first`; fixed the same day at the user's request, test first).
  - **Problem:** with `LLM_PRIMARY=anthropic:claude-haiku-5-5` in `.env`, README step 9's setup and where the official run's refusal points, the run reused Claude's own router replies. Its report then sat beside an earlier Claude report, not the official run. The test pinned only a free `LLM_PRIMARY`.
  - **Fix (user's rule):** `--claude-primary` always takes the official free run's routes, those of the default `LLM_PRIMARY` (`EvalSettings.model_fields`), whatever `.env` says. An explicit `--router-primary` is overridden too; no test pins that.
  - **Test:** the Claude-configuration test runs a free and a Claude `LLM_PRIMARY` row. The Claude row failed first (`'anthropic:claude-haiku-5-5' == 'gemini:gemini-3.5-flash-lite'`), passed after the fix, and failed again with the bug put back. The official run's untouched-settings check moved to its own test.
  - **Lesson:** a configuration that must match the official run names the official model itself, rather than reading it from the environment.

- 2026-10-21: CI's answer eval missed its reply cache on x15 and a09 on 10b's PR. Then Google failed both live calls: a 503, and an answer unfinished at 30 s. A read-only investigation found the cause; branch `rerank-deadline` fixes it.
  - **Cause:** the primary call's key hashes its prompt, and the prompt holds the 12 passages search returns.
    - The answer suite searched with the API's 500 ms rerank deadline. Past it, search keeps fused order, so the passages, the prompt and the key followed the runner's speed.
    - Not 10b: it changed no key input, and both router keys still hit.
  - **Why x15 and a09:** with the router reply cached, the guessed search (`router.guess`, "Caterpillar" to CAT) and the plan's search start almost together.
    - When the route names no tickers, the guess is discarded but ran on until the answer ended.
    - Reranks queue on `_rerank_lock`, so the plan's rerank waited inside its own 500 ms. On this PC a rerank takes 128-138 ms.
  - **Fix (a):** the answer suite waits up to 60 s for the reranker, as the retrieval suite does (`harness.eval_settings`).
  - **Fix (b):** a guess the plan does not use is cancelled as soon as the plan is known, in production too. `_rerank` now marks a cancelled call abandoned, so a call still queued skips the model.
  - **No key changes for a search that met 500 ms:**
    - The deadline is no key input. `answer_path` holds the models, revisions, rerank candidates and tokens, and the index hash; a pin row covers the deadline.
    - A search that met 500 ms ranks the same under 60 s, so its prompt and key stay the same.
    - Cancelling a guess the plan never used changes no prompt.
    - Only the resume file's name changes, since its digest holds the deadline. That matters only for a run interrupted across the change.
  - **What can still go live in CI:** only a question that searches, and only where CI's cache lacks the reranker-order variant. Each calls once, and the router calls stay cached.
    - dev ci: 9 questions (c06, c07, c11, x06, x11, x15, x16, a02, a09). At worst 11 Gemini calls, about 59,500 input tokens.
    - nightly (test split): 11 questions. At worst 11 Gemini calls (about 60,700 input tokens) and 8 judge calls (about 8,000).
    - All on free tiers, so $0 billed. A different CPU's float results can still reorder close scores (rare).
  - **CI's cache:** only CI runs fill it, never local runs. Locally, 2 of 1,015 answer records were degraded, so local replies are almost all the reranker-order variant.
    - A PR run's cache can be restored only by re-runs of that PR, not by `main` (GitHub's dependency-caching reference, read 2026-10-21). So the push to `main` after a merge can make the PR run's live calls once more.
    - Entries unused for 7 days are evicted, which would make the next run cold.

## Known Issues and Pitfalls

- 2026-10-21: Pitfall: gitleaks' `generic-api-key` rule matches across CRLF line ends.
  - In `.env.example`, `GEMINI_API_KEY=` followed by `GROQ_API_KEY=` is flagged in a Windows working copy (`core.autocrlf=true`).
  - main's own file with CRs added gives the same finding, and with LF it scans clean. CI scans LF blobs.
  - So scan files with CRs stripped before reading such a finding as a secret.
- 2026-10-21: Pitfall: a deliberate break of `set_floors` wrote the repo's `evals/thresholds.json`, because the new test had not pointed `THRESHOLDS` at a temp file. The rewrite equalled HEAD's bytes, and the CRLF checkout was restored. Tests that could write floors now monkeypatch `THRESHOLDS`.

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
- 2026-10-15: Smart App Control (on, enforced) blocks `torch_python.dll` of torch 2.13.0 and 2.14.1 every time (Code Integrity events 3077/3033); 2.12.x and older load. The llm package pins `torch>=2.12.0,<2.13` on Windows only (`sys_platform == 'win32'`, user request 2026-10-16), so Linux, the images and CI, takes the current torch (2.14.1+cpu in the lock). A first load of other new native files (numpy's `_philox`) was blocked once and passed on retry.
- 2026-10-15: `UPDATE ... SET status = CASE WHEN ... THEN :a ELSE :b END` sends the parameters as text, and Postgres refuses text for the `filing_status` enum; type the branches with `literal(value, Filing.status.type)`. This failed all 30 filings at the end of embed on the first run (vectors stored); replaying `embed.dlq` after the fix indexed them.
- 2026-10-15: gpt-oss-20b routed "revenue in fiscal 2027" as out_of_scope until the prompt said only the topic decides out_of_scope, with that example; the time-trap check then refuses it by name.
- 2026-10-15: `uv run --env-file` cannot parse an unquoted value with spaces (compose can); `.env` quotes `SEC_USER_AGENT`.
- 2026-10-16: NVIDIA retires catalog models (gpt-oss-120b on 2026-09-03), and a retired id answers 410 with the end-of-life date in its body. Fixed in 6b (user request): `providers.failure` now maps 410 like 402, to `AiUnavailableError` (permanent, no retry, 503 `ai_unavailable` once no fallback is left). Before, it was `UpstreamError`, and a retired `LLM_FALLBACK` ended an answer in 502.
- 2026-10-16: A candidate pool (each reranker's top 10 plus the top 5 of vector, full-text, hint-phrase and item-section sources) can miss gold that sits in an unlikely spot. CAT's backlog paragraph sits among the patents text of Item 1, so x15 lost all its gold this way. A hint-phrase check found no other question with no pooled chunk for its most specific phrase. Broad phrases still leave chunks outside the pools (for example 5 of 13 "concentrates and syrups" chunks for x07), so some gold may be unpooled. The retrieval report's judged@10 shows how much of each top 10 carries a label.
- 2026-10-16: One run's rerank p95 can rank two close configurations the wrong way round. TinyBERT's single-run p95 (217 ms) looked slower than MiniLM-L-2's (194 ms), yet pooled over three passes it was faster (162 against 184 ms). Compare close latencies over repeated, alternating passes.
- 2026-10-16: `split_sentences` (validate.py) split after "U.S." when a capital followed. Validation then saw "…sales from the U.S." as a sentence without a citation and dropped it, leaving "Government, either as a prime contractor…" as an orphan fragment (x16's final answer). Fixed the same day (user request):
  - A period after an abbreviation (`ABBREVIATION`: initials such as U.S., e.g. or N.A., and Inc., Corp., Co., No., etc.) ends a sentence only when a common sentence starter follows (`STARTER`: The, It, However...).
  - Limit: an abbreviation that really ends a sentence before another capitalized word ("in the U.S. Revenue rose") stays joined to the next sentence.
  - Reach: of the 62 cached drafts in the latest dev run, only x16 had a cut after an abbreviation. None of the calibration sample's 30 sentences or 14 judge prompts change, so its cached judge calls still hold.
  - `evals/calibrate.py` still skips fragments after "U.S." and answers trimmed by validation when it draws; both date from before the fix, and v1's sample is frozen.
- 2026-10-16: On a Core `AsyncConnection`, `connection.scalars(select(Model))` returns the first column (the ids), not ORM objects; read rows with `execute` instead. The harness's dry run with scripted models caught it before any quota was spent.
- 2026-10-16: The router (gpt-oss-20b) causes 12 of the 15 dev false refusals. Route accuracy is 1.000, but router accuracy (route, tickers, years, metric) is 0.671.
  - It guesses tickers from company names and gets 6 wrong, each refused as an untracked company: GOOG (GOOGL), HST (HD), CONP (COP), UHG (UNH), FMS (FCX), and NSC with UPU for a UNP question that names Norfolk Southern.
  - It leaves `metric` null on comparison questions, so no facts are read, the search finds no figures and the model replies INSUFFICIENT: 6 refusals (c01, c03, c07, c08, c09, c10), and comparison match is 0.200.
  - Smaller misses with no false refusal: no tickers for x08 and x11 (an unscoped search, still answered); absent a04, a06 and a07 routed out_of_scope; t07 without its fiscal year.
  - Not fixed yet (user decision pending). Likely fixes: give the router the tracked companies' tickers and names, and require a metric for comparisons of reported figures.
- 2026-10-16: Router v2 (user decision; details and numbers in `docs/prompt-log.md`, the new prompt log).
  - **Tracked companies:** the router sees them, its tickers are an enum of them, and untracked ones go in `other_companies`. A reply is checked in code and asked again once; a ticker still unknown is refused.
  - **Comparisons:** each needs a metric.
  - **Code fixes:** names the model misfiles as other companies are matched to tracked ones. An untracked company is refused only when nothing tracked is named, or when its figures are needed.
  - **Dev, gate off:**
    - Numeric exact match 0.821 to 1.000, comparison match 0.200 to 1.000.
    - False refusal 0.288 to 0.096, and correct refusal stays 1.000.
  - **Sweep:** still no feasible threshold. False refusal stays 0.096 for any t up to 4.338, so `RELEVANCE_MIN` stays -3.0.
- 2026-10-16: Judge calibration sample (user decision, option A): 30 sentences from the router-v2 dev run, frozen in `evals/calibration/v1/sample.jsonl` and shuffled. 21 are natural (16 that pass the validator, 5 that fail it), and 9 are constructed negatives (a one-passage citation pointed at another retrieved passage the answer never cited). The eval card says constructed negatives may be easier to catch.
- 2026-10-16: The 429 rule in `evals/calls.py` now depends on Retry-After. A 429 without one (Gemini) stops the run on the 3rd in a row, one with a short Retry-After (Groq) on the 10th, and a Retry-After over 120 s stops it at once. Reason: large judge prompts under Groq's 8K tokens-a-minute limit drew three short waits in a row and stopped calibration runs that still had quota. Groq's 200K tokens-a-day limit is not in its headers. When it is nearly used up, a small request still passes while a large one gets a long Retry-After, which shows as exit 2.
- 2026-10-16: Groq's daily limits refill continuously, not at a fixed hour. At 07:00 UTC, with 111 of 1,000 requests used, `x-ratelimit-reset-requests` read 2h39m50.4s, exactly 111 x 86.4 s. The tokens-a-day limit presumably refills the same way, about 139 tokens a minute for gpt-oss-120b's 200K. So a tiny request that passes says nothing about room for a 2-4K-token judge call; estimate the wait as the tokens a run still needs divided by 139, in minutes from the stop.
- 2026-10-16: The calibration labels come from Claude in another chat, not a human (user decision).
  - Export: `make calibrate ARGS=export` writes `sample_for_labeling.jsonl` (ids s01-s30; question, sentence, cited passages with quotes; no verdict, no stratum).
  - Import: `make calibrate ARGS=import` reads `claude_labels.jsonl` (`{"id", "label": "y"|"n", "labeler", "why"}`, every id exactly once) and runs the judge. `result.json` records the labeler.
  - Wording: the eval card and the README say plainly that the judge was calibrated against labels by Claude, a different and stronger model than the judge, not by a human.
  - Before the export, constructed quotes became a seeded 12-word span instead of a passage's first 12 words, which a careful labeler could spot. The unlabeled sample was redrawn with the same 30 sentences.
- 2026-10-16: Judge calibration result (numbers and both disagreements in `evals/eval-card.md`): kappa 0.84 (95% CI 0.59 to 1.00) on 29 of 30 sentences, so citation precision and faithfulness count under the plan's rule (point estimate 0.7 or more).
  - Claude labeled all 21 natural sentences supported, the 5 that fail the validator included: their quotes failed, not their content. So every negative was constructed, natural-only kappa is 0 by construction, and how well the judge catches real unsupported sentences is untested.
  - The judge was stricter than Claude twice, both "partly": a comparison's conclusion (c06, "Therefore, Caterpillar's ... was higher" from two cited facts) and a sentence merging two passages (x01). The judge gives no reasons; if it marks comparison conclusions "partly" in general, comparison answers will pull faithfulness down on the test run.
  - A judge reply can name a source the sentence does not cite (s30: "judged sources [2], cited [1]"); `judge.parse` rejects it and the sentence goes unscored.
  - Added to the eval card (user request, 2026-10-16):
    - With s30 counted as a disagreement, kappa is 0.77 (95% CI 0.47 to 1.00), still 0.7 or more.
    - On s19 the judge's "partly" is defensible ("sourcing from" against "manufacture").
    - On s07 the judge's "partly" was first written up as strictness that may understate faithfulness. Revised the same day (user decision): under the written criterion the sources state both figures but not the comparison, so the judge's reading is the correct one and Claude's v1 label was lenient. v1's labels stay unchanged, because relabeling after seeing the judge would bias kappa.
    - A follow-up check is planned: about 10 natural sentences that fail the validator, from decision 4's runs, labeled by Claude, then judged.
- 2026-10-16: Judge calibration as planned (20 sentences that pass the validator, 10 that fail it) cannot be drawn from the dev run. Gemini's drafts almost always pass: 2 regenerations, a draft citation pass rate of 0.970, and 1 failing sentence in all. The judge also said yes on 59 of 62 passing sentences, so a 21-sentence sample would hold almost no negatives, and kappa would be unstable. The sample is not drawn; user decision pending on how to add negatives.
- 2026-10-16: `make label` and `make audit` append to `labels.jsonl`, which golden v1's manifest hashes, so both now refuse once the set is frozen. A new label would make every eval run exit 3.
- 2026-10-16: gitleaks' generic-api-key rule blocked the user's commit with about 1,600 findings: JSON fields named `key` that held hex cache digests (each call in the eval reports, and failing items in the calibration samples). No real secret was involved.
  - Fixed at the source (user decision, the way FreightAudit fixed it): `Call.cache_id` replaces `Call.key`, and calibration sample items carry `cache_id`.
  - The existing files were rewritten with the field name only, values unchanged and checked: 1,595 fields in 12 reports, 5 in calibration v1's `sample.jsonl` (its sha256 changed; todo.md) and 6 in the follow-up sample.
  - The gitignored reply cache (`.cache/evals/calls.jsonl`) keeps its internal `key` field.
  - Rule: never give a field that holds a high-entropy value (hash, digest, id) a name containing key, token, secret, auth or access. Fix findings at the source, never with `--no-verify` or an allowlist.
- 2026-10-16: `make eval ARGS=--refresh` would have stored its new replies under the same cache keys, and `Cache` loaded the latest reply per key.
  - Every later cache run would then have read the refreshed replies, so earlier reports would no longer reproduce from the cache.
  - `make calibrate ARGS=import` would have rebuilt v1's failing drafts from different text (`new_verdicts` reads them by key) and called the judge live.
  - Fixed before its first use (user approval): `--tag=NAME` replaces `--refresh` and joins the answer path (`answer_path`), so a live run gets its own keys, and the same NAME reuses them. `--primary-tag=NAME` gives only the primary new keys, so router replies come from the cache. `Cache` lost its `refresh` flag, so each key is written once.
- 2026-10-17: On the test split the router (gpt-oss-20b) sent 3 of 6 textual questions out of scope with no tickers. They were x13 (UnitedHealth's businesses), x14 (Pfizer's patent expiries) and x18 (the Grasberg mine). That is all 3 false refusals; dev's came from the model and validation. It also gave t10 (a time trap) and a03 (absent) no ticker, so they were refused as "nothing relevant enough" rather than by their own rules. Not fixed (user decision pending).
- 2026-10-17: Claude Haiku 5.5's adaptive thinking counts toward `max_tokens`, and the answer cap (`drafting.MAX_TOKENS`, 1,024) was sized for models that barely reason. On the pinned dev run (effort low) 4 answers hit the cap. Three regenerations (x03, x17, x19), whose prompt lists the draft's problems, spent all 1,024 tokens thinking and returned no text, so validation refused them. Fixed the same day (user decision): Claude's thinking is off, so the cap holds only text; the dev rerun had no truncated or empty reply.
- 2026-10-17: An XBRL fact's source heading can name the wrong fiscal period. `_fact_source` (answering.py) joins the plan's fiscal year with the period of the filing that reported the value (`fiscal {year} {fact.fiscal_period}`).
  - Under the latest-filed rule, a year-end balance often comes from the next year's 10-Q comparative. Goldman Sachs' total assets at 2025-12-31 (fact 460279) and Lockheed Martin's cash at 2025-12-31 (fact 557549) come from 2026 Q2 10-Qs, so their headings read "fiscal 2025 Q2".
  - Claude Haiku took that literally ("fiscal 2025 Q2 rather than the end of fiscal 2025") and answered INSUFFICIENT_EVIDENCE on n17 and n24. Gemini answered from the same heading.
  - Not fixed (user decision pending): label an instant fact by its date and the period asked for, not the reporting filing's period.
- 2026-10-17: The `anthropic` SDK 1.x runs on httpx2, not httpx. It takes no shared `httpx.AsyncClient`, respx cannot mock it (tests pass `httpx2.AsyncClient(transport=httpx2.MockTransport(...))`), and errors mid-stream surface as raw `httpx2` exceptions, which the provider maps to `UpstreamError`. A stream's mid-answer error event raises `APIStatusError` with status 200, so its `type` names the error.
- 2026-10-16: Gemini 3.5 Flash-Lite's own time to first token (free tier) moves with the hour.
  - On the same 46 dev questions, its p50 was 0.97 s at 05:56 UTC and 3.38 s at 09:00 UTC.
  - Prompts of about 330 tokens slowed as much as 5,000-token ones, and the 09:00 run drew two 503s. The router (Groq) moved only from 0.60 to 0.66 s.
  - So compare latency configurations within one sitting, in interleaved passes; decision 3 runs minimal, default, minimal.
- 2026-10-17: `uv run --env-file FILE` (uv 0.12.23) never overrides a variable already set in the environment: a set value beat the file's, and an empty value in the file did not blank a set one. So a process's environment, such as a CI job's secrets, wins over a copied `.env.example`.
- 2026-10-17: GNU make exits 2 whenever a recipe fails, whatever the command's own code, so `make eval` hides the harness's exit 1, 2, 3 or 4. The nightly therefore calls `python -m evals.harness` directly. The PR eval reads the verdict files, not exit codes.
- 2026-10-17: `trivy fs` over the whole repo through the Windows bind mount took 11 minutes, almost all of it the walk, even with `--skip-dirs`. One lockfile per run takes seconds, so `make vuln-scan` names each one. `--include-dev-deps` exists only for `fs`; `trivy image` refuses it.
- 2026-10-17: git inside the oasdiff and gitleaks images refuses a checkout owned by another user, as on a Linux runner. The Makefile passes `safe.directory=/repo` through `GIT_CONFIG_COUNT`/`KEY_0`/`VALUE_0`, which counts as command-line config. It is untested on GitHub until the test PR.
- 2026-10-17: A restore rebuilds the HNSW index. Two restores of `corpus-v1.dump` gave identical top 10s on all 70 dev questions. The dev database, whose index was built as chunks were embedded, differs on o03 and u02 (unanswerable, one chunk each); scored metrics are identical.
- 2026-10-17: `pg_dump --exclude-table-data` also drops a sequence's value when it names the sequence. Without that, the dump carried the private tables' id counters.
- 2026-10-17: Git Bash rewrites a `/tmp/...` argument to `docker compose exec` into a Windows path; set `MSYS_NO_PATHCONV=1`. Python's subprocess calls are not affected.
- 2026-10-18: `app.dependency_overrides` reach only code that FastAPI calls through `Depends`. A GraphQL resolver that called `answer_limits` directly would skip the tests' `UNLIMITED` override, so the resolver gets its limits from the `answer_limits_for` dependency of the context getter.
- 2026-10-18: typeshed's `AsyncGenerator.__aiter__` returns a plain `AsyncIterator`, so a protocol that an async generator must satisfy (`AnswerEvents`) declares `__aiter__` as returning `AsyncIterator`, with `__anext__` and `aclose` returning `Awaitable`.
- 2026-10-18: FastAPI's native telemetry records `url.query` with its values and redacts only cloud signatures (`fastapi/telemetry/_asgi.py`). The `QueryNames` span processor rewrites it to parameter names in `on_start`, and the `uvicorn.access` filter does the same for access lines, with the same helper.
- 2026-10-18: uvicorn's `Config.configure_logging()` sets the `uvicorn.access` logger to `propagate = False` (with no handlers) when a server starts with `access_log=False`, and a later server with the access log on does not undo it (uvicorn/config.py:427-429). The shared test servers start that way, so the access-log test passed alone and failed in the full unit run. What we did: the test sets `propagate` back with monkeypatch, as a fresh API process has it. Production is not affected: `python -m filinglens_api` runs one server with the access log on.
- 2026-10-18: Celery's prefork children leave through `os._exit`, which skips the SDK's flush at exit, so `worker_process_shutdown` shuts the providers down. The solo pool (tests) sends `worker_process_init` but no shutdown signal; its process exits normally.
- 2026-10-18: Jaeger 2.21's built-in config binds every endpoint to `${env:JAEGER_LISTEN_HOST:-localhost}`, and the image sets `JAEGER_LISTEN_HOST=0.0.0.0`; its in-memory backend is `some_storage` (max 100,000 traces), changed with `--set`. It serves only the v3 query API (`/api/v3/traces` with `query.service_name`, `query.attributes` as JSON, and both `query.start_time_*`); `/api/traces` and `/api/services` answer 404 (live check).
- 2026-10-18: `evals/corpus.py` (`make corpus-restore` and `corpus-dump`) runs `docker compose` without `-p`, so it always reaches the dev project `filinglens`. For a throwaway project, the live check ran the same `cp` and `pg_restore` arguments with `-p filinglens-demo` by hand.
- 2026-10-18: A counter with no zero series hides a process's first events: its first export already holds them, and `increase()` sees no rise. The live check showed it for `filinglens_sec_requests_total`, whose status panel stayed empty; `start_ingest_series` now creates each SEC kind at status 200 too.
- 2026-10-18: `export MSYS_NO_PATHCONV=1` (for Docker paths in Git Bash) also stops the conversion of `/h/...` for other programs, so Python was handed `H:\h\...`; with it set, pass `H:/...` paths.
- 2026-10-18: A client polling uvicorn every 5 s can reuse a keep-alive connection just as uvicorn's 5 s idle timeout closes it: httpx raises "Server disconnected without sending a response" with no fault on the server. Poll with a fresh connection, or more often than the timeout.
- 2026-10-18: A pydantic validator is a class method, so a subclass method with the same name replaces the parent's validator, even when the two validate different fields. `ApiSettings._empty_is_off` (`LLM_ANSWER_FALLBACK`) replaced `TelemetrySettings._empty_is_off` (`OTEL_EXPORTER_OTLP_ENDPOINT`), so `ApiSettings` and `EvalSettings` read an empty endpoint as an invalid URL and exited at startup.
  - It showed first in CI on the step 8 pull request: CI's `.env` is a copy of `.env.example`, which sets the variable empty. The local `.env` has no such line, and an absent variable takes the default without the validator. Compose also passes it empty when telemetry is off (not observed in a container).
  - What we did: renamed them `_empty_endpoint_is_off` and `_empty_fallback_is_off`, then added a test that loads `ApiSettings` and `IngestSettings` with both variables empty. It was written first and failed for `ApiSettings` before the rename. Best option: the user's choice, and the smallest change that restores the inherited rule.
  - Rule: a validator's name must be unique across the whole settings hierarchy, `EvalSettings` in `evals/harness.py` included. `Cls.__pydantic_decorators__.field_validators` shows which fields each name validates.
- 2026-10-18: Two parsers read an answer's markers. `validate.MARKER` reads source ids only (`[C2]`, `[F1]`); `judge.CITE` and `metrics.NUMBERED` read any `[n]` in the final text. Whatever the first lets through and the second reads breaks the judge: a JudgeError, or a verdict made up for a source the judge never saw.
  - Seen so far: Gemini dropped the "C" of C12 twice (the textual fixture, 2026-10-15; nightly x18, 2026-10-18) and wrote `[D1]` once (x11, dev, 2026-10-16).
  - What we did: the `STRAY` check above. A new check on markers needs both a row it flags and a row it leaves alone.
- 2026-10-18: A recorded fixture can hold a bug as its expected output. `services/api/tests/fixtures/answers/textual.json` recorded an answer that shows a dangling `[12]`, and its tests passed. The file stays as recorded. Tests that need a draft that holds use `textual_exchanges()` (`[C12]` where Gemini wrote `[12]`), and `test_a_marker_naming_no_source_is_sent_back_and_never_shown` replays it verbatim.
- 2026-10-18: A nightly rerun replays; it does not resample. This comes from the code and the workflow; it has not been observed yet.
  - A completed run deletes its run file. The reply cache, judge replies included, is saved and restored (`restore-keys: eval-calls-`), so a rerun without a code or prompt change repeats the same replies and verdicts.
  - A changed validation outcome changes the regeneration prompt, so only that call goes live.
  - Model variation found in one run stays in the cache until a key changes, such as c15's refusal in run 39068994474.
- 2026-10-18: A nightly job log shows no reply text: evals log at WARNING, and "answer failed validation, regenerating" is info level. A question's failing sentences are only in the run's Actions cache, which cannot be downloaded, and in the report JSON of the artifact.

- 2026-10-18: FastAPI 0.143 keeps an included router as an `_IncludedRouter` entry in `app.routes` (lazy inclusion), so the included routes do not show in `app.routes`.
  - What happened: PR A's first route-table test found no `/graphql` route at all.
  - What we did: the test reads the router object we filter (`main.graphql_router.routes`) instead of FastAPI's internals. The 405 test covers the routing behaviour.
- 2026-10-18: Git Bash rewrites any argument that starts with `/` into a Windows path, a regex included. During B1's red checks, `/^\d+$/.test(retryAfter)` reached Python as `C:/Program Files/Git/^/d+$/.test(retryAfter)`, so that mutation was not applied. Set `MSYS_NO_PATHCONV=1`, and then pass `H:/...` paths (see above). Git Bash here also has no `python` on PATH: the Microsoft Store alias answers "Python was not found". Run scratch scripts with `uv run --no-project python -I`.
- 2026-10-18: `test_twenty_workers_never_exceed_eight_sec_requests_a_second` failed once with its tightest 9-request span at 0.925 s against its 0.95 s floor. That `make test-int` overlapped lint, pyright, the unit suite, `npm ci` and two Docker tool runs. Alone it passed, and so did the whole suite rerun with nothing beside it. Likely cause, not confirmed: CPU contention delays a client between its Redis grant and its request, which squeezes the arrival gaps at the fake SEC server. Run `make test-int` with nothing heavy beside it.
- 2026-10-18: Correction to the entry above: CPU contention is not the whole story. On the final B1 tree, `test_twenty_workers_never_exceed_eight_sec_requests_a_second` failed again in a `make test-int` with nothing else of ours running (0.940 s against 0.95 s). Run alone five times, it passed four and failed one (0.940 s).
  - B1 cannot affect it: the test and every module its 20 processes load are identical to main.
  - The cause of the extra jitter today is not confirmed. Other sessions on this PC are one guess.
  - The knob is `JITTER_S = 0.05` (`test_pipeline.py:80`). Today's misses were 60 and 75 ms. Widening it is the user's call, as a separate fix.
- 2026-10-18: `node --test` reports a test that reaches its `timeout` option as cancelled, not failed, though the run exits 1. So a red check on node tests reads the exit code or the cancelled count, not only the fail count. Seen when B1's signal mutations left a stubbed fetch hanging.
- 2026-10-19: Next 16 pitfalls met in B2:
  - A route handler's `request.url` and `nextUrl` use localhost, whatever host the browser asked for (decision above). Redirect with a relative `Location`, and compare origins with the `Host` header.
  - `instrumentation.ts` is compiled for the Edge runtime too, so a `process.exit` in it warns at build time. The check lives in `lib/startup.ts`, imported only when `NEXT_RUNTIME === "nodejs"`.
  - `not-found.tsx` and `error.tsx` take no `metadata` export (only the experimental `global-not-found` does), so they set their title with React 19's `<title>` element. `error.tsx` receives `retry`, not `reset`, in Next 16.
  - `next build` type-checks every `.ts` file the tsconfig includes, `e2e/` and `playwright.config.ts` too.
- 2026-10-19: web's `postinstall` runs `npm --prefix ../clients/ts ci --omit=dev`, which removes `clients/ts`'s dev dependencies (typescript, the codegen tools). After `npm ci` in web, `npm --prefix clients/ts run typecheck` fails until `make codegen` (its own `npm ci`) or `npm --prefix clients/ts ci` reinstalls them. CI runs them in separate jobs, so it never meets this.
- 2026-10-19: Playwright's `response.headers()` leaves out security-related headers, `Clear-Site-Data` among them; `response.allHeaders()` has them. The sign-out spec first failed on this.
- 2026-10-19: `page.addInitScript` with a `securitypolicyviolation` listener and `page.exposeFunction` catches CSP reports; Chrome reports a blocked redirect under the URL before the redirect (`form-action http://127.0.0.1:3102/logout` when `/logout` redirected off-origin).
- 2026-10-20: `make corpus-restore` and `make migrate` always target the dev stack. Both pass `.env`, and `evals/corpus.py` runs `docker compose` without `-p`. Production restores by exact container name (todo.md, step 10).
- 2026-10-20: Compose reads every `${VAR:?}` in its files before it applies profiles. So `.env.prod` needs `GRAFANA_ADMIN_PASSWORD` and `SEC_USER_AGENT` even with monitoring and the workers off.
- 2026-10-20: Tailscale is not installed on this PC. FreightAudit's Funnel runs in its prod stack's own tailscale container.

## Rejected Approaches

None yet.

## Lessons Learned

None yet.

## Constraints

- 2026-10-16: FreightAudit and FilingLens share one Groq account, so they share each model's daily tokens: about 200K for gpt-oss-120b, refilling continuously at about 8.3K an hour (user rule).
  - About 25K a day of gpt-oss-120b stays reserved for FreightAudit's CI, so FilingLens spends at most 175K of it in any 24 hours.
  - FreightAudit uses gpt-oss-120b and qwen3.8-27b, not gpt-oss-20b, and Groq's limits are per model, so FilingLens's router model (gpt-oss-20b) has its own 200K a day.
  - Before an eval run that spends quota, show its Groq tokens per model and whether it needs the judge. Run the judge only where the decision depends on it, and spread runs over days when needed.
  - Groq shows no daily token level (see Known Issues), so schedules come from refill arithmetic.
  - CI (2026-10-17):
    - A live PR answer eval uses about 28K gpt-oss-20b, out of that model's 200K a day, which FreightAudit does not use.
    - The nightly's judge uses 18-28K gpt-oss-120b, from the allowance shared with FreightAudit's CI and its 25K reserve.
    - A PR eval with unchanged prompts that hits the cache uses none.
- 2026-10-16: Gemini's daily quota resets at midnight Pacific, which is 15:00 Taipei (07:00 UTC) during daylight time (user). Runs that need a fresh Gemini allowance start after that; the test day starts at 15:07 Taipei.
- 2026-10-21: FilingLens's Gemini key belongs to Triage Copilot's Google project and shares its quota (user). Production AI waits for a key from FilingLens's own project, billing off (todo.md, step 10, B28).

## Unresolved Questions

- 2026-10-13: Corpus size estimate (200k to 300k chunks for S&P 500 10-Ks) is unmeasured. Measure on a 20-filing sample first. Measured on 2026-10-15 on the 30 golden-set 10-Ks: mean 375 chunks per 10-K (median 314), so about 190k chunks for one 10-K per S&P 500 company. 10-Qs are still unmeasured.
- 2026-10-14: Free-tier rate limits will slow full eval runs. Check each provider's console before a big run. Dollar cost targets apply only on a paid tier.
- 2026-10-25: Funnel's speed behind the egress proxy. With no UDP route out, every Funnel connection rides one Tailscale relay through squid. FreightAudit's public requests after its proxy: 3 of 10 within 2.5 s, 2 of 10 never connected in 30 s, TLS up to 5.0 s (its own docs, 2026-10-21). Whether FilingLens's node has direct UDP paths today is unknown. The rollout measures ten requests before and after (deploy.md, step 30) and rolls back if one passes the web's 5 s page timeout.
