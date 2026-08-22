import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_openai_provider_requires_key() -> None:
    with pytest.raises(ValidationError):
        Settings(chat_llm_provider="openai", openai_api_key=None, anthropic_api_key=None)


def test_anthropic_provider_requires_key() -> None:
    with pytest.raises(ValidationError):
        Settings(chat_llm_provider="anthropic", openai_api_key=None, anthropic_api_key=None)


def test_resolved_provider_prefers_explicit_setting() -> None:
    settings = Settings(
        chat_llm_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-openai-test",
    )
    assert settings.resolved_provider == "anthropic"


def test_resolved_provider_auto_detects_openai_first() -> None:
    settings = Settings(chat_llm_provider=None, openai_api_key="sk-test", anthropic_api_key=None)
    assert settings.resolved_provider == "openai"


def test_no_provider_configured() -> None:
    settings = Settings(chat_llm_provider=None, openai_api_key=None, anthropic_api_key=None)
    assert settings.resolved_provider is None
    assert settings.llm_configured is False


def test_cors_origins_list_splits_and_strips() -> None:
    settings = Settings(
        cors_allowed_origins="https://a.com, https://b.com ,https://c.com",
        openai_api_key="sk-test",
    )
    assert settings.cors_origins_list == ["https://a.com", "https://b.com", "https://c.com"]


def test_agent_owner_name_rejects_blank() -> None:
    with pytest.raises(ValidationError):
        Settings(agent_owner_name="", openai_api_key="sk-test")


def test_agent_owner_name_accepts_custom_value() -> None:
    settings = Settings(agent_owner_name="Alex", openai_api_key="sk-test")
    assert settings.agent_owner_name == "Alex"


def test_zizkadb_ready_requires_enabled_and_host_or_key() -> None:
    assert Settings(openai_api_key="sk-test").zizkadb_ready is False
    assert Settings(openai_api_key="sk-test", zizkadb_enabled=True).zizkadb_ready is False
    assert (
        Settings(
            openai_api_key="sk-test",
            zizkadb_enabled=True,
            zizkadb_host="http://localhost:9000",
        ).zizkadb_ready
        is True
    )
    assert (
        Settings(
            openai_api_key="sk-test",
            zizkadb_enabled=True,
            zizkadb_api_key="zizkadb_live_test",
        ).zizkadb_ready
        is True
    )


def test_zizkadb_host_must_be_http_url() -> None:
    with pytest.raises(ValidationError):
        Settings(openai_api_key="sk-test", zizkadb_host="localhost:9000")


def test_zizkadb_host_rejects_slash_slash_comment_values() -> None:
    # dotenv does not treat // as a comment. A copied .env.example with
    # ZIZKADB_HOST= // note must fail closed, not start with a junk URL.
    with pytest.raises(ValidationError):
        Settings(openai_api_key="sk-test", zizkadb_host="// localhost:9000")


def test_zizkadb_api_key_must_use_known_prefix() -> None:
    with pytest.raises(ValidationError):
        Settings(openai_api_key="sk-test", zizkadb_api_key="sk-wrong")


def test_zizkadb_agent_strips_whitespace() -> None:
    settings = Settings(openai_api_key="sk-test", zizkadb_agent="  personal-assistant  ")
    assert settings.zizkadb_agent == "personal-assistant"


def test_zizkadb_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(openai_api_key="sk-test", zizkadb_timeout_seconds=0)


def test_optional_zizkadb_blanks_are_treated_as_unset() -> None:
    settings = Settings(
        openai_api_key="sk-test",
        zizkadb_host="   ",
        zizkadb_api_key="",
        zizkadb_agent="  ",
        zizkadb_timeout_seconds="",  # type: ignore[arg-type]
    )
    assert settings.zizkadb_host is None
    assert settings.zizkadb_api_key is None
    assert settings.zizkadb_agent == "personal-assistant"
    assert settings.zizkadb_timeout_seconds == 3.0
    assert settings.zizkadb_ready is False
