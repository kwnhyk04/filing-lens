"""Repo-wide test setup: no network, JSON logs, the unit marker, and the integration fixtures.

The integration fixtures start throwaway Postgres, RabbitMQ and Redis containers on 127.0.0.1 with
the compose images (Testcontainers).
"""

import asyncio
import os
import re
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from hypothesis import settings as hypothesis_settings
from hypothesis.database import DirectoryBasedExampleDatabase
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

import network_guard
from filinglens_telemetry import configure_logging, otel

network_guard.install()  # before any test module creates a client
# Telemetry goes to memory for the whole session: a process installs its providers once, and
# configure_telemetry never runs here with an endpoint. Tests read the spans and metric changes.
SPANS = InMemorySpanExporter()
METRICS = InMemoryMetricReader()
otel.install(*otel.providers("filinglens-tests", SimpleSpanProcessor(SPANS), METRICS))
# Local models load from the Hugging Face cache (HF_HOME, filled by `make models`), never from the
# network. Set before any test imports huggingface_hub; the processes tests start inherit it.
os.environ["HF_HUB_OFFLINE"] = "1"
ROOT = Path(__file__).parent
COMPOSE_FILE = ROOT / "infra" / "docker-compose.yml"
# Failing examples replay first on the next run; the database stays in the repo's .cache (H:).
hypothesis_settings.register_profile(
    "filinglens",
    database=DirectoryBasedExampleDatabase(ROOT / ".cache" / "hypothesis"),
    deadline=None,  # timing is not a property here, and Windows timing is noisy
)
hypothesis_settings.load_profile("filinglens")


@pytest.hookimpl(tryfirst=True)  # before -m selects tests by marker
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """A test without the integration or e2e marker is a unit test (`make test` runs -m unit)."""
    for item in items:
        if not item.get_closest_marker("integration") and not item.get_closest_marker("e2e"):
            item.add_marker(pytest.mark.unit)


@pytest.fixture(autouse=True)
def _json_logs() -> None:
    """The production log format. structlog's default renderer prints tracebacks with rich, locals
    included, which took 3.8 s for one logged 500."""
    configure_logging("tests")


@pytest.fixture
def spans() -> InMemorySpanExporter:
    """The spans that end during the test."""
    SPANS.clear()
    return SPANS


def _points() -> Iterator[tuple[str, dict[str, object], float]]:
    """Every series now: its metric, its labels, and a counter's sum, a histogram's count or a
    gauge's value."""
    data = METRICS.get_metrics_data()
    for resource in data.resource_metrics if data else ():
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                for point in metric.data.data_points:
                    value = point.value if isinstance(point, NumberDataPoint) else point.count
                    yield metric.name, dict(point.attributes or {}), value


def _series() -> dict[tuple[str, str], float]:
    """Every series now, by metric name and its labels as `a=1,b=2`."""
    return {
        (name, ",".join(f"{k}={v}" for k, v in sorted(labels.items()))): value
        for name, labels, value in _points()
    }


# Label names a series may carry: small fixed sets, never an id, a question, a CIK or a key.
LABELS = {
    *(
        "outcome",
        "reason",
        "route",
        "stage",
        "phase",
        "provider",
        "model",
        "task",
        "kind",
        "status",
    ),
    *("gen_ai.provider.name", "gen_ai.request.model", "gen_ai.token.type", "error.type"),
    *("http.request.method", "http.response.status_code", "http.route"),
    *("network.protocol.version", "url.scheme"),
}


@pytest.fixture(scope="session", autouse=True)
def _labels_from_fixed_sets() -> Iterator[None]:
    """After the last test: every series any test recorded carries only LABELS."""
    yield
    found = {f"{name}: {label}" for name, labels, _ in _points() for label in labels}
    if unknown := sorted(pair for pair in found if pair.split(": ")[1] not in LABELS):
        pytest.fail(f"metric labels outside the allowlist: {unknown}")


@pytest.fixture
def metric_changes() -> Callable[[str], dict[str, float]]:
    """changes(name): how much each of the metric's series moved during the test, by labels."""
    before = _series()

    def changes(name: str) -> dict[str, float]:
        return {
            labels: value - before.get((metric, labels), 0)
            for (metric, labels), value in _series().items()
            if metric == name and value != before.get((metric, labels), 0)
        }

    return changes


def compose_image(name: str) -> str:
    match = re.search(rf"image: ({re.escape(name)}:\S+)", COMPOSE_FILE.read_text(encoding="utf-8"))
    if match is None:
        raise LookupError(f"no {name} image in infra/docker-compose.yml")
    return match.group(1)


# Testcontainers publishes on every interface; AGENTS.md wants 127.0.0.1, hence the ports override.
@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    from testcontainers.community.postgres import PostgresContainer

    container = PostgresContainer(compose_image("pgvector/pgvector"), driver="asyncpg")
    container.ports["5432"] = ("127.0.0.1", None)  # pyright: ignore[reportArgumentType]
    with container:
        yield container.get_connection_url(host="127.0.0.1")


async def _execute_outside_transaction(url: str, statement: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture
def database_url(postgres_url: str) -> Iterator[str]:
    """A new empty database on the shared container, so a test may leave it at any revision."""
    name = f"test_{uuid.uuid4().hex}"
    asyncio.run(_execute_outside_transaction(postgres_url, f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    finally:
        drop = f'DROP DATABASE "{name}" WITH (FORCE)'
        asyncio.run(_execute_outside_transaction(postgres_url, drop))


@pytest.fixture(scope="session")
def rabbitmq_url() -> Iterator[str]:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    container = (
        DockerContainer(compose_image("rabbitmq"))
        .with_env("RABBITMQ_DEFAULT_USER", "test")
        .with_env("RABBITMQ_DEFAULT_PASS", "test")
        .waiting_for(LogMessageWaitStrategy("Server startup complete"))
    )
    container.ports["5672"] = ("127.0.0.1", None)  # pyright: ignore[reportArgumentType]
    with container:
        yield f"amqp://test:test@127.0.0.1:{container.get_exposed_port(5672)}//"


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    from testcontainers.community.redis import RedisContainer

    container = RedisContainer(compose_image("redis"))
    container.ports["6379"] = ("127.0.0.1", None)  # pyright: ignore[reportArgumentType]
    with container:
        yield f"redis://127.0.0.1:{container.get_exposed_port(6379)}/0"
