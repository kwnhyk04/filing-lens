"""Idempotent seed: the companies FilingLens tracks, upserted by CIK."""

import asyncio

import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_core.settings import DatabaseSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Company
from filinglens_telemetry import configure_logging

COMPANIES = [
    {"cik": 320193, "ticker": "AAPL", "name": "Apple Inc."},
    {"cik": 789019, "ticker": "MSFT", "name": "Microsoft Corporation"},
    {"cik": 1018724, "ticker": "AMZN", "name": "Amazon.com, Inc."},
    {"cik": 1652044, "ticker": "GOOGL", "name": "Alphabet Inc."},
    {"cik": 1045810, "ticker": "NVDA", "name": "NVIDIA Corporation"},
    {"cik": 19617, "ticker": "JPM", "name": "JPMorgan Chase & Co."},
]


async def seed(engine: AsyncEngine) -> None:
    statement = insert(Company).values(COMPANIES)
    statement = statement.on_conflict_do_update(
        index_elements=["cik"],
        set_={"ticker": statement.excluded.ticker, "name": statement.excluded.name},
    )
    async with engine.begin() as connection:
        await connection.execute(statement)


async def main() -> None:
    settings = load_settings(DatabaseSettings)
    configure_logging("seed", settings.log_level)
    engine = make_engine(settings)
    try:
        await seed(engine)
    finally:
        await engine.dispose()
    structlog.get_logger(__name__).info("seeded companies", count=len(COMPANIES))


if __name__ == "__main__":
    asyncio.run(main())
