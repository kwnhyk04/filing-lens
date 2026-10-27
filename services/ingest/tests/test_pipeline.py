"""Ingest pipeline against real Postgres, Redis and RabbitMQ and a fake SEC server (needs Docker).

The step 4 done checks: 20 workers stay under 8 SEC requests a second, a filing that fails every
attempt lands in fetch.dlq and dead_letters (then replays), a full fetch queue makes discover back
off without losing filings, and a killed worker's message is redelivered without duplicate rows.
Step 4b: facts load once and set fiscal periods; one unparseable filing fails only its own item,
and a rerun downloads no document again. The fake SEC serves a trimmed real Apple 10-K.
"""

import asyncio
import gzip
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from amqp.exceptions import NotFound
from celery import Celery
from fastapi.testclient import TestClient
from kombu import Connection, Producer
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from redis import Redis
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import filinglens_sec_client
from filinglens_api.main import app
from filinglens_core import queues
from filinglens_core.errors import FilingLensError, NotFoundError, RateLimitedError, UpstreamError
from filinglens_core.settings import EMBEDDING_MODELS
from filinglens_db.models import (
    Chunk,
    Company,
    DeadLetter,
    Filing,
    FilingStatus,
    FinancialFact,
    FiscalSource,
    IngestJob,
    IngestJobCompany,
    IngestJobItem,
    ItemStatus,
    JobStatus,
    Section,
)
from filinglens_ingest import topology
from filinglens_ingest.reparse import queue_embed, reparse
from filinglens_ingest.replay import replay
from filinglens_sec_client import (
    COOL_OFF_KEY,
    REFUSED_KEY,
    REQUESTS_KEY,
    STRIKE_KEY,
    SecClient,
    SecRefusedError,
)

pytestmark = pytest.mark.integration
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
RUN_WORKER = Path(__file__).with_name("run_worker.py")
USER_AGENT = "FilingLens tests tests@filinglens.test"
CIK = 1
ACCESSION = "0000000001-26-000001"
DOCUMENT = f"/Archives/edgar/data/{CIK}/{ACCESSION.replace('-', '')}/one-10k.htm"
JITTER_S = 0.05  # scheduling noise between a Redis grant and the fake server's clock
FIXTURES = Path(__file__).with_name("fixtures")
TEN_K = (FIXTURES / "aapl-10k-2025.htm").read_bytes()  # a real 10-K, trimmed
FINISHED = (JobStatus.SUCCEEDED, JobStatus.PARTIALLY_FAILED, JobStatus.FAILED)
# A worker that takes a filing from fetch to chunk.
TO_EMBED = f"{queues.FETCH},{queues.FETCH_RETRY},{queues.PARSE},{queues.CHUNK},{queues.EMBED}"

type Route = Callable[[], tuple[int, bytes]]


class FakeSec:
    """EDGAR stand-in on 127.0.0.1: answers each path from `routes` and logs every arrival."""

    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.default: Route | None = None  # answers paths without a route; 404 when None
        self.requests: list[tuple[float, str]] = []  # (time.perf_counter(), path)
        self.agents: set[str] = set()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                fake.requests.append((time.perf_counter(), self.path))
                fake.agents.add(self.headers.get("User-Agent", ""))
                route = fake.routes.get(self.path, fake.default)
                status, body = route() if route else (404, b"")
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                """Quiet: the tests read `requests` instead."""

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def hits(self, path: str) -> int:
        return sum(1 for _, seen in self.requests if seen == path)


@dataclass
class Worker:
    process: subprocess.Popen[bytes]
    log: Path

    def output(self) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace")


def run[T](url: str, work: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    async def main() -> T:
        engine = create_async_engine(url)
        try:
            return await work(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def wait_for(check: Callable[[], bool], timeout: float, *workers: Worker) -> None:
    """Poll `check` until it holds; on timeout, fail with the tail of each worker's log."""
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            logs = "\n".join(worker.output()[-4000:] for worker in workers)
            raise AssertionError(f"timed out after {timeout} s\n{logs}")
        time.sleep(0.25)


def queue_state(broker: Connection, name: str) -> tuple[int, int]:
    """(messages, consumers) of a queue; (0, 0) while it does not exist."""
    channel = broker.channel()
    try:
        _, messages, consumers = channel.queue_declare(queue=name, passive=True)
    except NotFound:  # RabbitMQ closed the channel
        return 0, 0
    channel.close()
    return messages, consumers


def drain(broker: Connection, name: str) -> list[list[Any]]:
    """Take every message off a work queue; returns each task's args."""
    queue = topology.WORK_QUEUES[name](broker)
    found: list[list[Any]] = []
    while (message := queue.get(no_ack=True)) is not None:
        assert message.headers["task"] == queues.FETCH_TASK
        assert message.body is not None
        found.append(json.loads(message.body)[0])
    return found


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def fake_sec() -> Iterator[FakeSec]:
    sec = FakeSec()
    try:
        yield sec
    finally:
        sec.server.shutdown()
        sec.server.server_close()


@pytest.fixture
def redis(redis_url: str) -> Redis:
    client = Redis.from_url(redis_url)
    client.flushdb()
    return client


@pytest.fixture
def broker(rabbitmq_url: str) -> Iterator[Connection]:
    """A publisher-confirm connection to the test RabbitMQ, with the pipeline's queues emptied.

    Purged, not deleted: kombu's pooled connections remember which queues they declared, and a
    publish to a queue deleted behind their back would vanish.
    """
    with Connection(rabbitmq_url, transport_options={"confirm_publish": True}) as connection:
        for name in [*topology.WORK_QUEUES, *topology.DEAD_LETTER_QUEUES]:
            channel = connection.channel()
            try:
                channel.queue_purge(name)
            except NotFound:  # not declared yet; RabbitMQ closed the channel
                continue
            channel.close()
        yield connection


@pytest.fixture
def producer(rabbitmq_url: str) -> Celery:
    """Sends tasks by name, as the API does, with publisher confirms."""
    app = Celery("tests", broker=rabbitmq_url, set_as_current=False)
    app.conf.broker_transport_options = {"confirm_publish": True}
    return app


@pytest.fixture
def db(database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """A fresh database at head."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), "head")
    return database_url


@pytest.fixture
def start_worker(
    db: str, redis: Redis, redis_url: str, rabbitmq_url: str, fake_sec: FakeSec, tmp_path: Path
) -> Iterator[Callable[[str, str], Worker]]:
    """Starts ingest worker processes on the test services; kills them all at the end."""
    env = os.environ | {
        "DATABASE_URL": db,
        "REDIS_URL": redis_url,
        "BROKER_URL": rabbitmq_url,
        "SEC_USER_AGENT": USER_AGENT,
        "SEC_WWW_URL": fake_sec.url,
        "SEC_DATA_URL": fake_sec.url,
        "SEC_CACHE_DIR": str(tmp_path / "sec"),
        "LOG_LEVEL": "INFO",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",  # no telemetry unless a test asks for it
    }
    workers: list[Worker] = []

    def start(name: str, consume: str, **extra_env: str) -> Worker:
        log = tmp_path / f"{name}.log"
        with log.open("wb") as out:
            process = subprocess.Popen(  # noqa: S603 - this interpreter and our own script
                [sys.executable, str(RUN_WORKER), name, consume],
                env=env | {"HEALTH_PORT": str(_free_port())} | extra_env,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        workers.append(Worker(process, log))
        return workers[-1]

    try:
        yield start
    finally:
        for worker in workers:
            worker.process.kill()
            worker.process.wait()


async def add_job(engine: AsyncEngine, *, discovered: bool, cik: int = CIK) -> UUID:
    """A job over one company; `discovered` says discovery already walked every page."""
    request = {"ciks": [cik], "form_types": ["10-K", "10-Q"], "since": "2000-01-01"}
    async with engine.begin() as connection:
        job_id = await connection.scalar(
            insert(IngestJob)
            .values(idempotency_key=uuid4().hex, request=request)
            .returning(IngestJob.id)
        )
        status = ItemStatus.SUCCEEDED if discovered else ItemStatus.PENDING
        await connection.execute(
            insert(IngestJobCompany).values(job_id=job_id, cik=cik, status=status)
        )
    assert job_id is not None
    return job_id


async def add_filing(
    engine: AsyncEngine, job_id: UUID, accession: str = ACCESSION, document: str = "one-10k.htm"
) -> int:
    """A filing as discover leaves it: discovered, its job item queued."""
    async with engine.begin() as connection:
        company = insert(Company).values(cik=CIK, ticker="ONE", name="One Corp")
        await connection.execute(company.on_conflict_do_nothing())
        filing_id = await connection.scalar(
            insert(Filing)
            .values(
                accession_number=accession,
                cik=CIK,
                form_type="10-K",
                filed_on=date(2026, 2, 1),
                period_end=date(2025, 12, 31),
                primary_document=document,
            )
            .returning(Filing.id)
        )
        await connection.execute(
            insert(IngestJobItem).values(
                job_id=job_id, filing_id=filing_id, status=ItemStatus.RUNNING
            )
        )
    assert filing_id is not None
    return filing_id


async def snapshot(engine: AsyncEngine) -> dict[str, Any]:
    """Every row the pipeline writes, for exact comparisons."""
    async with engine.connect() as connection:
        items = select(IngestJobItem.status, IngestJobItem.attempts).order_by(IngestJobItem.id)
        letters = select(DeadLetter.task_name, DeadLetter.payload, DeadLetter.error)
        companies = select(IngestJobCompany.status)
        return {
            "jobs": (await connection.execute(select(IngestJob.status))).scalars().all(),
            "companies": (await connection.execute(companies)).scalars().all(),
            "items": [tuple(row) for row in await connection.execute(items)],
            "filings": (await connection.execute(select(Filing.status))).scalars().all(),
            "letters": [tuple(row) for row in await connection.execute(letters)],
        }


def sec_client(fake_sec: FakeSec, redis_url: str, cache: Path) -> SecClient:
    return SecClient(
        user_agent=USER_AGENT,
        www_url=fake_sec.url,
        data_url=fake_sec.url,
        cache_dir=cache,
        redis=Redis.from_url(redis_url),
    )


# Each process asks for REQUESTS documents of its own, so the cache never answers for SEC.
CLIENT = """
import sys
from pathlib import Path
import network_guard
from redis import Redis
from filinglens_sec_client import SecClient
network_guard.install()
url, redis_url, cache, agent, worker, requests = sys.argv[1:]
sec = SecClient(user_agent=agent, www_url=url, data_url=url, cache_dir=Path(cache),
                redis=Redis.from_url(redis_url))
for n in range(int(requests)):
    sec.document(1, f"0000000001-26-{int(worker):06d}", f"doc{n}.htm")
"""
WORKERS, REQUESTS = 20, 4


def test_twenty_workers_never_exceed_eight_sec_requests_a_second(
    fake_sec: FakeSec, redis: Redis, redis_url: str, tmp_path: Path
) -> None:
    fake_sec.default = lambda: (200, b"<html>filing</html>")
    command = [sys.executable, "-c", CLIENT, fake_sec.url, redis_url, str(tmp_path), USER_AGENT]
    processes = [  # from the repo root, where python -c finds network_guard
        subprocess.Popen([*command, str(worker), str(REQUESTS)], cwd=PYPROJECT.parent)  # noqa: S603
        for worker in range(WORKERS)
    ]
    for process in processes:
        assert process.wait(timeout=120) == 0

    arrivals = sorted(at for at, _ in fake_sec.requests)
    assert len(arrivals) == WORKERS * REQUESTS
    assert len({path.split("/")[5] for _, path in fake_sec.requests}) == WORKERS  # all took part
    assert fake_sec.agents == {USER_AGENT}
    # No second holds more than 8 requests: any 9 in a row span at least a second.
    assert min(arrivals[i + 8] - arrivals[i] for i in range(len(arrivals) - 8)) >= 1 - JITTER_S
    # And the bucket does not throttle below the limit by much once every worker is up.
    assert arrivals[-1] - arrivals[0] <= (len(arrivals) - 1) / 6


def test_a_403_cools_every_client_off_once_and_a_second_one_is_a_refusal(
    fake_sec: FakeSec,
    redis: Redis,
    redis_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(filinglens_sec_client, "COOL_OFF_S", 1)
    folder = f"/Archives/edgar/data/{CIK}/{ACCESSION.replace('-', '')}"
    fake_sec.routes[f"{folder}/refused.htm"] = lambda: (403, b"Request Rate Threshold Exceeded")
    fake_sec.routes[f"{folder}/busy.htm"] = lambda: (503, b"")
    fake_sec.routes[f"{folder}/fine.htm"] = lambda: (200, b"<html>fine</html>")
    one, two = (sec_client(fake_sec, redis_url, tmp_path / name) for name in ("one", "two"))

    with pytest.raises(RateLimitedError):  # a 403 pauses every client for one cool-off
        one.document(CIK, ACCESSION, "refused.htm")
    assert 0 < redis.pttl(COOL_OFF_KEY) <= 1000
    started = time.perf_counter()
    assert two.document(CIK, ACCESSION, "fine.htm") == b"<html>fine</html>"
    assert time.perf_counter() - started >= 0.8  # the other client waited out the cool-off

    # A success in between makes the next 403 another throttle, not a refusal.
    with pytest.raises(RateLimitedError):
        one.document(CIK, ACCESSION, "refused.htm")
    # A 403 right after that cool-off is a refusal: this request and every later one fail.
    with pytest.raises(SecRefusedError, match="Check SEC_USER_AGENT"):
        one.document(CIK, ACCESSION, "refused.htm")
    sent = len(fake_sec.requests)
    with pytest.raises(SecRefusedError):
        two.document(CIK, ACCESSION, "busy.htm")
    assert len(fake_sec.requests) == sent  # failed without reaching SEC

    redis.delete(REFUSED_KEY, STRIKE_KEY)  # what a worker restart does
    assert two.document(CIK, ACCESSION, "fine.htm") == b"<html>fine</html>"
    assert fake_sec.hits(f"{folder}/fine.htm") == 1  # the second read came from the cache
    with pytest.raises(UpstreamError):  # transient: the task retries
        one.document(CIK, ACCESSION, "busy.htm")
    with pytest.raises(NotFoundError):  # permanent: straight to the dead-letter queue
        one.document(CIK, ACCESSION, "missing.htm")


def test_a_filing_failing_every_attempt_lands_in_fetch_dlq_and_dead_letters_then_replays(
    db: str,
    fake_sec: FakeSec,
    broker: Connection,
    producer: Celery,
    start_worker: Callable[[str, str], Worker],
) -> None:
    job_id = run(db, lambda engine: add_job(engine, discovered=True))
    filing_id = run(db, lambda engine: add_filing(engine, job_id))
    fake_sec.routes[DOCUMENT] = lambda: (503, b"busy")
    worker = start_worker("dlq", TO_EMBED)
    wait_for(lambda: queue_state(broker, queues.FETCH)[1] == 1, 60, worker)

    producer.send_task(
        queues.FETCH_TASK, args=[filing_id, str(job_id)], queue=topology.WORK_QUEUES[queues.FETCH]
    )
    wait_for(lambda: queue_state(broker, "fetch.dlq")[0] == 1, 60, worker)
    assert fake_sec.hits(DOCUMENT) == 7  # the first attempt and max_retries=6 retries
    state = run(db, snapshot)
    [(task, payload, error)] = state["letters"]
    assert (task, payload) == (queues.FETCH_TASK, {"args": [filing_id, str(job_id)], "kwargs": {}})
    assert error.startswith("UpstreamError: SEC answered 503")
    assert state["items"] == [(ItemStatus.FAILED, 7)]
    assert state["filings"] == [FilingStatus.FAILED]
    assert state["jobs"] == [JobStatus.FAILED]  # its only filing failed
    message = topology.DEAD_LETTER_QUEUES["fetch.dlq"](broker).get(no_ack=False)
    assert message is not None
    assert message.headers["task"] == queues.FETCH_TASK
    assert message.headers["x-death"][0]["reason"] == "rejected"
    message.requeue()

    # SEC recovers: the replayed message starts over with a fresh retry count and succeeds.
    fake_sec.routes[DOCUMENT] = lambda: (200, TEN_K)
    assert replay(broker, "fetch.dlq", 100) == 1
    wait_for(lambda: run(db, snapshot)["jobs"] == [JobStatus.SUCCEEDED], 60, worker)
    state = run(db, snapshot)
    assert state["items"] == [(ItemStatus.SUCCEEDED, 8)]
    assert state["filings"] == [FilingStatus.EMBEDDED]  # no facts, so no fiscal year: not indexed
    assert len(state["letters"]) == 1  # kept as history
    assert queue_state(broker, "fetch.dlq")[0] == 0


def submissions(numbers: range, filed: str, forms: tuple[str, ...]) -> dict[str, list[str]]:
    """One page of SEC's submissions JSON, column by column."""
    return {
        "accessionNumber": [f"0000000001-24-{n:06d}" for n in numbers],
        "filingDate": [filed for _ in numbers],
        "reportDate": ["2023-12-31" for _ in numbers],
        "form": [forms[n % len(forms)] for n in numbers],
        "primaryDocument": [f"doc{n}.htm" for n in numbers],
    }


def test_a_full_fetch_queue_makes_discover_back_off_without_losing_filings(
    db: str,
    rabbitmq_url: str,
    fake_sec: FakeSec,
    broker: Connection,
    producer: Celery,
    start_worker: Callable[[str, str], Worker],
) -> None:
    older, oldest = (f"CIK{CIK:010d}-submissions-00{n}.json" for n in (1, 2))
    recent = submissions(range(30), "2024-03-01", ("10-K", "10-Q", "10-Q", "10-Q"))
    eight_k = ["0000000001-24-000099", "2024-03-02", "2024-03-02", "8-K", "8k.htm"]
    for values, value in zip(recent.values(), eight_k, strict=True):
        values.append(value)  # the job wants 10-K and 10-Q only
    main = {
        "cik": f"{CIK:010d}",
        "name": "One Corp",
        "tickers": ["ONE"],
        "filings": {
            "recent": recent,
            "files": [
                {"name": older, "filingFrom": "2005-01-01", "filingTo": "2009-12-31"},
                {"name": oldest, "filingFrom": "1995-01-01", "filingTo": "1999-12-31"},
            ],
        },
    }
    fake_sec.routes[f"/submissions/CIK{CIK:010d}.json"] = lambda: (200, json.dumps(main).encode())
    page = json.dumps(submissions(range(30, 50), "2007-03-01", ("10-K", "10-Q"))).encode()
    fake_sec.routes[f"/submissions/{older}"] = lambda: (200, page)
    job_id = run(db, lambda engine: add_job(engine, discovered=False))

    # Fill the fetch queue to its limit, without confirms (fast); no worker consumes it here.
    with Connection(rabbitmq_url) as filler:
        topology.WORK_QUEUES[queues.FETCH](filler).declare()
        fill = Producer(filler)
        for _ in range(queues.FETCH_MAX_LENGTH):
            fill.publish(b"filler", exchange="", routing_key=queues.FETCH)
    wait_for(lambda: queue_state(broker, queues.FETCH)[0] == queues.FETCH_MAX_LENGTH, 30)

    worker = start_worker("discover", f"{queues.DISCOVER},{queues.FACTS}")  # no companyfacts: 404
    producer.send_task(
        queues.DISCOVER_TASK, args=[str(job_id), CIK], queue=topology.WORK_QUEUES[queues.DISCOVER]
    )
    wait_for(lambda: "fetch queue full, discover backs off" in worker.output(), 60, worker)
    assert queue_state(broker, queues.FETCH)[0] == queues.FETCH_MAX_LENGTH  # nothing got past
    assert run(db, snapshot)["items"] == [(ItemStatus.PENDING, 0)] * 30  # recorded, waiting

    broker.default_channel.queue_purge(queues.FETCH)  # the consumers catch up
    wait_for(lambda: run(db, snapshot)["companies"] == [ItemStatus.SUCCEEDED], 120, worker)
    queued = drain(broker, queues.FETCH)

    async def filing_ids(engine: AsyncEngine) -> list[int]:
        async with engine.connect() as connection:
            return list((await connection.execute(select(Filing.id).order_by(Filing.id))).scalars())

    ids = run(db, filing_ids)
    assert len(ids) == 50  # both pages; the 8-K is left out
    assert sorted(args[0] for args in queued) == ids  # each filing queued once, none lost
    assert {args[1] for args in queued} == {str(job_id)}
    assert run(db, snapshot)["items"] == [(ItemStatus.RUNNING, 0)] * 50
    assert fake_sec.hits(f"/submissions/{oldest}") == 0  # its filings predate the job's since


def test_a_killed_worker_has_its_message_redelivered_without_duplicate_rows(
    db: str,
    fake_sec: FakeSec,
    broker: Connection,
    producer: Celery,
    start_worker: Callable[[str, str], Worker],
    tmp_path: Path,
) -> None:
    job_id = run(db, lambda engine: add_job(engine, discovered=True))
    filing_id = run(db, lambda engine: add_filing(engine, job_id))
    release = threading.Event()

    def first_hangs() -> tuple[int, bytes]:
        if fake_sec.hits(DOCUMENT) == 1:
            release.wait(30)  # worker A dies while it waits for this answer
        return 200, TEN_K

    fake_sec.routes[DOCUMENT] = first_hangs
    consume = TO_EMBED
    first = start_worker("a", consume)
    wait_for(lambda: queue_state(broker, queues.FETCH)[1] == 1, 60, first)
    producer.send_task(
        queues.FETCH_TASK, args=[filing_id, str(job_id)], queue=topology.WORK_QUEUES[queues.FETCH]
    )
    wait_for(lambda: fake_sec.hits(DOCUMENT) == 1, 60, first)

    first.process.kill()  # mid-task: the message is not acked yet (acks_late)
    first.process.wait()
    release.set()
    wait_for(lambda: queue_state(broker, queues.FETCH) == (1, 0), 30)  # back in the queue
    second = start_worker("b", consume)
    wait_for(lambda: run(db, snapshot)["jobs"] == [JobStatus.SUCCEEDED], 60, second)

    async def counts(engine: AsyncEngine) -> tuple[int | None, ...]:
        async with engine.connect() as connection:
            return tuple(
                [
                    await connection.scalar(select(func.count()).select_from(table))
                    for table in (Filing, IngestJobItem, IngestJobCompany, DeadLetter)
                ]
            )

    assert run(db, counts) == (1, 1, 1, 0)  # no duplicate rows, nothing dead-lettered
    state = run(db, snapshot)
    assert state["items"] == [(ItemStatus.SUCCEEDED, 1)]  # worker A's try never finished
    assert state["filings"] == [FilingStatus.EMBEDDED]
    assert fake_sec.hits(DOCUMENT) == 2
    cached = tmp_path / "sec" / f"{DOCUMENT.lstrip('/')}.gz"
    assert cached.exists()


def test_without_redis_fetch_pauses_without_contacting_sec_and_resumes_later(
    db: str,
    fake_sec: FakeSec,
    broker: Connection,
    producer: Celery,
    start_worker: Callable[..., Worker],
) -> None:
    job_id = run(db, lambda engine: add_job(engine, discovered=True))
    filing_id = run(db, lambda engine: add_filing(engine, job_id))
    fake_sec.routes[DOCUMENT] = lambda: (200, TEN_K)
    consume = f"{queues.FETCH},{queues.FETCH_RETRY}"
    dead_redis = f"redis://127.0.0.1:{_free_port()}/0"  # nothing listens there
    paused = start_worker("no-redis", consume, REDIS_URL=dead_redis)
    wait_for(lambda: queue_state(broker, queues.FETCH)[1] == 1, 60, paused)
    producer.send_task(
        queues.FETCH_TASK, args=[filing_id, str(job_id)], queue=topology.WORK_QUEUES[queues.FETCH]
    )

    def pauses() -> int:
        return paused.output().count("SEC rate limiter unavailable, task paused")

    # More pauses than max_retries: had a pause spent a retry, the filing would be dead by now.
    wait_for(lambda: pauses() > 7, 120, paused)
    assert fake_sec.requests == []  # fail closed: nothing reached SEC
    state = run(db, snapshot)
    assert state["items"] == [(ItemStatus.RUNNING, 0)]  # pauses are no attempts
    assert state["letters"] == []
    assert queue_state(broker, "fetch.dlq")[0] == 0

    paused.process.kill()  # Redis is back: the next worker reaches it
    paused.process.wait()
    healthy = start_worker("redis", TO_EMBED)
    wait_for(lambda: run(db, snapshot)["jobs"] == [JobStatus.SUCCEEDED], 60, healthy)
    assert run(db, snapshot)["items"] == [(ItemStatus.SUCCEEDED, 1)]
    assert fake_sec.hits(DOCUMENT) == 1


def test_a_403_after_a_cool_off_fails_the_job_with_a_clear_reason(
    db: str,
    fake_sec: FakeSec,
    redis: Redis,
    broker: Connection,
    producer: Celery,
    start_worker: Callable[..., Worker],
) -> None:
    job_id = run(db, lambda engine: add_job(engine, discovered=True))
    filings = [
        run(db, lambda engine: add_filing(engine, job_id)),
        run(db, lambda engine: add_filing(engine, job_id, "0000000001-26-000002", "two.htm")),
    ]
    fake_sec.default = lambda: (403, b"Your Request Originates from an Undeclared Automated Tool")
    worker = start_worker("refused", f"{queues.FETCH},{queues.FETCH_RETRY}")
    wait_for(lambda: queue_state(broker, queues.FETCH)[1] == 1, 60, worker)
    for filing_id in filings:
        producer.send_task(
            queues.FETCH_TASK,
            args=[filing_id, str(job_id)],
            queue=topology.WORK_QUEUES[queues.FETCH],
        )

    wait_for(lambda: run(db, snapshot)["jobs"] == [JobStatus.FAILED], 60, worker)
    assert len(fake_sec.requests) == 2  # the 403 that cooled off, the 403 after it; then none
    state = run(db, snapshot)
    assert sorted(state["items"]) == [(ItemStatus.FAILED, 1), (ItemStatus.FAILED, 2)]
    assert state["filings"] == [FilingStatus.FAILED] * 2
    assert len(state["letters"]) == 2
    for _, _, error in state["letters"]:
        assert error.startswith("SecRefusedError: SEC still refuses requests after a cool-off")
        assert "Check SEC_USER_AGENT" in error
    assert redis.get(REFUSED_KEY) is not None  # later requests fail without reaching SEC


APPLE = 320193
APPLE_10K = "0000320193-25-000079"  # in the companyfacts fixture
APPLE_10Q = "0000320193-26-000001"  # made up, so companyfacts lacks it


async def job_status(engine: AsyncEngine, job_id: UUID) -> JobStatus:
    async with engine.connect() as connection:
        query = select(IngestJob.status).where(IngestJob.id == job_id)
        return (await connection.execute(query)).scalar_one()


def finished(db: str, job_id: UUID) -> Callable[[], bool]:
    """A wait_for check: the job reached a final status."""
    return lambda: run(db, lambda engine: job_status(engine, job_id)) in FINISHED


async def embedded_by(engine: AsyncEngine) -> dict[str | None, int]:
    """Chunks per model in their embedding column (head: embedding_v2), unembedded under None."""
    query = select(Chunk.embedding_v2_model, func.count()).group_by(Chunk.embedding_v2_model)
    async with engine.connect() as connection:
        return {model: n for model, n in await connection.execute(query)}


async def count(engine: AsyncEngine, table: type[Any]) -> int:
    async with engine.connect() as connection:
        return await connection.scalar(select(func.count()).select_from(table)) or 0


async def items_of(engine: AsyncEngine, job_id: UUID) -> dict[str, tuple[ItemStatus, str | None]]:
    """Each filing's item in the job: accession number -> (status, error)."""
    query = (
        select(Filing.accession_number, IngestJobItem.status, IngestJobItem.error)
        .join(Filing, Filing.id == IngestJobItem.filing_id)
        .where(IngestJobItem.job_id == job_id)
    )
    async with engine.connect() as connection:
        return {
            row.accession_number: (row.status, row.error) for row in await connection.execute(query)
        }


async def filings(engine: AsyncEngine) -> dict[str, tuple[Any, ...]]:
    """accession number -> (status, fiscal year, fiscal period, fiscal source)."""
    query = select(
        Filing.accession_number,
        Filing.status,
        Filing.fiscal_year,
        Filing.fiscal_period,
        Filing.fiscal_source,
    )
    async with engine.connect() as connection:
        return {row[0]: tuple(row[1:]) for row in await connection.execute(query)}


async def add_apple_filings(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(Company).values(cik=APPLE, ticker="AAPL", name="Apple Inc.")
        )
        rows = [
            (APPLE_10K, "10-K", date(2025, 10, 31), date(2025, 9, 27)),
            (APPLE_10Q, "10-Q", date(2026, 1, 30), date(2025, 12, 27)),
        ]
        await connection.execute(
            insert(Filing).values(
                [
                    {
                        "accession_number": accession,
                        "cik": APPLE,
                        "form_type": form,
                        "filed_on": filed,
                        "period_end": period_end,
                        "primary_document": "doc.htm",
                    }
                    for accession, form, filed, period_end in rows
                ]
            )
        )


def test_facts_load_once_and_give_each_filing_its_fiscal_period(
    db: str,
    fake_sec: FakeSec,
    broker: Connection,
    producer: Celery,
    start_worker: Callable[[str, str], Worker],
) -> None:
    facts = (FIXTURES / "aapl-companyfacts.json").read_bytes()
    fake_sec.routes[f"/api/xbrl/companyfacts/CIK{APPLE:010d}.json"] = lambda: (200, facts)
    submissions = json.dumps({"fiscalYearEnd": "0927"}).encode()
    fake_sec.routes[f"/submissions/CIK{APPLE:010d}.json"] = lambda: (200, submissions)
    run(db, add_apple_filings)
    worker = start_worker("facts", queues.FACTS)

    loaded: list[int] = []
    for _ in range(2):  # the second run must insert nothing
        job_id = run(db, lambda engine: add_job(engine, discovered=False, cik=APPLE))
        producer.send_task(
            queues.FACTS_TASK, args=[str(job_id), APPLE], queue=topology.WORK_QUEUES[queues.FACTS]
        )
        wait_for(finished(db, job_id), 60, worker)
        assert run(db, partial(job_status, job_id=job_id)) == JobStatus.SUCCEEDED
        loaded.append(run(db, partial(count, table=FinancialFact)))
    assert loaded == [28, 28]  # 29 entries, less the 8-K one without a fiscal year
    assert {accession: row[1:] for accession, row in run(db, filings).items()} == {
        APPLE_10K: (2025, "FY", FiscalSource.COMPANYFACTS),
        APPLE_10Q: (2026, "Q1", FiscalSource.PERIOD_OF_REPORT),
    }


def test_reparse_takes_todays_sections_from_the_sec_cache_and_queues_embed(
    db: str, broker: Connection, rabbitmq_url: str, tmp_path: Path
) -> None:
    """NVDA's trimmed 10-K, stored as the parser left it before Item 8 took its statements, is
    parsed again from the SEC cache alone; embed is left to its worker."""
    cache = tmp_path / "sec"
    folder = cache / "Archives" / "edgar" / "data" / str(CIK) / ACCESSION.replace("-", "")
    folder.mkdir(parents=True)
    (folder / "one-10k.htm.gz").write_bytes(
        gzip.compress((FIXTURES / "nvda-10k-2026.htm").read_bytes())
    )

    async def work(engine: AsyncEngine) -> tuple[int, list[str], list[str], FilingStatus | None]:
        filing_id = await add_filing(engine, await add_job(engine, discovered=True))
        async with engine.begin() as connection:  # an old parse: Item 15 holds the statements
            section_id = await connection.scalar(
                insert(Section)
                .values(filing_id=filing_id, item="15", title="Exhibits", char_start=0, char_end=8)
                .returning(Section.id)
            )
            row = {"id": "old", "section_id": section_id, "char_start": 0, "token_count": 3}
            await connection.execute(insert(Chunk).values(row | {"text": "Item 15."}))
            indexed = update(Filing).where(Filing.id == filing_id)
            await connection.execute(
                indexed.values(status=FilingStatus.INDEXED, fiscal_year=2026, fiscal_period="FY")
            )
        with pytest.raises(FilingLensError, match="not in the SEC cache"):
            await reparse(engine, ACCESSION, tmp_path / "empty")  # and nothing changed
        async with engine.connect() as connection:
            assert await connection.scalar(select(func.count()).select_from(Chunk)) == 1
        assert await reparse(engine, ACCESSION, cache) == filing_id
        async with engine.connect() as connection:
            query = select(Section.item).where(Section.filing_id == filing_id)
            items = (await connection.execute(query.order_by(Section.char_start))).scalars()
            chunks = (await connection.execute(select(Chunk.id))).scalars().all()
            status = await connection.scalar(select(Filing.status).where(Filing.id == filing_id))
        return filing_id, list(items), list(chunks), status

    filing_id, items, chunks, status = run(db, work)
    assert items[-3:] == ["15", "8", "16"]
    assert chunks and "old" not in chunks  # the old chunks went with their sections
    assert status == FilingStatus.PARSED  # until embed indexes it again
    queue_embed(rabbitmq_url, [filing_id])
    assert queue_state(broker, queues.EMBED) == (1, 0)


def test_an_unparseable_filing_fails_alone_and_a_rerun_downloads_no_document(
    db: str,
    fake_sec: FakeSec,
    redis: Redis,
    broker: Connection,
    producer: Celery,
    start_worker: Callable[[str, str], Worker],
) -> None:
    good, bad = "0000000001-26-000010", "0000000001-26-000011"
    recent = {
        "accessionNumber": [good, bad],
        "filingDate": ["2026-02-02", "2026-02-01"],
        "reportDate": ["2025-12-31", "2025-12-31"],
        "form": ["10-K", "10-K"],
        "primaryDocument": ["good.htm", "bad.htm"],
    }
    main = json.dumps(
        {
            "name": "One Corp",
            "tickers": ["ONE"],
            "fiscalYearEnd": "1231",
            "filings": {"recent": recent, "files": []},
        }
    ).encode()
    fake_sec.routes[f"/submissions/CIK{CIK:010d}.json"] = lambda: (200, main)
    no_items = b"<html><body><p>Exhibit 99.1</p><p>Press release.</p></body></html>"
    documents = {
        f"/Archives/edgar/data/{CIK}/{good.replace('-', '')}/good.htm": TEN_K,
        f"/Archives/edgar/data/{CIK}/{bad.replace('-', '')}/bad.htm": no_items,
    }
    for path, body in documents.items():
        fake_sec.routes[path] = lambda body=body: (200, body)
    worker = start_worker("all", f"{queues.DISCOVER},{TO_EMBED},{queues.FACTS}")

    def ingest() -> UUID:
        job_id = run(db, lambda engine: add_job(engine, discovered=False))
        producer.send_task(
            queues.DISCOVER_TASK,
            args=[str(job_id), CIK],
            queue=topology.WORK_QUEUES[queues.DISCOVER],
        )
        wait_for(finished(db, job_id), 120, worker)
        return job_id

    first = ingest()
    assert run(db, partial(job_status, job_id=first)) == JobStatus.PARTIALLY_FAILED
    items = run(db, partial(items_of, job_id=first))
    assert items[good] == (ItemStatus.SUCCEEDED, None)
    assert items[bad][0] == ItemStatus.FAILED
    assert str(items[bad][1]).startswith("ParseError: No required item found")
    state = run(db, filings)
    assert state[good] == (FilingStatus.INDEXED, 2025, "FY", FiscalSource.PERIOD_OF_REPORT)
    assert state[bad][0] == FilingStatus.FAILED
    assert run(db, partial(count, table=Section)) == 23  # the 10-K's items
    chunks = run(db, partial(count, table=Chunk))
    assert chunks > 0
    assert run(db, embedded_by) == {EMBEDDING_MODELS["embedding_v2"]: chunks}  # head's column
    assert queue_state(broker, "parse.dlq")[0] == 1

    second = ingest()  # the parsed filing is skipped; the bad one fails again from the cache
    assert run(db, partial(job_status, job_id=second)) == JobStatus.PARTIALLY_FAILED
    statuses = {status for status, _ in run(db, partial(items_of, job_id=second)).values()}
    assert statuses == {ItemStatus.SKIPPED, ItemStatus.FAILED}
    assert all(fake_sec.hits(path) == 1 for path in documents)  # no document downloaded again
    assert redis.hget(REQUESTS_KEY, "document") == b"2"
    assert run(db, partial(count, table=Chunk)) == chunks


class OtlpSink:
    """The collector's OTLP/HTTP receiver on 127.0.0.1: keeps each body by path."""

    def __init__(self) -> None:
        self.bodies: defaultdict[str, list[bytes]] = defaultdict(list)  # /v1/traces, /v1/metrics
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                sink.bodies[self.path].append(self.rfile.read(length))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                """Quiet."""

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def spans(self) -> list[Any]:
        return [
            span
            for body in list(self.bodies["/v1/traces"])
            for resource in ExportTraceServiceRequest.FromString(body).resource_spans
            for scope in resource.scope_spans
            for span in scope.spans
        ]


TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"  # the caller's trace
ADMIN_KEY = "a" * 32


def test_an_ingest_job_is_one_trace_from_the_api_through_every_task(
    db: str,
    redis_url: str,
    rabbitmq_url: str,
    fake_sec: FakeSec,
    broker: Connection,
    start_worker: Callable[..., Worker],
    monkeypatch: pytest.MonkeyPatch,
    spans: InMemorySpanExporter,
) -> None:
    sink = OtlpSink()
    recent = {
        "accessionNumber": [ACCESSION],
        "filingDate": ["2026-02-02"],
        "reportDate": ["2025-12-31"],
        "form": ["10-K"],
        "primaryDocument": ["one-10k.htm"],
    }
    main = {"name": "One Corp", "tickers": ["ONE"], "fiscalYearEnd": "1231"}
    main_body = json.dumps(main | {"filings": {"recent": recent, "files": []}}).encode()
    fake_sec.routes[f"/submissions/CIK{CIK:010d}.json"] = lambda: (200, main_body)
    fake_sec.routes[DOCUMENT] = lambda: (200, TEN_K)  # no companyfacts: a 404, so no facts
    telemetry = {"OTEL_EXPORTER_OTLP_ENDPOINT": sink.url, "OTEL_BSP_SCHEDULE_DELAY": "200"}
    worker = start_worker("all", f"{queues.DISCOVER},{TO_EMBED},{queues.FACTS}", **telemetry)
    keys = {"API_KEY": "k" * 32, "ADMIN_API_KEY": ADMIN_KEY}
    for name, value in {"REDIS_URL": redis_url, "BROKER_URL": rabbitmq_url, **keys}.items():
        monkeypatch.setenv(name, value)
    body = {"ciks": [CIK], "form_types": ["10-K"], "since": "2000-01-01"}
    headers = {"X-API-Key": ADMIN_KEY, "Idempotency-Key": uuid4().hex, "traceparent": TRACEPARENT}
    with TestClient(app) as api:  # the in-process API, on the session's in-memory providers
        accepted = api.post("/v1/ingest-jobs", json=body, headers=headers)
    assert accepted.status_code == 202
    job_id = UUID(accepted.json()["job_id"])
    wait_for(finished(db, job_id), 180, worker)
    assert run(db, partial(job_status, job_id=job_id)) == JobStatus.SUCCEEDED

    def runs() -> dict[str, Any]:
        return {s.name.removeprefix("run/"): s for s in sink.spans() if s.name.startswith("run/")}

    tasks = {"discover", "fetch", "parse", "chunk", "embed", "facts"}
    wait_for(lambda: tasks <= runs().keys(), 30, worker)
    trace_id = bytes.fromhex(TRACEPARENT.split("-")[1])
    assert {span.trace_id for span in sink.spans()} == {trace_id}  # one trace, nothing else
    [server] = [span for span in spans.get_finished_spans() if span.name == "POST /v1/ingest-jobs"]
    assert server.context is not None
    assert server.context.trace_id == int.from_bytes(trace_id)
    assert runs()["discover"].parent_span_id == server.context.span_id.to_bytes(8)
    assert any(span.name == "SEC GET document" for span in sink.spans())
    wait_for(lambda: bool(sink.bodies["/v1/metrics"]), 30, worker)  # metrics on their own path
    exported = b"".join(b for bodies in sink.bodies.values() for b in bodies)
    exported += server.to_json().encode()
    for secret in ("tests@filinglens.test", db, rabbitmq_url, ADMIN_KEY):
        assert secret.encode() not in exported
    sink.server.shutdown()
