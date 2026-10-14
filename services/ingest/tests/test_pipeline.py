"""Ingest pipeline against real Postgres, Redis and RabbitMQ and a fake SEC server (needs Docker).

The step 4 done checks: 20 workers stay under 8 SEC requests a second, a filing that fails every
attempt lands in fetch.dlq and dead_letters (then replays), a full fetch queue makes discover back
off without losing filings, and a killed worker's message is redelivered without duplicate rows.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from amqp.exceptions import NotFound
from celery import Celery
from kombu import Connection, Producer
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import filinglens_sec_client
from filinglens_core import queues
from filinglens_core.errors import NotFoundError, RateLimitedError, UpstreamError
from filinglens_db.models import (
    Company,
    DeadLetter,
    Filing,
    FilingStatus,
    IngestJob,
    IngestJobCompany,
    IngestJobItem,
    ItemStatus,
    JobStatus,
)
from filinglens_ingest import topology
from filinglens_ingest.replay import replay
from filinglens_sec_client import COOL_OFF_KEY, SecClient

pytestmark = pytest.mark.integration
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
RUN_WORKER = Path(__file__).with_name("run_worker.py")
USER_AGENT = "FilingLens tests tests@filinglens.test"
CIK = 1
ACCESSION = "0000000001-26-000001"
DOCUMENT = f"/Archives/edgar/data/{CIK}/{ACCESSION.replace('-', '')}/one-10k.htm"
JITTER_S = 0.05  # scheduling noise between a Redis grant and the fake server's clock

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
    }
    workers: list[Worker] = []

    def start(name: str, consume: str) -> Worker:
        log = tmp_path / f"{name}.log"
        with log.open("wb") as out:
            process = subprocess.Popen(  # noqa: S603 - this interpreter and our own script
                [sys.executable, str(RUN_WORKER), name, consume],
                env=env | {"HEALTH_PORT": str(_free_port())},
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


async def add_job(engine: AsyncEngine, *, discovered: bool) -> UUID:
    """A job over company CIK; `discovered` says discovery already walked every page."""
    request = {"ciks": [CIK], "form_types": ["10-K", "10-Q"], "since": "2000-01-01"}
    async with engine.begin() as connection:
        job_id = await connection.scalar(
            insert(IngestJob)
            .values(idempotency_key=uuid4().hex, request=request)
            .returning(IngestJob.id)
        )
        status = ItemStatus.SUCCEEDED if discovered else ItemStatus.PENDING
        await connection.execute(
            insert(IngestJobCompany).values(job_id=job_id, cik=CIK, status=status)
        )
    assert job_id is not None
    return job_id


async def add_filing(engine: AsyncEngine, job_id: UUID) -> int:
    """Filing ACCESSION as discover leaves it: discovered, its job item queued."""
    async with engine.begin() as connection:
        await connection.execute(insert(Company).values(cik=CIK, ticker="ONE", name="One Corp"))
        filing_id = await connection.scalar(
            insert(Filing)
            .values(
                accession_number=ACCESSION,
                cik=CIK,
                form_type="10-K",
                filed_on=date(2026, 2, 1),
                period_end=date(2025, 12, 31),
                primary_document="one-10k.htm",
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
from redis import Redis
from filinglens_sec_client import SecClient
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
    processes = [
        subprocess.Popen([*command, str(worker), str(REQUESTS)])  # noqa: S603 - our own code
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


def test_a_throttled_request_pauses_every_client_and_responses_are_cached(
    fake_sec: FakeSec,
    redis: Redis,
    redis_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(filinglens_sec_client, "COOL_OFF_S", 1)
    folder = f"/Archives/edgar/data/{CIK}/{ACCESSION.replace('-', '')}"
    fake_sec.routes[f"{folder}/throttled.htm"] = lambda: (403, b"Request Rate Threshold Exceeded")
    fake_sec.routes[f"{folder}/busy.htm"] = lambda: (503, b"")
    fake_sec.routes[f"{folder}/fine.htm"] = lambda: (200, b"<html>fine</html>")
    one, two = (sec_client(fake_sec, redis_url, tmp_path / name) for name in ("one", "two"))

    with pytest.raises(RateLimitedError):
        one.document(CIK, ACCESSION, "throttled.htm")
    assert 0 < redis.pttl(COOL_OFF_KEY) <= 1000
    started = time.monotonic()
    assert two.document(CIK, ACCESSION, "fine.htm") == b"<html>fine</html>"
    assert time.monotonic() - started >= 0.8  # the other client waited out the cool-off

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
    worker = start_worker("dlq", f"{queues.FETCH},{queues.FETCH_RETRY}")
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
    fake_sec.routes[DOCUMENT] = lambda: (200, b"<html>10-K</html>")
    assert replay(broker, "fetch.dlq", 100) == 1
    wait_for(lambda: run(db, snapshot)["jobs"] == [JobStatus.SUCCEEDED], 60, worker)
    state = run(db, snapshot)
    assert state["items"] == [(ItemStatus.SUCCEEDED, 8)]
    assert state["filings"] == [FilingStatus.FETCHED]
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

    worker = start_worker("discover", queues.DISCOVER)
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
        return 200, b"<html>10-K</html>"

    fake_sec.routes[DOCUMENT] = first_hangs
    consume = f"{queues.FETCH},{queues.FETCH_RETRY}"
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
    assert state["items"] == [(ItemStatus.SUCCEEDED, 2)]  # attempt 1 died with worker A
    assert state["filings"] == [FilingStatus.FETCHED]
    assert fake_sec.hits(DOCUMENT) == 2
    cached = tmp_path / "sec" / f"{DOCUMENT.lstrip('/')}.gz"
    assert cached.exists()
