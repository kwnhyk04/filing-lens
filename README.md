# FilingLens

FilingLens answers questions about SEC filings. Every sentence cites the passage or XBRL fact behind it. Before an answer is shown, code checks each quote word for word, and each dollar amount, percentage and comma-grouped number against a cited source in scale, sign and unit. It refuses when the filings cannot answer. It holds the latest 10-K of 30 US companies.

**Live:** https://filing-lens-virid.vercel.app. "Open the demo" shows saved answers without signing in.

## How it works

1. **Ingest:** workers fetch filings from SEC EDGAR, split them into item sections and chunks, embed the chunks into Postgres (pgvector) with a local model, and load the XBRL facts.
2. **Route:** a small model reads the question: which companies, fiscal years and figure. Off-topic questions, untracked companies and fiscal years with no 10-K yet are refused here. Questions about FilingLens itself or its collection get a fixed answer with figures read from the database, and no answer model runs.
3. **Find:** a figure comes from the XBRL facts first, and text from hybrid search with a reranker. For a comparison of two facts, code does the arithmetic.
4. **Answer:** the model writes each sentence with its citations and quotes the passages it used.
5. **Check:** code confirms each quote is in its passage, and that each amount it can read (dollars, percentages, comma-grouped numbers) matches a cited source in scale, sign and unit, with rule 4's rounding allowed. It does not check which line item or period a figure belongs to, or numbers written any other way. A failed draft is rewritten once, then the sentences that still fail are dropped. If none holds, the answer is refused.

The web app (Next.js on Vercel) calls the API from its server, so the browser never holds the key. The API (FastAPI, GraphQL, Celery, RabbitMQ, Redis) runs on one PC behind a Tailscale Funnel. Claude Haiku 5.5 answers while its credits last, until 2026-11-10 at the latest; then Gemini's and NVIDIA's free tiers do.

## Results

Golden set v3's test split on `corpus-v3`: 55 questions, 11,375 passages, scored by a separate judge model. Both runs measured the same code on 2026-11-06. Saved reports: [Claude first](evals/reports/2026-11-06-claude-first.md) and [free models only](evals/reports/2026-11-06.md). Each cell gives the 95% interval. **Met** or **missed** means the whole interval clears or misses the target; anything else is **unclear**.

| Metric | Target | Claude first | Free models only |
| --- | --- | --- | --- |
| Numeric exact match (n 12) | 0.92 | 1.000 (0.758 to 1.000), unclear | 1.000 (0.758 to 1.000), unclear |
| Citation precision | 0.95 | 1.000 (1.000 to 1.000, n 42), met | 0.992 (0.974 to 1.000, n 39), met |
| Faithfulness | 0.92 | 0.985 (0.961 to 1.000, n 42), met | 0.990 (0.968 to 1.000, n 39), met |
| Correct refusal (n 10) | 0.90 | 1.000 (0.722 to 1.000), unclear | 1.000 (0.722 to 1.000), unclear |
| False refusal (n 45) | 5% or lower | 6.7% (2.3% to 17.9%), unclear | 13.3% (6.3% to 26.2%), missed |
| Retrieval recall@10 (n 25) | 0.90 | 0.599 (0.485 to 0.713), missed | 0.599 (0.485 to 0.713), missed |
| Time to first token, p50 | 1.0 s | 1.95 s (1.93 to 2.06, n 43), missed | 1.97 s (1.84 to 3.46, n 37), missed |
| Full answer, p95 | 6 s | 6.74 s (4.54 to 7.51, n 47), unclear | 9.09 s (6.96 to 11.12, n 42), missed |
| Cost per query, as billed | $0.015 | $0.0011 ($0.0009 to $0.0013, n 55), met | $0 (n 55), met |

What these numbers do and do not show:

- **Corpus:** both runs used `corpus-v3`, which carries the parser fix of 2026-11-06. Production has served the same corpus since that day.
- **Against the runs before:** the stricter amount check changed no verdict in the 346 draft sentences of these two runs, and no cited quote depends on which corpus it came from. c19's new false refusal under Claude first fails the old check too: the model's rewrite broke two older rules.
- **Latency:** in the free run, Gemini's own first token took over 3 s on 12 of 43 calls, against none on 2026-10-31. Neither the check nor the corpus explains that; the cause is not confirmed.
- **Numeric gold** comes from the same XBRL lookup the answers use, so exact match shows the model repeats the figure it was given, not that the lookup is right.
- **Passage gold** is golden v2's, moved to the re-parsed passages by exact text or word overlap. It is AI-labeled, cross-checked blind by a second model on 50 passages; no human spot check in v2. 33 gold passages of this split wait for a person and stay out of the score, so recall does not compare with v2's. Claude made those labels, its labels calibrated the judge, and Claude wrote the Claude-first answers.
- **Test split:** no prompt was tuned on it, but its answers were read by hand on 2026-11-05, before the amount check changed. Treat it as seen.

Every metric and miss: [evals/README.md](evals/README.md).

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
- A table's unit is checked only where the quote, its passage or the 40,000 characters above state one. A figure from a table that states none within reach is dropped.
- A right comparison can still be refused: a rewrite that cites the calculation without both its facts, or compares without stating both figures, loses those sentences.
- The API runs on one PC. When it is off, the site falls back to the saved answers.

## Docs

[Guide](docs/guide.md) (setup, every command, the API, CI), [deploy](docs/deploy.md), [monitoring](docs/monitoring.md), [migrations](docs/migrations.md), [eval results](evals/README.md), [eval card](evals/eval-card.md), [third-party credits](docs/third-party.md). Licence: [MIT](LICENSE).
