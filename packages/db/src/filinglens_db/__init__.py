"""Async engine helpers; models, migrations and seeds live in the submodules."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from filinglens_core.settings import DatabaseSettings

CONNECT_TIMEOUT_S = 5
STATEMENT_TIMEOUT_S = 30


def make_engine(
    settings: DatabaseSettings, *, statement_timeout_s: float = STATEMENT_TIMEOUT_S
) -> AsyncEngine:
    """Async engine whose connects and statements both time out."""
    return create_async_engine(
        str(settings.database_url.get_secret_value()),
        pool_pre_ping=True,
        connect_args={"timeout": CONNECT_TIMEOUT_S, "command_timeout": statement_timeout_s},
    )


async def ping(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
