from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "production"] = "development"
    port: int = 8000

    # Identity — who the agent represents. Drives the system prompt and the
    # fallback reply shown when the LLM is unreachable/unconfigured. Change
    # these (and app/knowledge/*) to turn this into your own agent.
    agent_owner_name: str = Field(default="Saad", min_length=1)
    agent_contact_email: str | None = None

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

    # ZizkaDB observability — off by default so CI/tests need no live instance.
    zizkadb_enabled: bool = False
    zizkadb_host: str | None = None
    zizkadb_api_key: str | None = None
    zizkadb_agent: str = Field(default="personal-assistant", min_length=1, max_length=255)
    zizkadb_timeout_seconds: float = Field(default=3.0, gt=0, le=15)

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "chat_llm_provider",
        "agent_contact_email",
        "zizkadb_host",
        "zizkadb_api_key",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
        return v or None

    @field_validator("zizkadb_agent", mode="before")
    @classmethod
    def _strip_agent_name(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or "personal-assistant"
        return v

    @field_validator("zizkadb_timeout_seconds", mode="before")
    @classmethod
    def _blank_timeout_to_default(cls, v: object) -> object:
        if v is None or v == "":
            return 3.0
        return v

    @field_validator("zizkadb_host")
    @classmethod
    def _validate_zizkadb_host(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("ZIZKADB_HOST must be an http(s) URL")
        return v.rstrip("/")

    @field_validator("zizkadb_api_key")
    @classmethod
    def _validate_zizkadb_api_key(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith(("zizkadb_live_", "zizkadb_dev_", "agdb_live_", "agdb_")):
            raise ValueError(
                "ZIZKADB_API_KEY must be a ZizkaDB key (zizkadb_live_... or zizkadb_dev_...)"
            )
        return v

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

    @property
    def zizkadb_ready(self) -> bool:
        return self.zizkadb_enabled and bool(self.zizkadb_host or self.zizkadb_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
