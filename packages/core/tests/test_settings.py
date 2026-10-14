import pytest

from filinglens_core.settings import ApiSettings, load_settings

VALID = {
    "DATABASE_URL": "postgresql+asyncpg://app:db-password@localhost:5433/app",
    "REDIS_URL": "redis://localhost:6380/0",
    "BROKER_URL": "amqp://app:mq-password@localhost:5672//",
    "API_KEY": "k" * 32,
}


def set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    for name, value in {**VALID, **overrides}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def test_loads_valid_environment_and_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    settings = load_settings(ApiSettings)
    assert settings.api_port == 4100
    assert "db-password" not in repr(settings)
    assert "mq-password" not in repr(settings)


@pytest.mark.parametrize(
    ("overrides", "variable"),
    [
        ({"API_KEY": None}, "API_KEY"),
        ({"API_KEY": "short-api-key"}, "API_KEY"),
        ({"DATABASE_URL": "mysql://app:db-password@db/app"}, "DATABASE_URL"),
    ],
)
def test_refuses_to_start_naming_the_variable_but_not_its_value(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str | None], variable: str
) -> None:
    set_env(monkeypatch, **overrides)
    with pytest.raises(SystemExit) as exc:
        load_settings(ApiSettings)
    message = str(exc.value)
    assert message.startswith(f"Invalid configuration: {variable}: ")
    assert "db-password" not in message
    assert "short-api-key" not in message
