"""Every metric FilingLens records, in one place: dashboards and alerts are checked against SPECS.

Instruments come from the OpenTelemetry API, so they cost nothing until configure_telemetry
installs the SDK. Labels come from small fixed sets only: never a request id, question, CIK,
accession number, chunk id or key.
"""

from collections.abc import Callable, Iterable, Sequence
from typing import Literal

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Counter, Histogram, Observation, UpDownCounter

Kind = Literal["counter", "histogram", "updown", "gauge"]
SPECS: list[tuple[str, str, Kind]] = []  # (name, unit, kind) of every instrument below

# Seconds, on the targets (retrieval 0.25 s, TTFT 1 and 2 s, answer 6 s) up to the 30 s limit.
SECONDS = (0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 10.0, 15.0, 20.0, 30.0)
PHASES = (0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1.0, 2.5, 5.0)  # search phases
TASKS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)  # ingest tasks, 300 s soft limit
TOKENS = (16, 64, 256, 1024, 2048, 4096, 8192, 16384, 32768)

meter = metrics.get_meter("filinglens")


def _counter(name: str, unit: str, description: str) -> Counter:
    SPECS.append((name, unit, "counter"))
    return meter.create_counter(name, unit=unit, description=description)


def _histogram(name: str, unit: str, description: str, buckets: Sequence[float]) -> Histogram:
    SPECS.append((name, unit, "histogram"))
    return meter.create_histogram(
        name, unit=unit, description=description, explicit_bucket_boundaries_advisory=buckets
    )


def _updown(name: str, unit: str, description: str) -> UpDownCounter:
    SPECS.append((name, unit, "updown"))
    return meter.create_up_down_counter(name, unit=unit, description=description)


# Answers. Outcome answered, refused (reason: the refusal code), failed (reason: the error code,
# or timeout) or cancelled (the client left).
ANSWERS = _counter("filinglens.answers", "{answer}", "Answers by outcome and reason.")
ANSWER_TTFT = _histogram(
    "filinglens.answer.ttft", "s", "Time to the first visible text of an answer.", SECONDS
)
ANSWER_STAGE = _histogram(
    "filinglens.answer.stage.duration",
    "s",
    "Time in each answer stage; total is the whole.",
    SECONDS,
)
REGENERATIONS = _counter(
    "filinglens.answer.regenerations", "{regeneration}", "Drafts that failed validation."
)
DROPPED = _counter(
    "filinglens.answer.dropped_sentences", "{sentence}", "Sentences validation removed."
)
CREDITS = _counter("filinglens.answer.credits_usd", "", "Prepaid credits answers spent (Claude).")
REJECTED = _counter(
    "filinglens.answers.rejected", "{answer}", "Answers refused before any work, by reason."
)
INFLIGHT = _updown("filinglens.answers.inflight", "{answer}", "Answers admitted and not ended.")

# Model calls, with the OpenTelemetry GenAI names, plus a counter whose series exist from start.
LLM_DURATION = _histogram(
    "gen_ai.client.operation.duration", "s", "Duration of each model call.", SECONDS
)
LLM_TOKENS = _histogram("gen_ai.client.token.usage", "{token}", "Tokens per model call.", TOKENS)
LLM_CALLS = _counter("filinglens.llm.calls", "{call}", "Model calls by provider and outcome.")

# Search.
SEARCH = _histogram("filinglens.search.duration", "s", "Search time by phase.", PHASES)
RERANK_TIMEOUTS = _counter(
    "filinglens.search.rerank_timeouts", "{search}", "Searches whose rerank timed out."
)

# Ingest.
INGEST_TASKS = _counter(
    "filinglens.ingest.tasks", "{task}", "Ingest task runs by task and outcome."
)
INGEST_TASK_DURATION = _histogram(
    "filinglens.ingest.task.duration", "s", "Ingest task run time.", TASKS
)
EMBEDDED = _counter("filinglens.embed.chunks", "{chunk}", "Chunks the embed stage wrote.")
SEC_REQUESTS = _counter(
    "filinglens.sec.requests", "{request}", "Requests sent to SEC, by kind and status."
)
SEC_COOLOFFS = _counter("filinglens.sec.cooloffs", "{cooloff}", "SEC 403 or 429 cool-offs.")
SEC_REFUSALS = _counter(
    "filinglens.sec.refusals", "{refusal}", "SEC calls stopped by a recorded refusal."
)

REFUSALS = (
    "out_of_scope",
    "untracked_company",
    "time_trap",
    "no_relevant_passages",
    "insufficient_evidence",
    "validation_failed",
)
FAILURES = ("ai_unavailable", "upstream_error", "timeout", "internal")
REJECTIONS = ("rate_limited", "ai_disabled", "budget_exhausted", "budget_unavailable", "overloaded")
TASK_NAMES = ("discover", "fetch", "parse", "chunk", "embed", "facts")
TASK_OUTCOMES = ("succeeded", "retried", "paused", "dead_lettered")
SEC_KINDS = ("submissions", "document", "companyfacts", "tickers")  # SecClient's request kinds


def start_answer_series(models: Iterable[str]) -> None:
    """Create the series alerts count from 0, so increase() sees the first event after a start."""
    ANSWERS.add(0, {"outcome": "answered", "reason": "none"})
    ANSWERS.add(0, {"outcome": "cancelled", "reason": "none"})
    for reason in REFUSALS:
        ANSWERS.add(0, {"outcome": "refused", "reason": reason})
    for reason in FAILURES:
        ANSWERS.add(0, {"outcome": "failed", "reason": reason})
    for reason in REJECTIONS:
        REJECTED.add(0, {"reason": reason})
    for model in models:  # provider:model
        provider, _, name = model.partition(":")
        for outcome in ("ok", "error"):
            LLM_CALLS.add(0, {"provider": provider, "model": name, "outcome": outcome})
    REGENERATIONS.add(0)
    RERANK_TIMEOUTS.add(0)


def start_ingest_series() -> None:
    """Create the ingest series alerts count from 0 (see start_answer_series)."""
    for task in TASK_NAMES:
        for outcome in TASK_OUTCOMES:
            INGEST_TASKS.add(0, {"task": task, "outcome": outcome})
    for kind in SEC_KINDS:  # the common status, so a process's first requests show too
        SEC_REQUESTS.add(0, {"kind": kind, "status": "200"})
    SEC_REFUSALS.add(0)


def observe_answer_limits(
    tokens_today: Callable[[], int | None], token_budget: int, inflight_limit: int
) -> None:
    """Gauges for the day's AI tokens against the budget, and the in-flight cap. Call it once per
    process (__main__): a second registration under a name keeps the first callback."""

    def tokens(_: CallbackOptions) -> Iterable[Observation]:
        used = tokens_today()
        return [] if used is None else [Observation(used)]  # no reading while Redis is down

    def constant(value: int) -> Callable[[CallbackOptions], Iterable[Observation]]:
        return lambda _: [Observation(value)]

    for name, unit, callback, description in (
        ("filinglens.ai.tokens_today", "{token}", tokens, "LLM tokens spent today (UTC)."),
        ("filinglens.ai.token_budget", "{token}", constant(token_budget), "DAILY_AI_TOKEN_BUDGET."),
        (
            "filinglens.answers.inflight_limit",
            "{answer}",
            constant(inflight_limit),
            "LLM_MAX_INFLIGHT.",
        ),
    ):
        meter.create_observable_gauge(
            name, callbacks=[callback], unit=unit, description=description
        )


SPECS.extend(
    (name, "{token}" if "ai." in name else "{answer}", "gauge")
    for name in (
        "filinglens.ai.tokens_today",
        "filinglens.ai.token_budget",
        "filinglens.answers.inflight_limit",
    )
)
