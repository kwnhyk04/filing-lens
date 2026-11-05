# FilingLens

FilingLens answers questions about SEC filings. Every sentence cites the passage or XBRL fact behind it, code checks each quote and amount against that source before the answer is shown, and it refuses when the filings cannot answer. It holds the latest 10-K of 30 US companies.

**Live:** https://filing-lens-virid.vercel.app. "Open the demo" shows saved answers without signing in.

## How it works

1. **Ingest:** workers fetch filings from SEC EDGAR, split them into item sections and chunks, embed the chunks into Postgres (pgvector) with a local model, and load the XBRL facts.
2. **Route:** a small model reads the question: which companies, fiscal years and figure. Off-topic questions, untracked companies and fiscal years with no 10-K yet are refused here. Questions about FilingLens itself or its collection get a fixed answer with figures read from the database, and no answer model runs.
3. **Find:** a figure comes from the XBRL facts first, and text from hybrid search with a reranker. For a comparison of two facts, code does the arithmetic.
4. **Answer:** the model writes each sentence with its citations and quotes the passages it used.
5. **Check:** code confirms each quote is in its passage and each amount matches a cited source. A failed draft is rewritten once, then the sentences that still fail are dropped. If none holds, the answer is refused.

The web app (Next.js on Vercel) calls the API from its server, so the browser never holds the key. The API (FastAPI, GraphQL, Celery, RabbitMQ, Redis) runs on one PC behind a Tailscale Funnel. Claude Haiku 5.5 answers while its credits last, until 2026-11-10 at the latest; then Gemini's and NVIDIA's free tiers do.

## Results

Golden set v2's test split: 55 questions, never tuned on, scored by a separate judge model. Saved reports: [Claude first](evals/reports/2026-11-05-claude-first.md) and [free models only](evals/reports/2026-10-31.md).

| Metric | Target | Claude first | Free models only |
| --- | --- | --- | --- |
| Numeric exact match (n 12) | 0.92 | 1.000 | 1.000 |
| Citation precision | 0.95 | 0.993 | 1.000 |
| Faithfulness | 0.92 | 0.976 | 0.990 |
| Correct refusal (n 10) | 0.90 | 1.000 | 1.000 |
| False refusal (n 45) | 5% or lower | 4.4% | 13.3% |
| Retrieval recall@10 (n 25) | 0.90 | 0.596 | 0.596 |
| Time to first token, p50 | 1.0 s | 2.41 s | 1.47 s |
| Cost per query, as billed | $0.015 | $0.0012 | $0 |

Recall and speed miss their targets. The passage labels behind recall are AI-labeled, cross-checked blind by a second model; no human spot check in v2. Every metric and miss: [evals/README.md](evals/README.md).

## Run it

Needs uv, Docker, GNU make and Node 24.7+.

```sh
cp .env.example .env     # change the passwords and keys, and set SEC_USER_AGENT
uv sync
make models              # once: the local embedding and rerank models
make dev                 # Postgres, Redis, RabbitMQ, the API and the workers
make migrate REV=0008
make seed
npm --prefix web ci
npm --prefix web run hash-password   # paste the line it prints into .env
npm --prefix web run session-secret  # adds SESSION_SECRET to .env
echo 'API_URL=http://127.0.0.1:4100' >> .env
npm --prefix web run dev # http://127.0.0.1:3100
```

Real filings and live answers need a few more settings, and `make test`, `make test-int` and `npx playwright test` run the tests: [docs/guide.md](docs/guide.md).

## Known issues

- Email alerts failed until 2026-11-04 (wrong Gmail sender); fixed since.
- Production still runs `corpus-v1`, which files the financial sections of four 10-Ks (JPM, CVX, NVDA, PLD) under a later item. `corpus-v2` fixes that and waits for its restore ([docs/deploy.md](docs/deploy.md)).
- The API runs on one PC. When it is off, the site falls back to the saved answers.

## Docs

[Guide](docs/guide.md) (setup, every command, the API, CI), [deploy](docs/deploy.md), [monitoring](docs/monitoring.md), [migrations](docs/migrations.md), [eval results](evals/README.md), [eval card](evals/eval-card.md), [third-party credits](docs/third-party.md). Licence: [MIT](LICENSE).
