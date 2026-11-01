"""Process settings, read from environment variables and validated at startup.

Each process loads only the class it needs, so the worker never sees the API key.
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AmqpDsn,
    Field,
    HttpUrl,
    PostgresDsn,
    RedisDsn,
    Secret,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Chunk embedding columns and the model behind each; a query must use its column's model.
EmbeddingColumn = Literal["embedding", "embedding_v2"]
EMBEDDING_MODELS: dict[EmbeddingColumn, str] = {
    "embedding": "BAAI/bge-small-en-v1.5",  # migration 0006 drops the column
    "embedding_v2": "BAAI/bge-base-en-v1.5",
}
EMBEDDING_DIMENSIONS: dict[EmbeddingColumn, int] = {"embedding": 384, "embedding_v2": 768}
# Cross-encoders search can rerank with; filinglens_llm.local pins their revisions.
RerankModel = Literal[
    "cross-encoder/ms-marco-TinyBERT-L-2-v2",
    "cross-encoder/ms-marco-MiniLM-L-2-v2",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
]
# LLM roles name a provider and its model id, such as groq:openai/gpt-oss-20b; every provider but
# Ollama needs its key.
PROVIDER_KEYS = {
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "nvidia": "nvidia_api_key",
    "anthropic": "anthropic_api_key",
    "ollama": None,
}
ModelRole = Annotated[str, Field(pattern=r"^(gemini|groq|openrouter|nvidia|anthropic|ollama):\S+$")]


class DatabaseSettings(BaseSettings):
    """Enough for migrations and seed scripts."""

    # Values may be secrets: errors name the field but never echo the input.
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    database_url: Secret[PostgresDsn]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


SERVICE_NAME = r"^[a-z][a-z0-9-]{0,62}$"  # OTEL_SERVICE_NAME, the Prometheus job label


class TelemetrySettings(BaseSettings):
    """Traces and metrics over OTLP/HTTP (docs/monitoring.md); no endpoint, no telemetry."""

    model_config = SettingsConfigDict(hide_input_in_errors=True)

    otel_exporter_otlp_endpoint: HttpUrl | None = None
    otel_service_name: str = Field(default="filinglens", pattern=SERVICE_NAME)

    @field_validator("otel_exporter_otlp_endpoint", mode="before")
    @classmethod
    def _empty_endpoint_is_off(cls, value: Any) -> Any:
        return value or None  # compose passes OTEL_EXPORTER_OTLP_ENDPOINT= when it is off


class ApiSettings(DatabaseSettings, TelemetrySettings):
    otel_service_name: str = Field(default="filinglens-api", pattern=SERVICE_NAME)
    redis_url: Secret[RedisDsn]
    broker_url: Secret[AmqpDsn]
    api_key: SecretStr = Field(min_length=32)
    admin_api_key: SecretStr = Field(min_length=32)  # admin routes (ingest jobs) need this one
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=4100, ge=1, le=65535)
    # Embedding column that search reads on every query; docs/migrations.md says when to flip it.
    retrieval_embedding_column: EmbeddingColumn = "embedding_v2"
    # Search reranks the fused top RERANK_CANDIDATES, each cut to RERANK_MAX_TOKENS; past the
    # timeout it keeps the fused order (degraded). Defaults: user decision, docs/memory.md.
    rerank_model: RerankModel = "cross-encoder/ms-marco-TinyBERT-L-2-v2"
    rerank_candidates: int = Field(default=50, ge=1, le=100)
    rerank_max_tokens: int = Field(default=512, ge=32, le=512)
    rerank_timeout_ms: int = Field(default=500, ge=1)
    # AI_ENABLED=true turns on model calls (off by default); the budget counts LLM tokens per UTC
    # day. Answers past LLM_MAX_INFLIGHT in progress get 503.
    ai_enabled: bool = False
    daily_ai_token_budget: int = Field(default=1_000_000, ge=0)
    # Claude's own tokens a UTC day, apart from the free models' budget: 1,500,000 costs at most
    # $0.75 (all at the output price), FilingLens's $15 share over the days to 2026-11-10.
    claude_daily_token_budget: int = Field(default=1_500_000, ge=0)
    llm_max_inflight: int = Field(default=4, ge=1)
    # How long a sign-in's answer stays in Redis for a repeat question; at most the 8-hour session.
    recent_answers_ttl_s: int = Field(default=1800, ge=60, le=28_800)
    llm_primary: ModelRole = "gemini:gemini-3.5-flash-lite"
    llm_router: ModelRole = "groq:openai/gpt-oss-20b"
    llm_fallback: ModelRole = "nvidia:openai/gpt-oss-20b"  # provisional until the key lists models
    # Answers only: tried after LLM_PRIMARY, before LLM_FALLBACK. Empty keeps the free-only chain;
    # anthropic:claude-haiku-5-5 runs on prepaid credits, skipped once they are gone and from the
    # day ANTHROPIC_CREDITS_EXPIRE (UTC).
    llm_answer_fallback: ModelRole | None = None
    # Routing only: tried after LLM_ROUTER, before LLM_FALLBACK. With Claude routing first, the
    # free router that takes over when Claude stops (production: groq:openai/gpt-oss-20b).
    llm_router_fallback: ModelRole | None = None
    anthropic_credits_expire: date = date(2026, 11, 10)
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    nvidia_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    ollama_url: HttpUrl = HttpUrl("http://127.0.0.1:11434/v1")

    @field_validator("llm_answer_fallback", "llm_router_fallback", mode="before")
    @classmethod
    def _empty_fallback_is_off(cls, value: Any) -> Any:
        return value or None  # compose passes LLM_ANSWER_FALLBACK= when it is unset

    @model_validator(mode="after")
    def _keys_for_roles(self) -> Self:
        """With AI on, every role's provider needs its key; the error names the variable. Claude
        may route and answer first, but the models behind it stay free, since its stops (credits,
        key, budget) hand every call to them."""
        for role in ("llm_router_fallback", "llm_fallback"):
            if (getattr(self, role) or "").startswith("anthropic:"):
                raise ValueError(f"{role.upper()} cannot be Claude: the chain behind it is free")
        if self.ai_enabled:
            roles = ("llm_primary", "llm_router", "llm_router_fallback", "llm_fallback")
            for role in (*roles, "llm_answer_fallback"):
                if (value := getattr(self, role)) is None:
                    continue
                key = PROVIDER_KEYS[value.partition(":")[0]]
                secret: SecretStr | None = getattr(self, key) if key else None
                if key is not None and (secret is None or not secret.get_secret_value()):
                    raise ValueError(f"{role.upper()} needs {key.upper()} while AI_ENABLED=true")
        return self

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


class IngestSettings(DatabaseSettings, TelemetrySettings):
    otel_service_name: str = Field(default="filinglens-ingest", pattern=SERVICE_NAME)
    redis_url: Secret[RedisDsn]
    broker_url: Secret[AmqpDsn]
    health_port: int = Field(default=8001, ge=1, le=65535)
    # SEC fair access wants a declared tool with a contact, such as "FilingLens jane@mail.com".
    sec_user_agent: str = Field(pattern=r"\S+@\S+\.\S+")
    sec_www_url: HttpUrl = HttpUrl("https://www.sec.gov")  # filing documents (Archives)
    sec_data_url: HttpUrl = HttpUrl("https://data.sec.gov")  # submissions JSON
    sec_cache_dir: Path = Path("/var/cache/filinglens/sec")  # raw SEC responses, gzipped
    # The column the embed stage fills; the same flag search reads (docs/migrations.md).
    retrieval_embedding_column: EmbeddingColumn = "embedding_v2"

    @field_validator("sec_user_agent")
    @classmethod
    def _real_contact(cls, value: str) -> str:
        if "@example." in value:
            raise ValueError("needs your own contact address, not the .env.example placeholder")
        return value


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
