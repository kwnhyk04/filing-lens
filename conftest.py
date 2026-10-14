"""Integration fixtures: throwaway Postgres and Redis on 127.0.0.1, using the compose images."""

import asyncio
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

COMPOSE_FILE = Path(__file__).parent / "infra" / "docker-compose.yml"


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
