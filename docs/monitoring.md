# Monitoring

Traces, metrics, dashboards and alerts for FilingLens (step 8). The services export OpenTelemetry over OTLP/HTTP to a collector; Jaeger keeps the traces, Prometheus the metrics, and Grafana shows both. Logs stay JSON on stdout, and every line written inside a span carries its `trace_id` and `span_id`.

## What runs where

| Service | Profile | Role | Host port (127.0.0.1) |
| --- | --- | --- | --- |
| api, ingest, embed | default | Export traces and metrics when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; off (and free) when it is empty. Each process is its own `service.instance.id`, so prefork workers never overwrite each other's counts. | unchanged |
| otel-collector | observability | Receives OTLP on 4318 (HTTP) and 4317 (gRPC) behind a `memory_limiter`. Traces go to Jaeger; metrics are re-exposed for Prometheus on 8889, with exemplars, and expire 1 minute after a process stops. It probes the API's `/readyz` every 15 s (`httpcheck`) and serves its own metrics on 8888. | 4328 / 4327 |
| jaeger | observability | Traces in memory, at most 20,000 (a restart clears them). Its own metrics on 8888. | 16687 |
| prometheus | observability | Scrapes the collector (the services' metrics with `honor_labels`, and its own), RabbitMQ's per-queue endpoint (`:15692/metrics/detailed`, Celery's event and control queues dropped), Jaeger and itself every 15 s. Evaluates `infra/prometheus-alerts.yml`. Keeps 15 days or 1 GB (volume `prometheus-data`), exemplars included. | 9091 |
| grafana | observability | Datasources `prometheus` and `jaeger` and three dashboards, provisioned read-only in a FilingLens folder. Anonymous viewers in development only; the prod override turns them off. Usage reporting off. | 3101 |

The monitoring UIs stay on 127.0.0.1 and never go through Tailscale Funnel. In production only Grafana publishes (127.0.0.1:3111), and Alertmanager runs there too: it groups the alerts and sends them to Discord and email (`docs/deploy.md`, Alert delivery). Prometheus finds it through `infra/prometheus-alertmanagers.yml`, which only production mounts, so development sends nothing.

## Turning it on

In `.env`:

```
COMPOSE_PROFILES=observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:${OTEL_HTTP_PORT}
```

Then `make dev`. The value is the host's URL, for processes run with `uv run --env-file .env`; compose gives the containers `http://otel-collector:4318` whenever the variable is set, and an empty value when it is not. Set both or neither: with the endpoint set and no collector, every process logs a failed export each 15 s.

`OTEL_SERVICE_NAME` defaults to `filinglens-api` and `filinglens-ingest`; compose sets `filinglens-embed` for the embed worker. The name is the Prometheus `job` label.

## Traces

- **Requests:** FastAPI's own telemetry (`FastAPI(telemetry=...)`) makes one server span per request, named after its route, with `request_id`, the status and the route. The health probes are left out. `url.query` keeps parameter names only (`q&cursor`); a part without `=`, or a name longer than 24 characters, becomes `_`, since it may be search words or a pasted key. So search text never leaves the process, and access lines follow the same rule.
- **Answers:** a span for each stage that ran (`route`, `facts`, `retrieve`, `generate`, `regenerate`), built when the stage ends, so no span is current across the stream's yields. Each model call is a `chat <model>` client span with the `gen_ai.*` attributes, its tokens and, for a stream, a `first_token` event. The request's span carries `filinglens.answer.outcome`, `.reason` (the refusal code or error), `.route`, `.degraded` and the tokens, and a `fallback` event (role, from and to model, error type) for each model call that fell back.
- **Search:** a `search` span with one child per phase (`embed`, `sql`, `load`, `rerank`).
- **Ingest jobs:** one trace from `POST /v1/ingest-jobs` through every task. Our own Celery hooks carry the context: each publish adds a `traceparent` header (no span, so a publish that fails leaves nothing open), and each task run is a consumer span `run/<task>` that continues it. A run carries `filinglens.ingest.outcome` (succeeded, retried, paused or dead_lettered); a full fetch queue adds a `fetch queue full` event to discover's run; every SEC call is a `SEC GET <kind>` span with its status, the limiter wait and whether the cache answered.
- **Never recorded:** question text, prompts, replies or quotes, query values, keys, the SEC User-Agent (it holds a contact), exception messages (spans carry the error type only).

### Finding a trace

- **A reported request:** take its `X-Request-ID` response header. In Jaeger, search service `filinglens-api` with tags `request_id=<id>`.
- **A log line:** its `trace_id` goes into Jaeger's "Lookup by Trace ID".
- **A slow point on a dashboard:** latency panels show exemplars; a point's trace link opens it in Jaeger.
- **An ingest job:** search `filinglens-api`, operation `POST /v1/ingest-jobs`; the trace continues into `filinglens-ingest` and `filinglens-embed`.
- **Failed answers:** search tags `filinglens.answer.outcome=failed`.

## Metrics

Every instrument is declared in `packages/telemetry/src/filinglens_telemetry/metrics.py` (`SPECS`), and a test checks that the dashboards and alerts name only those. Labels come from small fixed sets: never a request id, question, CIK, accession number, chunk id or key. Prometheus names: dots become underscores, `s` adds `_seconds`, counters end in `_total`.

| Metric | Labels | What it counts |
| --- | --- | --- |
| `http_server_request_duration_seconds` | `http_route`, `http_request_method`, `http_response_status_code` | Every request but the probes (FastAPI). |
| `filinglens_answers_total` | `outcome` (answered, refused, failed, cancelled), `reason` | Answers that ended. Refusal codes: out_of_scope, untracked_company, time_trap, no_relevant_passages, insufficient_evidence, validation_failed. Failures: ai_unavailable, upstream_error, timeout, internal. |
| `filinglens_answers_rejected_total` | `reason` (rate_limited, ai_disabled, budget_exhausted, budget_unavailable, overloaded) | Answers refused before any work. |
| `filinglens_answer_ttft_seconds`, `filinglens_answer_stage_duration_seconds` | `route`, `stage` (route, facts, retrieve, generate, regenerate, total) | Time to first token and time per stage. |
| `filinglens_answer_regenerations_total`, `filinglens_answer_dropped_sentences_total`, `filinglens_answer_credits_usd_total` | none | Validation's second drafts and removed sentences; Claude credits. |
| `filinglens_answers_inflight`, `filinglens_answers_inflight_limit` | none | Answers admitted and not ended, against `LLM_MAX_INFLIGHT`. |
| `filinglens_ai_tokens_today`, `filinglens_ai_token_budget` | none | The day's tokens (Redis `ai:usage:<UTC date>`) against `DAILY_AI_TOKEN_BUDGET`. No reading while Redis is down. |
| `gen_ai_client_operation_duration_seconds`, `gen_ai_client_token_usage`, `filinglens_llm_calls_total` | provider, model, error type or outcome | Every model call. |
| `filinglens_search_duration_seconds`, `filinglens_search_rerank_timeouts_total` | `phase` (embed, sql, load, rerank, total) | Search time per phase; reranks past `RERANK_TIMEOUT_MS`. |
| `filinglens_ingest_tasks_total`, `filinglens_ingest_task_duration_seconds` | `task`, `outcome` | Task runs: succeeded, retried, paused or dead_lettered. |
| `filinglens_embed_chunks_total` | none | Chunks the embed stage wrote. |
| `filinglens_sec_requests_total`, `filinglens_sec_cooloffs_total`, `filinglens_sec_refusals_total` | `kind`, `status` | Requests sent to SEC, its 403 and 429 cool-offs, and calls stopped by a recorded refusal. |
| `rabbitmq_detailed_queue_messages_ready`, `rabbitmq_detailed_queue_consumers` | `queue` | Queue depth and consumers (RabbitMQ). |
| `httpcheck_status`, `httpcheck_error` | `http_url`, `http_status_class` | The collector's probe of `/readyz`. |

The counters that alerts read start at 0 for every known label value when a process starts, so the first event after a restart counts.

## Dashboards

| Dashboard | Question it answers | Panels |
| --- | --- | --- |
| FilingLens: service health | Is FilingLens up, and are requests fast and error-free? Open it first. | API ready, alerts firing (count and list), consumers per work queue, scrape targets up, requests and 5xx share by route, p50/p95 latency by route with exemplars, 429/500/502/503 counts, search p95 by phase against 250 ms, reranks that timed out, answers in flight against the cap, rejections by reason. |
| FilingLens: answers and LLM | Are answers good, fast and affordable? The production view of what the evals measure. | Answers by outcome and reason, TTFT p50/p95 against 1 and 2 s, full answer p95 against 6 s, stage p50s, regenerations and dropped sentences per answer, model calls by provider, model and outcome, model call p95, the failed share per provider, tokens per answer against 8,000 in and 600 out, credits spent, today's tokens against the budget. |
| FilingLens: ingest pipeline | Is ingestion moving, and how fast? Target: 500 filings in 2 hours. | Ready messages per queue (fetch caps at 10,000), dead-letter queues, consumers, task runs by outcome, task p95, filings chunked per hour against 250, chunks embedded per second against 13.0, SEC requests per second by kind against 8, SEC status codes, cool-offs and refusals. |

The JSON lives in `infra/dashboards/`; Grafana reads it read-only, so edit the files and restart Grafana.

## Alerts

Fourteen rules in `infra/prometheus-alerts.yml`, each with a firing and a quiet test case (`make monitoring-check`, also in CI's lint job). The tests also hold each `for` before it elapses, and keep the ratio rules quiet above their minimum counts but under their ratios. The label allowlist is checked once the whole test session ends, over every series any test recorded. They show in Prometheus (`/alerts`) and on the service health dashboard, and production's Alertmanager sends them to Discord and email (`docs/deploy.md`, Alert delivery). Every rule keeps firing for 10 minutes after its condition clears (`keep_firing_for`), so a flapping condition stays one alert and one message. Ratio rules need a minimum count, so one event at low traffic cannot fire them.

| Alert | Severity | Fires when |
| --- | --- | --- |
| ApiNotReady | critical | `/readyz` is not 2xx, or the probe fails, for 2 minutes |
| WorkerNotConsuming | critical | A work queue holds ready messages and has had no consumer for 5 minutes |
| SecRefused | critical | Any SEC refusal in 15 minutes |
| AnswersFailing | critical | 2 or more failed answers in 30 minutes |
| AiBudgetExhausted | critical | Today's tokens reach a budget above 0 |
| AiBudgetNearlyUsed | warning | 80% to 100% of the budget for 5 minutes |
| LlmProviderErrors | warning | Over 25% of a provider's calls fail in 30 minutes, with at least 4 calls |
| ClaudeKeyOrModelRejected | critical | Anthropic rejected Claude's key or model (401, 403, 404) |
| CitationValidationDegraded | warning | Over 25% of drafts written again in 6 hours, with at least 8 drafts |
| SearchDegraded | warning | Over 10% of reranks time out in 1 hour, with at least 10 reranks |
| DeadLetters | warning | A dead-letter queue holds a message for 1 minute |
| IngestStalled | warning | Work queues hold ready messages but no task finished in 15 minutes, for 10 minutes |
| MonitoringTargetDown | warning | A scrape target is down for 5 minutes |
| TelemetryMissing | warning | The api sent no telemetry for 10 minutes; ingest or embed, while their queues have a consumer or ready work |

No alert on time to first token: free-tier latency drifts with the hour, so it would fire on nothing you can act on. The answers dashboard shows it against its targets.

### ApiNotReady

The API is down, or a store it needs is unreachable. `docker compose logs api` shows `readiness check failed` with the check (`postgres`, `rabbitmq` or `redis`); `docker compose ps` shows which container is unhealthy.

### WorkerNotConsuming

`ingest` or `embed` is down or crash-looping while its queue holds work, so jobs stall silently. Production runs the workers for an ingest alone, so there an idle queue with no consumer does not fire it. `docker compose ps ingest embed`, then `docker compose logs --tail 100 <service>`: a configuration error names the variable at startup.

### SecRefused

SEC answered 403 again right after a cool-off, so every fetch fails at once. Fix `SEC_USER_AGENT` in `.env` (the tool's name and a contact email), restart the workers (`docker compose up -d ingest embed`; a restart clears the recorded refusal), then replay the dead letters (see DeadLetters).

### AnswersFailing

On the answers dashboard, "Answers by outcome and reason" names the failure: `ai_unavailable` (a provider refused the key, has no credits left, or stayed rate limited after the fallbacks), `upstream_error`, `timeout` (30 s) or `internal` (a bug: the API log holds the traceback with the request id). In Jaeger, search `filinglens.answer.outcome=failed`. AI switched off and the budget are rejections, not failures.

### AiBudgetExhausted

Answers return 503 until 00:00 UTC; the budget check fails closed. If the spend was intended, raise `DAILY_AI_TOKEN_BUDGET` and restart the api. Otherwise look for the runaway: tokens per answer, and model calls by provider.

### AiBudgetNearlyUsed

A warning before answers stop. Same panels as above.

### LlmProviderErrors

The provider's error types are on `gen_ai_client_operation_duration_seconds` (label `error_type`). Check its status page and quota. Answers fall back meanwhile, which cites worse (decision 4, `docs/memory.md`) and is slower.

### ClaudeKeyOrModelRejected

Anthropic answered 401, 403 or 404, so Claude is off for good in every process (`filinglens_claude_off{kind="key_or_model"}` is 1) and answers use the free models. The api log has `claude rejected the key or model` with the status and Anthropic's message.
1. Fix `ANTHROPIC_API_KEY` or the Claude model in `LLM_PRIMARY` (or `LLM_ANSWER_FALLBACK`).
2. Delete the switch-off: `docker exec <redis container> redis-cli DEL ai:claude:off`.
3. Restart the api, which also forgets it in memory.

Credits running out also switch Claude off (`kind="credits"`); that is planned and does not alert.

### CitationValidationDegraded

The production proxy for citation precision: more drafts fail validation. The share is of drafts (`generate` stages), whatever the answer's outcome. Open answer traces with a `regenerate` span, compare with the evals (`make eval`), and look for a provider or prompt change. The dev baseline is about 4% (2 of 53 drafts).

### SearchDegraded

Reranks run past `RERANK_TIMEOUT_MS`, so searches keep the fused order, which costs MRR. Usually CPU contention from the embed worker; the search p95 by phase panel shows where the time goes.

### DeadLetters

A filing or company failed for good: the `dead_letters` table and the job's failures hold the reason. Fix the cause, then replay: `uv run --env-file .env python -m filinglens_ingest.replay --queue fetch.dlq --limit 100` (or the queue named in the alert). It also catches a task killed at the 330 s hard limit, which writes no `dead_letters` row.

### IngestStalled

Workers are alive but stuck: a cool-off loop (the SEC panel), pauses while Redis is down, or a hung task. `docker compose logs --tail 200 ingest`.

### MonitoringTargetDown

Prometheus cannot scrape a target, so the alerts on its metrics are blind. `docker compose --profile observability ps`, then restart the target.

### TelemetryMissing

The service stopped exporting: check that `OTEL_EXPORTER_OTLP_ENDPOINT` is set, that the collector runs, and that the service itself runs. Without this rule every alert on the services' metrics would quietly resolve. A worker counts only while its queues have a consumer or ready work, so production's idle workers stay quiet.

## Screenshots

From the live check on a throwaway stack (2026-10-18), in `docs/screenshots/`: `service-health.png`, `answers.png`, `ingest.png` (the dashboards over 30 minutes that held 3 ingested filings, 10 answers and both alert drills), `trace-ingest.png` (one ingest job: 3 services, 31 spans) and `trace-answer.png` (a streamed answer whose router call fell back from Groq to NVIDIA).

Jaeger 2.21 serves only its v3 query API (`/api/v3/traces`, `/api/v3/services`); the old `/api/traces` answers 404.

## Checks

- `make test`: setup and redaction, the access log, trace ids in logs, answer spans and metrics for every outcome, provider spans, SEC counters, task outcomes, our Celery propagation (a failed publish included), the label allowlist, and the drift test against the dashboards and alerts.
- `make test-int`: one trace from `POST /v1/ingest-jobs` through discover, fetch, parse, chunk, embed and facts, exported by a worker to an OTLP sink in the test, with no secret in it; search spans and metrics.
- `make monitoring-check`: `promtool check config`, `promtool test rules`, `amtool check-config` (Alertmanager) and `otelcol-contrib validate`, from the compose images pinned by digest.
- `infra/tests/test_alerting.py` (`make test`, `make test-int`): Alertmanager's config and template, its entrypoint, and one delivery to a fake Discord webhook and a fake SMTP server on a network with no route out.

## Left out

| What | Add it when |
| --- | --- |
| An alert when delivery fails (`alertmanager_notifications_failed_total`, so each channel reports the other's failure) | todo.md |
| Log shipping (Loki); logs carry trace ids already | `docker compose logs` with grep falls short |
| SQL statement spans (the contrib SQLAlchemy instrumentation supports only SQLAlchemy below 2.1) | A slow query needs hunting: SQLAlchemy engine events, about 20 lines |
| Postgres and Redis exporters; `/readyz` covers reachability | Database tuning starts |
| Browser and backend-for-frontend tracing; the API already accepts `traceparent` | Step 9 |
| GraphQL per-resolver spans, eval telemetry, tail sampling, a dead man's switch | Needed |
