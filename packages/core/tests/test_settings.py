from datetime import date

import pytest

from filinglens_core.settings import ApiSettings, IngestSettings, load_settings

VALID = {
    "DATABASE_URL": "postgresql+asyncpg://app:db-password@localhost:5433/app",
    "REDIS_URL": "redis://localhost:6380/0",
    "BROKER_URL": "amqp://app:mq-password@localhost:5672//",
    "API_KEY": "k" * 32,
    "ADMIN_API_KEY": "a" * 32,
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
        ({"ADMIN_API_KEY": None}, "ADMIN_API_KEY"),
        ({"ADMIN_API_KEY": "k" * 32}, "ADMIN_API_KEY"),  # same as API_KEY
        ({"DATABASE_URL": "mysql://app:db-password@db/app"}, "DATABASE_URL"),
        ({"RETRIEVAL_EMBEDDING_COLUMN": "embedding_v3"}, "RETRIEVAL_EMBEDDING_COLUMN"),
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


@pytest.mark.parametrize(
    ("agent", "accepted"),
    [
        (None, False),
        ("FilingLens", False),  # no contact address
        ("FilingLens Your Name you@example.com", False),  # the .env.example placeholder
        ("FilingLens Jane Doe jane.doe@mail.net", True),
    ],
)
def test_ingest_needs_a_sec_user_agent_with_a_real_contact(
    monkeypatch: pytest.MonkeyPatch, agent: str | None, accepted: bool
) -> None:
    set_env(monkeypatch, SEC_USER_AGENT=agent)
    if accepted:
        assert load_settings(IngestSettings).sec_user_agent == agent
        return
    with pytest.raises(SystemExit, match=r"^Invalid configuration: SEC_USER_AGENT: "):
        load_settings(IngestSettings)


def test_ai_is_off_by_default_and_on_needs_every_roles_key(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    assert not load_settings(ApiSettings).ai_enabled
    set_env(monkeypatch, AI_ENABLED="true", GEMINI_API_KEY="", GROQ_API_KEY="g", NVIDIA_API_KEY="n")
    with pytest.raises(SystemExit, match="LLM_PRIMARY needs GEMINI_API_KEY while AI_ENABLED=true"):
        load_settings(ApiSettings)
    set_env(
        monkeypatch, AI_ENABLED="true", GEMINI_API_KEY="k", GROQ_API_KEY="g", NVIDIA_API_KEY="n"
    )
    assert load_settings(ApiSettings).llm_fallback == "nvidia:openai/gpt-oss-20b"


def test_the_answer_fallback_is_off_by_default_and_claude_only_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    settings = load_settings(ApiSettings)
    assert settings.llm_answer_fallback is None  # the free-only chain
    assert settings.anthropic_credits_expire == date(2026, 11, 10)
    set_env(monkeypatch, LLM_ANSWER_FALLBACK="")  # what compose passes when it is unset
    assert load_settings(ApiSettings).llm_answer_fallback is None
    keys = {"AI_ENABLED": "true", "GEMINI_API_KEY": "k", "GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n"}
    set_env(monkeypatch, **keys, LLM_ANSWER_FALLBACK="anthropic:claude-haiku-5-5")
    with pytest.raises(SystemExit, match="LLM_ANSWER_FALLBACK needs ANTHROPIC_API_KEY"):
        load_settings(ApiSettings)
    set_env(monkeypatch, ANTHROPIC_API_KEY="a")
    assert load_settings(ApiSettings).llm_answer_fallback == "anthropic:claude-haiku-5-5"
    set_env(monkeypatch, LLM_ROUTER="anthropic:claude-haiku-5-5")
    with pytest.raises(SystemExit, match="LLM_ROUTER cannot be Claude"):
        load_settings(ApiSettings)
    set_env(monkeypatch, LLM_ROUTER=None, LLM_FALLBACK="anthropic:claude-haiku-5-5")
    with pytest.raises(SystemExit, match="LLM_FALLBACK cannot be Claude"):  # it also routes
        load_settings(ApiSettings)
