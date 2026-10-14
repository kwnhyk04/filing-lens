"""Process settings, read from environment variables and validated at startup.

Each process loads only the class it needs, so the worker never sees the API key.
"""

from typing import Literal

from pydantic import AmqpDsn, Field, PostgresDsn, RedisDsn, Secret, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Enough for migrations and seed scripts."""

    # Values may be secrets: errors name the field but never echo the input.
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    database_url: Secret[PostgresDsn]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class ApiSettings(DatabaseSettings):
    redis_url: Secret[RedisDsn]
    broker_url: Secret[AmqpDsn]
    api_key: SecretStr = Field(min_length=32)
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=4100, ge=1, le=65535)


class IngestSettings(DatabaseSettings):
    redis_url: Secret[RedisDsn]
    broker_url: Secret[AmqpDsn]
    health_port: int = Field(default=8001, ge=1, le=65535)


def load_settings[T: BaseSettings](cls: type[T]) -> T:
    """Read settings from the environment, or exit naming each bad variable but never its value."""
    try:
        return cls()
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, error['loc'])).upper()}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False)
        )
        raise SystemExit(f"Invalid configuration: {problems}") from None
