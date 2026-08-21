from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "production"] = "development"
    port: int = 8000

    # LLM provider
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5"
    chat_llm_provider: Literal["openai", "anthropic"] | None = None

    # Safety / cost controls
    chat_max_llm_calls_per_day: int = 300
    chat_max_message_length: int = 2000
    chat_max_body_bytes: int = 8_192
    chat_flow_timeout_seconds: int = 25

    # Rate limiting
    rate_limit_per_session_per_10min: int = 20
    rate_limit_per_ip_per_10min: int = 40

    # CORS — comma-separated origins, e.g. "https://saadstack.com,http://localhost:5173"
    cors_allowed_origins: str = "http://localhost:5173"

    # Storage
    database_path: str = "./data/conversations.db"

    @field_validator("openai_api_key", "anthropic_api_key", "chat_llm_provider", mode="before")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return v or None

    @model_validator(mode="after")
    def _validate_provider_config(self) -> "Settings":
        if self.chat_llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("CHAT_LLM_PROVIDER=openai requires OPENAI_API_KEY")
        if self.chat_llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("CHAT_LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        return self

    @property
    def resolved_provider(self) -> Literal["openai", "anthropic", None]:
        if self.chat_llm_provider:
            return self.chat_llm_provider
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        return None

    @property
    def llm_configured(self) -> bool:
        return self.resolved_provider is not None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
