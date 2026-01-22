"""Application configuration using Pydantic settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LLMProvider = Literal["anthropic", "google", "openai"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "ai-sales-intelligence"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/sales_intelligence"
    )

    # LLM Provider Configuration
    llm_provider: LLMProvider = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    fallback_provider: LLMProvider = "google"
    fallback_model: str = "gemini-3-flash"

    # LLM API Keys (only the configured provider's key is required)
    anthropic_api_key: str = Field(default="")
    google_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")

    # LLM Generation Settings
    default_temperature: float = 0.7
    default_max_tokens: int = 1024

    # OpenTelemetry / Base14 Scout
    otel_service_name: str = "ai-sales-intelligence"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    scout_environment: str = "development"

    # Feature flags
    otel_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
