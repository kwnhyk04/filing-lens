"""Alembic environment: DATABASE_URL comes from the environment; migrations run over asyncpg."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from filinglens_core.settings import DatabaseSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Base
from filinglens_telemetry import configure_logging

LOCK_TIMEOUT = "5s"  # DDL that waits longer for a lock fails, instead of stalling queries behind it
STATEMENT_TIMEOUT_S = 3600  # concurrent index builds on a full table take minutes

settings = load_settings(DatabaseSettings)
configure_logging("migrations", settings.log_level)


def run_migrations(connection: Connection) -> None:
    # Every migration runs with lock_timeout: SET (not SET LOCAL) also covers autocommit blocks.
    connection.exec_driver_sql(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
    connection.commit()  # Alembic only manages transactions on a connection outside one
    # One transaction per revision: a failure leaves the earlier revisions applied and stamped.
    context.configure(
        connection=connection, target_metadata=Base.metadata, transaction_per_migration=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    engine = make_engine(settings, statement_timeout_s=STATEMENT_TIMEOUT_S)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


asyncio.run(main())
