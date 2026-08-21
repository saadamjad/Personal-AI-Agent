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
