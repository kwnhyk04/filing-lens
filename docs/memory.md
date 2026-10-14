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

## Rejected Approaches

None yet.

## Lessons Learned

None yet.

## Constraints

None yet.

## Unresolved Questions

- 2026-10-13: SEC fair-access policy (10 req/s, declared User-Agent) is from training data. Verify on sec.gov before building ingestion.
- 2026-10-13: Corpus size estimate (200k to 300k chunks for S&P 500 10-Ks) is unmeasured. Measure on a 20-filing sample first.
- 2026-10-14: Free-tier rate limits will slow full eval runs. Check each provider's console before a big run. Dollar cost targets apply only on a paid tier.
