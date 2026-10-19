# FilingLens

Answers analyst questions over SEC 10-K and 10-Q filings with sentence-level citations, and checks every number against SEC XBRL data.

## Setup

Needs uv, Docker, GNU make, and Node 24.7+ (`web/` signs in with `node:crypto`'s argon2, new in 24.7; the web's and the TypeScript client's tests rely on Node's type stripping; CI uses Node 24).

1. `cp .env.example .env`, then change every password and both API keys (`API_KEY`, `ADMIN_API_KEY`), and set `SEC_USER_AGENT` to your tool name and contact email (SEC requires one; compose refuses to start without it).
2. `uv sync` installs the Python workspace (Python 3.12).
3. `uv run python -m pre_commit install` turns on the gitleaks pre-commit hook.
4. `make models` once: it fetches the pinned embedders and rerankers into `HF_HOME` (set it to a folder on the data disk first; here `H:\.cache\huggingface`). Tests and containers load them offline from there.
5. `make dev` builds the images and starts Postgres, Redis, RabbitMQ, the API, the ingest worker and the embed worker. It returns once all are healthy.
6. `make migrate REV=0008`, then `make seed`. Dev stays at revision 0008, the last one before the embedding swap (model A), until the live swap; see `docs/migrations.md`.
7. Optional, live SEC: `make seed-real` ingests the latest 10-K of the 30 golden-set companies (`evals/golden-companies.csv`) through the workers, embeds and indexes them, with their XBRL facts.
8. Optional, answers: set `GEMINI_API_KEY`, `GROQ_API_KEY` and `NVIDIA_API_KEY` in `.env` and `AI_ENABLED=true` (off by default; with it on, startup refuses a missing key).
9. Optional, a paid answer fallback: set `ANTHROPIC_API_KEY` and `LLM_ANSWER_FALLBACK=anthropic:claude-haiku-5-5`. Answers then try Claude Haiku 5.5 after Gemini and before NVIDIA, on prepaid credits, until the credits are gone or `ANTHROPIC_CREDITS_EXPIRE` (default 2026-11-10) arrives. Left empty, the chain stays free-only.
10. Web, in your own terminal:
    - `npm --prefix web ci` (it also installs the TypeScript client's runtime dependencies).
    - `npm --prefix web run hash-password` asks for the sign-in password twice without echo (at least 12 characters) and prints a `LOGIN_PASSWORD_HASH='...'` line: paste it into `.env` as printed, single quotes included, so compose and uv leave its `$` alone.
    - `npm --prefix web run session-secret` appends `SESSION_SECRET` (32 random bytes, hex) to `.env` and prints nothing. It refuses when the line exists. To rotate it, delete the line and run it again; a new value signs everyone out.
    - Add `API_URL=http://127.0.0.1:4100`. The web reads only `API_URL`, `API_KEY`, `SESSION_SECRET`, `LOGIN_PASSWORD_HASH` and `WEB_PORT` from `.env`, never `ADMIN_API_KEY`.

## Usage

| Target | What it does |
| --- | --- |
| `make dev` / `make down` | Start the stack and wait until it is healthy / stop it (volumes are kept) |
| `make test` / `make test-int` | Unit tests (no Docker, no network; about 10 s) / integration tests in throwaway Postgres, RabbitMQ and Redis containers (needs Docker; about 2 minutes). Tests never reach SEC or a model provider: `network_guard.py` refuses every host but this machine |
| `make lint` / `make typecheck` | ruff / pyright (strict for `packages/*`) |
| `make migrate` / `make seed` | Apply Alembic migrations up to `REV` (default head; dev uses `REV=0008`) / upsert seed data |
| `make seed-real` | Live SEC, needs `make dev`: check the golden-set CIKs and tickers against SEC, then ingest each company's latest 10-K and its XBRL facts through the worker; prints filings per status, chunks per filing, facts per company and the SEC requests made. Do not run it, or queue ingest jobs, while golden set v1's test runs go on: new filings (Apple's FY2026 10-K lands around 2026-10-30) change the corpus, and the eval's drift check then stops every run |
| `make models` | Once, outside tests: fetch the pinned local models into `HF_HOME` |
| `make smoke` | Live models: three questions (numeric, textual, unanswerable) through the answer pipeline; prints answers, citations, tokens, stage latencies and time to first token |
| `make record-fixtures` | Live models: re-record the replies the answering tests replay (`services/api/tests/fixtures/answers`) |
| `make check-parallel-hnsw` | Dev stack: build a throwaway HNSW index with parallel workers, to confirm postgres's shared memory (`shm_size`) fits it |
| `make seed-fake` | Load and pagination tests only: 200 fake companies, 2,000 filings, 100k chunks with random vectors (about 2.5 minutes at the dev revision; a rerun adds nothing). Locks `chunks` while it loads |
| `make codegen` | Export `contracts/` from the app, then regenerate `clients/python`, `clients/python-graphql` and `clients/ts` |
| `make contracts-check` | Run codegen and fail if `contracts/` or `clients/` changed (commit or stage the output first) |
| `make contracts-breaking` | oasdiff (Docker): fail on breaking OpenAPI changes against `BASE` (default `main`) |
| `make eval` | Golden-set eval, needs `make dev`: `SUITE=retrieval\|answer\|all SPLIT=dev\|test SUBSET=full\|ci`. `ARGS` takes `--tag=NAME` (calls the answer models live once under NAME; earlier replies stay cached), `--primary-tag=NAME` (the same for the answer model only, with router replies from the cache), `--router-primary=PROVIDER:MODEL` (reuse the router replies of that answer model's run, so two answer models get identical inputs), `--min-relevance=X`, `--thinking=default`, `--no-judge` and `--ci` (CI runs: see CI below). Runs check the floors in `evals/thresholds.json` but never write them; `uv run python -m evals.harness --set-floors REPORT` writes the floors the rule gives a saved report's measured values, latency included, keeping only tighter ones; add `--replace` to replace that report's floors even when looser (only on request, with a reason). Pass/fail metrics use Wilson intervals. The answer suite calls the live models and prints a quota estimate first. Replies are cached, so a run stopped by a quota or rate limit (exit 2, the only stop that says to rerun after the quota resets) resumes when rerun. Reports go to `evals/reports/`. Exits 1 on a broken floor, 3 when the golden set or the corpus changed since the freeze, and 4 on any other failure with its reason (a refused key, credits gone, a retired model). The harness's own exit code shows when it runs directly; through make every failure is make's exit 2 |
| `make corpus-dump` / `make corpus-restore` | Dev stack: golden v1's corpus for CI as `.cache/corpus/corpus-v1.dump`, with rows of the public SEC tables only, checked for secrets / an empty Postgres (CI): fetch the `corpus-v1` release asset if missing, check its sha256 and restore it (`evals/corpus.py`) |
| `make demo-export` | Dev Postgres: write `web/demo/snapshot.json` for the public demo, from 8 recorded answers of the golden v1 test run (no model call) plus their sources and the coverage, read through the API's own GraphQL. It stops on a citation it cannot resolve or one inside the four mislabeled sections (Known limitations). Rebuild the web after it |
| `make actionlint` / `make secrets-scan` | Lint the GitHub Actions workflows / gitleaks over every commit (run it before a push) |
| `make vuln-scan` / `make image-scan` | Trivy on each lockfile, dev dependencies included, failing on a high or critical with a fix / on an image (`IMAGE`, default `filinglens-api`), failing on a critical with a fix |
| `make audit` / `make label` | Interactive passage labeling for the golden set (resumable). Both refuse once the set is frozen |
| `make calibrate` | Judge calibration. On screen you label sampled answer sentences against their cited sources. `ARGS=export` writes the sample for an outside labeler, and `ARGS=import` scores its labels from `claude_labels.jsonl`. The judge then scores the same sentences, Cohen's kappa goes to `evals/calibration/v1/result.json` with the labeler named, and judge metrics count only at 0.7 or more. A first argument `followup` (`ARGS="followup export"`) works on the second sample in `evals/calibration/v1-followup/`: natural sentences that fail the validator, from the fallback-model runs |

- API: `http://127.0.0.1:4100`. `/healthz` and `/readyz` need no key; everything else needs `X-API-Key`. `API_KEY` opens `/v1/companies`, `/v1/filings`, `/v1/search`, `/v1/answers` (plus `/stream` for Server-Sent Events) and `/graphql`; the admin routes `/v1/ingest-jobs` take only `ADMIN_API_KEY`. The contract is `contracts/openapi.json` (errors are RFC 9457 problems) and `contracts/schema.graphql`. Companies, filings and the GraphQL sections, chunks and facts come from Postgres; GraphQL `chunks(ids)` and `facts(ids)` look up an answer's citations (up to 20 ids) with their section, filing and company. An ingest job discovers each company's 10-K and 10-Q filings on EDGAR, fetches them into the SEC cache (`.cache/sec`, shared by the worker and host runs), splits them into item sections and token-aware chunks, embeds the chunks on the `embed` worker, and loads the company's XBRL facts. Search and answers run on that data (answers need `AI_ENABLED=true`).
- Limits: each key gets 60 requests a minute, and 10 answers a minute across REST, the stream and GraphQL (429 with `Retry-After` and `RateLimit-*`; a `rate_limited` error over GraphQL). Bodies are capped at 64 KB (413) and answers at 30 s (502), over GraphQL too. GraphQL refuses a query nested deeper than 6 levels or with an alias, before running it. Answers return 503 `ai_unavailable` once the day's LLM tokens (UTC) reach `DAILY_AI_TOKEN_BUDGET`, or when `AI_ENABLED=false` (the default), and 503 `overloaded` past `LLM_MAX_INFLIGHT` answers in progress.
- Model chain: an answer goes to `LLM_PRIMARY` (Gemini), then `LLM_ANSWER_FALLBACK` if set (Claude Haiku 5.5), then `LLM_FALLBACK` (NVIDIA); the router falls back to `LLM_FALLBACK` only. Claude is skipped for the rest of the credit period once its credits are gone (a 402, a 400 naming a spend limit, or a 429 without `Retry-After`; the log says `claude is off for the rest of the credit period`) and from `ANTHROPIC_CREDITS_EXPIRE`. A 429 asking for 10 s or less is retried once. `usage.cost_usd` in an answer is the credits it spent.
- Dead letters: a task that keeps failing ends in its dead-letter queue (`discover.dlq`, `fetch.dlq`, `parse.dlq`, `chunk.dlq`, `embed.dlq` or `facts.dlq`) and the `dead_letters` table; a filing parse cannot split fails with the reason in its job item. `docker compose exec ingest python -m filinglens_ingest.replay --queue fetch.dlq --limit 100` moves such messages back to their queue with fresh retries. If SEC still answers 403 after a cool-off, every SEC request stops and the job's filings fail with that reason: fix `SEC_USER_AGENT`, restart the worker (`docker compose up -d ingest`), then replay. Without Redis, workers pause instead of sending unlimited requests.
- Schema changes and the embedding model swap runbook: `docs/migrations.md`.
- Clients: `clients/python` (REST) and `clients/python-graphql` (GraphQL) are installed in the dev environment; `clients/ts` exports `createApiClient`, `executeGraphql`, `ApiError` and `readApiError` for server-side TypeScript (`npm --prefix clients/ts test` runs its tests).
- Web: `npm --prefix web run dev` (or `run build`, then `start`), then open `http://127.0.0.1:3100` and sign in. Ask streams a draft, then shows the checked answer with a card per citation: the passage with its quote marked, or the XBRL fact. Coverage lists the companies and their filings. `/demo` needs no sign-in: the saved answers and coverage from `web/demo/snapshot.json`. A live page whose API call fails (the PC is off, say) lands on its demo twin with a banner, and a rejected `API_KEY` shows a configuration error instead. The browser talks only to the web; its server routes call the API with `API_KEY`. Tests: `npm --prefix web test` (units, `node --test`), then after a build `npx playwright test` in `web/` (Chromium against a mock API that replays the snapshot: sign-in, Ask, offline, a rejected key, headers, axe, keyboard and a 390 px phone). Its browser comes from `npx playwright install --only-shell chromium`, once, with `PLAYWRIGHT_BROWSERS_PATH` set to a folder on the data disk first (here `H:\.cache\ms-playwright`). The visual design is described in `docs/design.md`; after a build, `npm --prefix web run screens` writes every screen in light, dark and phone width to `docs/screenshots/ui/`, each checked by axe first.
- Plain `docker compose ...` (for example `docker compose ps`) works from the repo root, because `.env` sets `COMPOSE_FILE`.
- Monitoring: set `COMPOSE_PROFILES=observability` and `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:${OTEL_HTTP_PORT}` in `.env` for traces in Jaeger (16687), metrics and 13 alert rules in Prometheus (9091), and three dashboards in Grafana (3101). Leave both empty and telemetry is off. What each dashboard and alert is for, and how to find a trace: `docs/monitoring.md`. `make monitoring-check` tests the alert rules. Toxiproxy runs under the `test` profile.
- Production: `docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d` (no published Postgres, RabbitMQ or Redis ports; restart policies; memory limits).
- Logs are JSON lines with a `request_id` (send `X-Request-ID` to set it) and, inside a trace, its `trace_id`. Credential fields and the API key are redacted, and access lines keep query parameter names only.
- Ports bind to 127.0.0.1 and can be changed in `.env`.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on pull requests, pushes to main and manual runs; the required check is `ci-ok`, which fails when any job failed or was cancelled.

- Jobs: lint (ruff, pyright, actionlint, and guards against an Anthropic secret or model and against steps that cannot fail), unit and integration tests, contracts (`make contracts-check`, the `clients/ts` tests, `make contracts-breaking` against the base), web (types, unit tests, build, Playwright; no secrets), security (gitleaks over the full history, Trivy on the lockfiles), migrations, eval, images (build api and ingest, Trivy), and on main only, publish to GHCR (`sha-<short>` and `latest`, with provenance) after migrations and every check.
- Pinning: actions are pinned to commits and tools to image digests, each release at least 7 days old. Trivy runs from 0.75.0 by digest with no token, no secret and no Docker socket; its GitHub Actions and the hijacked releases (binary 0.69.4, images 0.69.5 and 0.69.6) are never used.
- Secrets: Actions secrets `GEMINI_API_KEY` and `GROQ_API_KEY` only, read by the answer eval step alone. CI never calls Claude: there is no Anthropic secret, and `LLM_ANSWER_FALLBACK` is empty.
- Eval: it runs only when an eval input changed (`packages/{core,db,llm,retrieval,telemetry}/src`, `services/api/src`, `evals` without its reports, tests and Markdown, or `uv.lock`). It restores the frozen corpus from the `corpus-v1` release asset.
  - The retrieval suite runs on all 70 dev questions, with local models and no LLM call.
  - The answer suite runs on the 20-question dev ci subset without the judge.
  - The verdicts go to the PR comment and the job summary, and the reports to an artifact.
- `--ci` verdicts: the answer and retrieval verdicts head the PR comment.
  - PASS: the gated floors hold.
  - FAILED: the real reason, such as a broken floor, an errored question or a refused key.
  - INCOMPLETE: only for a quota or rate limit stop, which says to rerun after the quota resets.
  - NOT RUN: a Dependabot or fork PR gets no secrets, so no answer is measured. It is shown at the top, never as a pass, and the nightly eval measures main after the merge.
  - Latency is reported, marked "not gated": runners are not the production PC.
- Nightly (`nightly-eval.yml`, 19:17 UTC): the test split with the judge, only when the eval inputs changed since the last complete nightly run. It uploads the report and opens an issue when a floor breaks.
- Tokens per run, uncached (cached replies cost nothing):
  - PR answer eval (25 questions, 10 of them should-refuse): about 28K gpt-oss-20b, 0 gpt-oss-120b and about 20 Gemini requests (measured 2026-10-17). The Groq account is shared with FreightAudit's CI. Its daily allowance is per model, about 200K tokens each. FreightAudit keeps about 25K a day of gpt-oss-120b, which only the nightly's judge uses here.
  - CI floors are a tripwire for large drops, not a precise measure: with 8 numeric questions, the floor of 0.676 still lets 6 of 8 pass. The nightly run and the exam give the precise numbers.
  - Nightly: about 33K gpt-oss-20b, 18-28K gpt-oss-120b (the judge, shared with FreightAudit's Groq account) and about 25 Gemini requests.

## Evaluation

Golden set v1 (`evals/golden/v1`, frozen 2026-10-16) holds 100 questions over the 30 companies' latest 10-Ks. How it was built and labeled is in `evals/eval-card.md`.

- Textual gold is AI-labeled, spot-checked by a non-expert. Claude labeled every pooled passage.
- The human check was a fast spot-check by a non-expert, which cannot validate the labels on its own. The passage labels are not human-verified.
- Blind agreement on 79 passages was 49.4%, Cohen's kappa 0.10 (95% CI -0.07 to 0.26), which is not distinguishable from chance.
- The human then made the final call on the 40 disagreements and kept Claude's label on 37. That review showed Claude's reason, so it was not independent.
- Later, after reading the passage text, the human corrected 2 of their 3 overrides back to not gold. The final key now differs from Claude's labels on one passage.
- The judge behind citation precision and faithfulness (gpt-oss-120b) is calibrated against labels by Claude, a different and stronger model than the judge, not by a human. On 29 sentences it agreed 93.1%, Cohen's kappa 0.84 (95% CI 0.59 to 1.00), so those metrics count. Every negative in that sample was constructed. A follow-up spot check on natural sentences that fail the validator (2026-10-17) found the judge failing 3 of the 4 that Claude labeled not supported.
- While golden v1 is in use, don't run `make seed-real` or queue ingest jobs (see `make seed-real` above).

### Official results: test split, 2026-10-17

The run covers 30 questions on the free tiers. Gemini 3.5 Flash-Lite answers, gpt-oss-20b routes and gpt-oss-120b judges (report `evals/reports/2026-10-17.md`). The test floors in `evals/thresholds.json` come from this run. The dev floors that CI gates come from the dev reports of 2026-10-17. Retrieval accuracy floors sit one question's share below the measured value, because retrieval calls no model and repeats exactly (`evals/eval-card.md`).

The Haiku column is a comparison with Claude Haiku 5.5 pinned as the answer model: thinking off, judge on, nothing tuned (`evals/reports/runs/20261017T084716Z-answer-test-full.md`).
- It reuses the exact router replies of Gemini's run (`--router-primary=gemini:gemini-3.5-flash-lite --primary-tag=fair`), so both models answer identical inputs.
- It replaces an earlier Haiku run (`20261017T082950Z`) that asked the router again. The router then routed x13, x14 and x18 as textual, so that run's refusal figures differed by the router, not the answer model.
- With every router reply reused, no question had all its calls live. So Haiku's end-to-end latency is not measured, and its latency cells compare the answer models' own calls, paired by question.

| Metric | Target | Gemini (official), 95% CI | n | Status | Haiku (comparison), 95% CI |
| --- | --- | --- | --- | --- | --- |
| Retrieval recall@10 | 0.90 | 0.583 (0.314 to 0.816) | 6 | fail | same retrieval |
| MRR@10 | 0.70 | 0.833 (0.500 to 1.000) | 6 | pass | same retrieval |
| Retrieval latency p95 | 250 ms at about 250k chunks | 336 ms (275 to 364) at 11,263 chunks | 30 | not measured | same retrieval |
| Numeric exact match | 0.92 | 1.000 (1.000 to 1.000) | 12 | pass | 1.000 (1.000 to 1.000) |
| Citation precision | 0.95 | 0.944 (0.833 to 1.000) | 20 | fail | 0.958 (0.880 to 1.000) |
| Citation coverage | 0.95 | 0.971 (0.914 to 1.000) | 20 | pass | 1.000 (1.000 to 1.000) |
| Faithfulness | 0.92 | 0.970 (0.906 to 1.000) | 20 | pass | 0.944 (0.857 to 1.000) |
| Correct refusal | 0.90 | 1.000 (1.000 to 1.000) | 7 | pass | 1.000 (1.000 to 1.000) |
| False refusal | 5% or lower | 13.0% (0.0 to 26.1%) | 23 | fail | 13.0% (0.0 to 26.1%), the same 3 router calls |
| Time to first token p50 | 1.0 s | 1.55 s (1.45 to 1.62) | 19 | fail | not measured end to end; own first token 0.72 s against Gemini's 0.85 s, paired (difference −0.13 s, CI −0.18 to −0.07), n 22 |
| Time to first token p95 | 2.0 s | 1.84 s (1.67 to 1.84) | 19 | pass | not measured end to end; own first token 0.94 s against 1.13 s |
| Full answer latency p95 | 6 s | 2.15 s (1.97 to 4.89) | 21 | pass | not measured end to end; own reply 2.36 s against 2.10 s |
| Tokens per query, in / out | 8,000 / 600 | 3,188 (2,196 to 4,236) / 161 (119 to 221) | 30 | pass | 4,853 / 278 |
| Cost per query, paid-equivalent | $0.015 | $0.0010 ($0.0006 to $0.0014) | 30 | pass | $0.0006 ($0.0004 to $0.0009) |
| Cost per query, as billed | $0.015 | $0 | 30 | pass | $0.0005 in credits ($0.0003 to $0.0008) |
| Ingestion | 500 filings in under 2 hours | - | - | not measured | - |

Every miss, explained:

- **False refusal 13.0%:**
  - All three are the router (gpt-oss-20b) sending a textual question out of scope with no ticker: x13 (UnitedHealth's businesses), x14 (Pfizer's patent expiries) and x18 (the Grasberg mine in September 2025).
  - Retrieval ranked their gold first, so a correct route would likely have answered.
  - Asked again in the first Haiku run, the same router routed all three as textual, so it is not deterministic. That is why the Haiku comparison was rerun on Gemini's router replies.
- **Citation precision 0.944:** one sentence, 34 of 36 pairs pass.
  - c02 concludes "Therefore, Alphabet's total revenue was higher in fiscal 2025 [1][2]" from two cited facts.
  - The sources state both figures but not the comparison, so the judge rates it "partly" under the written criterion, as in calibration.
- **Recall@10 0.583:** it rests on 6 textual questions, so one question moves it by about 0.17, and the interval runs from 0.31 to 0.82.
  - x12 (Lilly's growth drivers) found none of its 3 gold passages in the top 10.
  - The passage gold is AI-labeled, spot-checked by a non-expert.
- **Time to first token p50 1.55 s:**
  - The stages run in sequence: the router (p50 0.62 s), then facts or retrieval, then Gemini's first token.
  - Gemini's own first token drifts with the hour on the free tier: on the same dev questions on 2026-10-16, p50 0.97 s at 05:56 UTC and 3.37 s at 09:00 UTC. This run's p95 pass reflects a fast hour.
  - Starting the search while the router runs saves a median 268 ms where the router agrees (dev).
  - On the same routes, Haiku's own first token was 0.13 s faster at p50 (95% CI 0.07 to 0.18 s). The answer model is a small part of the miss.
- **Not measured:** retrieval latency at the 250k-chunk scale, and ingestion of 500 filings.

Known weaknesses, with v2 ideas (nothing here is tuned on test results):

- **Router out-of-scope calls:** in code, a question that names a tracked company (`router.guess`) is never out of scope; or the router prompt gets in-scope examples. Measure either on a new dev set.
- **Router missing tickers:** t10 (a time trap) and a03 (an absent figure) were refused as "nothing relevant enough", because the router gave no ticker. Fill a single named company from `router.guess` when the router gives none.
- **Comparison conclusions:** check "higher" or "lower" against the cited fact values in code, like the derived-number check in `docs/todo.md`, so a correct conclusion can count as supported. Haiku's c12 conclusion ("decreased") got the same "partly".
- **Recall:** a v2 golden set with 20 or more textual test questions and human-verified passage labels. On dev, the MiniLM-L-6 reranker showed headroom at about 14 times the rerank time.
- **Time to first token:** skip the router call when code can route, or start the answer model on the early search. Measure across several hours, or on a paid tier with steadier latency.
- **Fact headings:** a year-end balance taken from the next year's 10-Q carries that 10-Q's period ("fiscal 2025 Q2"). Haiku refused two dev questions over it (n17, n24), and on test it hedged n28 (Prologis' liabilities, labeled "fiscal 2025 Q1"), which the judge rated "partly". Label instant facts by their date and the period asked for.
- **Judge:** the follow-up check passed one natural unsupported sentence (t07). Calibrate on a larger, human-labeled set of natural negatives.
- **Scale:** retrieval latency at about 250k chunks (`make seed-fake`), and ingestion timing at 500 filings.

## Known limitations

- **Section labels in four 10-Ks:** JPM, CVX, NVDA and PLD keep MD&A or the financial statements in a separate financial section, which their Items 7, 7A or 8 only point to.
  - The parser labels that content with the item heading before it: JPM under Item 15, CVX under Item 14, and NVDA and PLD under Items 15 and 16 for their Item 8 content. That is 1,373 of the 11,263 chunks.
  - The UI shows the item as stored, and the demo export refuses a citation inside these sections.
  - The fix waits for the next corpus: relabeling changes chunk ids that golden v1 freezes (`docs/memory.md`, 2026-10-18).

Layout: `services/` (api, ingest), `packages/` (core, db, retrieval, llm, sec_client, telemetry), `contracts/` (exported OpenAPI and GraphQL), `clients/` (generated), `web/`, `evals/`, `infra/`. See `docs/context.md` for the design and `docs/todo.md` for the build plan.
