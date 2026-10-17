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
9. Optional, a paid answer fallback: set `ANTHROPIC_API_KEY` and `LLM_ANSWER_FALLBACK=anthropic:claude-haiku-5-5`. Answers then try Claude Haiku 5.5 after Gemini and before NVIDIA, on prepaid credits, until the credits are gone or `ANTHROPIC_CREDITS_EXPIRE` (default 2026-11-10) arrives. Left empty, the chain stays free-only.

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
| `make eval` | Golden-set eval, needs `make dev`: `SUITE=retrieval\|answer\|all SPLIT=dev\|test SUBSET=full\|ci`. `ARGS` takes `--tag=NAME` (calls the answer models live once under NAME; earlier replies stay cached), `--primary-tag=NAME` (the same for the answer model only, with router replies from the cache), `--router-primary=PROVIDER:MODEL` (reuse the router replies of that answer model's run, so two answer models get identical inputs), `--min-relevance=X`, `--thinking=default` and `--no-judge`. Runs check the floors in `evals/thresholds.json` but never write them; `uv run python -m evals.harness --set-floors REPORT` writes the floors the rule gives a saved report's measured values, latency included, keeping only tighter ones. The answer suite calls the live models and prints a quota estimate first. Replies are cached, so a run stopped by a quota (exit 2) resumes when rerun. Reports go to `evals/reports/`. Exits 1 on a broken floor and 3 when the golden set or the corpus changed since the freeze |
| `make audit` / `make label` | Interactive passage labeling for the golden set (resumable). Both refuse once the set is frozen |
| `make calibrate` | Judge calibration. On screen you label sampled answer sentences against their cited sources. `ARGS=export` writes the sample for an outside labeler, and `ARGS=import` scores its labels from `claude_labels.jsonl`. The judge then scores the same sentences, Cohen's kappa goes to `evals/calibration/v1/result.json` with the labeler named, and judge metrics count only at 0.7 or more. A first argument `followup` (`ARGS="followup export"`) works on the second sample in `evals/calibration/v1-followup/`: natural sentences that fail the validator, from the fallback-model runs |

- API: `http://127.0.0.1:4100`. `/healthz` and `/readyz` need no key; everything else needs `X-API-Key`. `API_KEY` opens `/v1/companies`, `/v1/filings`, `/v1/search`, `/v1/answers` (plus `/stream` for Server-Sent Events) and `/graphql`; the admin routes `/v1/ingest-jobs` take only `ADMIN_API_KEY`. The contract is `contracts/openapi.json` (errors are RFC 9457 problems) and `contracts/schema.graphql`. Companies, filings and the GraphQL sections, chunks and facts come from Postgres. An ingest job discovers each company's 10-K and 10-Q filings on EDGAR, fetches them into the SEC cache (`.cache/sec`, shared by the worker and host runs), splits them into item sections and token-aware chunks, embeds the chunks on the `embed` worker, and loads the company's XBRL facts. Search and answers run on that data (answers need `AI_ENABLED=true`).
- Limits: each key gets 60 requests a minute, and 10 answers a minute (429 with `Retry-After` and `RateLimit-*`). Bodies are capped at 64 KB (413) and answers at 30 s (502). Answers return 503 `ai_unavailable` once the day's LLM tokens (UTC) reach `DAILY_AI_TOKEN_BUDGET`, or when `AI_ENABLED=false` (the default), and 503 `overloaded` past `LLM_MAX_INFLIGHT` answers in progress.
- Model chain: an answer goes to `LLM_PRIMARY` (Gemini), then `LLM_ANSWER_FALLBACK` if set (Claude Haiku 5.5), then `LLM_FALLBACK` (NVIDIA); the router falls back to `LLM_FALLBACK` only. Claude is skipped for the rest of the credit period once its credits are gone (a 402, a 400 naming a spend limit, or a 429 without `Retry-After`; the log says `claude is off for the rest of the credit period`) and from `ANTHROPIC_CREDITS_EXPIRE`. A 429 asking for 10 s or less is retried once. `usage.cost_usd` in an answer is the credits it spent.
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
- The judge behind citation precision and faithfulness (gpt-oss-120b) is calibrated against labels by Claude, a different and stronger model than the judge, not by a human. On 29 sentences it agreed 93.1%, Cohen's kappa 0.84 (95% CI 0.59 to 1.00), so those metrics count. Every negative in that sample was constructed. A follow-up spot check on natural sentences that fail the validator (2026-10-17) found the judge failing 3 of the 4 that Claude labeled not supported.
- While golden v1 is in use, don't run `make seed-real` or queue ingest jobs (see `make seed-real` above).

### Official results: test split, 2026-10-17

The run covers 30 questions on the free tiers. Gemini 3.5 Flash-Lite answers, gpt-oss-20b routes and gpt-oss-120b judges (report `evals/reports/2026-10-17.md`). The floors in `evals/thresholds.json` come from this run.

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

Layout: `services/` (api, ingest), `packages/` (core, db, retrieval, llm, sec_client, telemetry), `contracts/` (exported OpenAPI and GraphQL), `clients/` (generated), `web/`, `evals/`, `infra/`. See `docs/context.md` for the design and `docs/todo.md` for the build plan.
