"""Alembic environment: DATABASE_URL comes from the environment; migrations run over asyncpg."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from filinglens_core.settings import DatabaseSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Base
from filinglens_telemetry import configure_logging

settings = load_settings(DatabaseSettings)
configure_logging("migrations", settings.log_level)


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    engine = make_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


asyncio.run(main())
