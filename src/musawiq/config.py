"""Application configuration loaded from the environment.

The database URL is required; every other setting has a safe development
default. Settings are cached so the application has one configuration object
per process. Tests can call ``get_settings.cache_clear()`` after changing the
environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MUSAWIQ_",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(..., min_length=1)
    app_env: str = Field(default="development", min_length=1)
    log_level: str = Field(default="INFO", min_length=1)
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        min_length=1,
    )
    ai_provider: str = Field(default="groq", min_length=1)
    groq_api_key: str | None = Field(default=None)
    groq_model: str = Field(
        default="qwen/qwen3.8-27b", min_length=1
    )
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini", min_length=1)
    sufficiency_policy_version: str = Field(default="1", min_length=1)
    sales_history_min_orders: int = Field(default=20, ge=1)
    sales_history_min_days: int = Field(default=30, ge=1)
    sales_history_stale_days: int = Field(default=90, ge=1)
    audience_stale_days: int = Field(default=180, ge=1)
    competitive_data_stale_days: int = Field(default=90, ge=1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.strip().upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(
            "MUSAWIQ_DATABASE_URL is required and must not be empty "
            "(for example postgresql+psycopg://user:pass@host:5432/db)"
        ) from exc
