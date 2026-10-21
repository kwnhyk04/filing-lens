import pytest

from filinglens_core.settings import DatabaseSettings, load_settings
from filinglens_db import make_engine


def test_engine_errors_never_quote_their_sql_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    # A logged SQL error would otherwise carry the search text or the ids it was sent with.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@127.0.0.1:1/app")
    assert make_engine(load_settings(DatabaseSettings)).sync_engine.hide_parameters
