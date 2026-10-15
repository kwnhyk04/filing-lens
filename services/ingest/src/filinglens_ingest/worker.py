"""Celery app for the ingestion pipeline, plus /healthz and /readyz probes on HEALTH_PORT."""

import asyncio
import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import structlog
from celery import Celery
from celery.signals import setup_logging, worker_init, worker_ready
from redis import Redis

from filinglens_core import queues
from filinglens_core.settings import IngestSettings, load_settings
from filinglens_db import make_engine, ping
from filinglens_ingest import topology
from filinglens_sec_client import REFUSED_KEY, STRIKE_KEY
from filinglens_telemetry import configure_logging

CHECK_TIMEOUT_S = 2.0
log = structlog.get_logger(__name__)

settings = load_settings(IngestSettings)
app = Celery(
    "filinglens_ingest",
    broker=str(settings.broker_url.get_secret_value()),
    include=["filinglens_ingest.pipeline", "filinglens_ingest.reembed"],
)
app.conf.update(
    task_acks_late=True,  # ack after the task finishes, so a crashed worker's task is redelivered
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    task_soft_time_limit=300,
    task_time_limit=330,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    broker_connection_retry_on_startup=True,
    # RabbitMQ 4 refuses transient non-exclusive queues, which Celery uses for control and gossip.
    control_queue_exclusive=True,
    event_queue_exclusive=True,
    task_queues=list(topology.WORK_QUEUES.values()),  # consumed by workers; the DLQs never are
    task_routes={
        queues.DISCOVER_TASK: {"queue": queues.DISCOVER},
        queues.FETCH_TASK: {"queue": queues.FETCH},
        queues.PARSE_TASK: {"queue": queues.PARSE},
        queues.CHUNK_TASK: {"queue": queues.CHUNK},
        queues.FACTS_TASK: {"queue": queues.FACTS},
        queues.EMBED_TASK: {"queue": queues.EMBED},
        queues.REEMBED_TASK: {"queue": queues.REEMBED},
    },
    # Publisher confirms: RabbitMQ nacks a publish to a full queue instead of dropping it.
    broker_transport_options={"confirm_publish": True},
)


@worker_ready.connect
def clear_sec_refusal(**_: Any) -> None:
    """A restart may bring a fixed SEC_USER_AGENT, so SEC gets another chance."""
    url = str(settings.redis_url.get_secret_value())
    timeouts = {"socket_timeout": CHECK_TIMEOUT_S, "socket_connect_timeout": CHECK_TIMEOUT_S}
    with Redis.from_url(url, **timeouts) as client:
        client.delete(REFUSED_KEY, STRIKE_KEY)


@worker_ready.connect
def declare_dead_letter_queues(**_: Any) -> None:
    """Workers never consume the dead-letter queues, so declare them here.

    RabbitMQ drops a dead letter when no queue is bound for it.
    """
    with app.connection_for_write() as connection:
        for queue in topology.DEAD_LETTER_QUEUES.values():
            queue(connection.default_channel).declare()


@setup_logging.connect
def _setup_logging(**_: Any) -> None:
    configure_logging("ingest", settings.log_level)


def _ping_worker(worker: str) -> None:
    """Ping this worker through RabbitMQ, so a stalled consumer also reports unready."""
    with app.connection_for_write(connect_timeout=CHECK_TIMEOUT_S) as connection:
        if not app.control.ping([worker], timeout=CHECK_TIMEOUT_S, connection=connection):
            raise ConnectionError(f"{worker} did not answer a ping through RabbitMQ")


def _ping_redis() -> None:
    url = str(settings.redis_url.get_secret_value())
    timeouts = {"socket_timeout": CHECK_TIMEOUT_S, "socket_connect_timeout": CHECK_TIMEOUT_S}
    with Redis.from_url(url, **timeouts) as client:
        client.ping()


async def _ping_postgres() -> None:
    engine = make_engine(settings)
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            await ping(engine)
    finally:
        await engine.dispose()


def _check(name: str, probe: Callable[[], object]) -> bool:
    try:
        probe()
    except Exception as exc:
        log.warning("readiness check failed", check=name, error=repr(exc))
        return False
    return True


def readiness(worker: str) -> dict[str, bool]:
    return {
        "rabbitmq": _check("rabbitmq", lambda: _ping_worker(worker)),
        "redis": _check("redis", _ping_redis),
        "postgres": _check("postgres", lambda: asyncio.run(_ping_postgres())),
    }


class _Probes(BaseHTTPRequestHandler):
    worker = ""  # Celery hostname, set when the worker starts

    def do_GET(self) -> None:
        if self.path == "/healthz":
            status, body = 200, {"status": "ok"}
        elif self.path == "/readyz":
            checks = readiness(self.worker)
            ok = all(checks.values())
            status = 200 if ok else 503
            body = {"status": "ok" if ok else "unavailable", "checks": checks}
        else:
            status, body = 404, {"status": "not_found"}
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        """Probes arrive every few seconds; skip their access logs."""


@worker_init.connect
def start_probes(sender: Any, **_: Any) -> ThreadingHTTPServer:
    _Probes.worker = sender.hostname
    server = ThreadingHTTPServer(("127.0.0.1", settings.health_port), _Probes)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
