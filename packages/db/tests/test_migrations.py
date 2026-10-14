import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from filinglens_core.settings import DatabaseSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Company
from filinglens_db.seed import COMPANIES, seed

pytestmark = pytest.mark.integration
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"


async def seed_twice_and_count() -> int:
    engine = make_engine(load_settings(DatabaseSettings))
    try:
        await seed(engine)
        await seed(engine)
        async with engine.connect() as connection:
            return await connection.scalar(select(func.count()).select_from(Company)) or 0
    finally:
        await engine.dispose()


def test_migrations_round_trip_match_models_and_seed_is_idempotent(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(toml_file=PYPROJECT)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)  # raises if the models and the migrations disagree
    assert asyncio.run(seed_twice_and_count()) == len(COMPANIES)
