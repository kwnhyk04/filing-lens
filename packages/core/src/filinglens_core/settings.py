"""Process settings, read from environment variables and validated at startup.

Each process loads only the class it needs, so the worker never sees the API key.
"""

from typing import Literal

from pydantic import (
    AmqpDsn,
    Field,
    PostgresDsn,
    RedisDsn,
    Secret,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Chunk embedding columns and the model behind each; a query must use its column's model.
EmbeddingColumn = Literal["embedding", "embedding_v2"]
EMBEDDING_MODELS: dict[EmbeddingColumn, str] = {
    "embedding": "BAAI/bge-small-en-v1.5",  # migration 0006 drops the column
    "embedding_v2": "BAAI/bge-base-en-v1.5",
}
EMBEDDING_DIMENSIONS: dict[EmbeddingColumn, int] = {"embedding": 384, "embedding_v2": 768}


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
    admin_api_key: SecretStr = Field(min_length=32)  # admin routes (ingest jobs) need this one
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=4100, ge=1, le=65535)
    # Embedding column that search reads on every query; docs/migrations.md says when to flip it.
    retrieval_embedding_column: EmbeddingColumn = "embedding_v2"

    @field_validator("admin_api_key")
    @classmethod
    def _differs_from_api_key(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        api_key = info.data.get("api_key")
        if (
            isinstance(api_key, SecretStr)
            and api_key.get_secret_value() == value.get_secret_value()
        ):
            raise ValueError("must differ from API_KEY")
        return value


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
