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
- 2026-10-18: UI accessibility is checked by axe on every page plus keyboard-only and phone-width specs (user). Reason: axe misses focus order and keyboard-only flows.
- 2026-10-18: Container go for step 9 (user), also during Triage Copilot's exam window, since neither use makes a model call:
  - Uses: Testcontainers for `make test-int`, and FilingLens's own dev Postgres (`filinglens-postgres-1`) for `make demo-export`.
  - Conditions: check ports first; start and stop only FilingLens's own containers, by exact name; never touch FreightAudit's or Triage Copilot's containers or volumes; never stop Docker.
  - Model calls stay off. Any other container needs a new go.

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

## Unresolved Questions

- 2026-10-13: Corpus size estimate (200k to 300k chunks for S&P 500 10-Ks) is unmeasured. Measure on a 20-filing sample first. Measured on 2026-10-15 on the 30 golden-set 10-Ks: mean 375 chunks per 10-K (median 314), so about 190k chunks for one 10-K per S&P 500 company. 10-Qs are still unmeasured.
- 2026-10-14: Free-tier rate limits will slow full eval runs. Check each provider's console before a big run. Dollar cost targets apply only on a paid tier.
