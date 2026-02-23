"""Application configuration using Pydantic settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LLMProvider = Literal["anthropic", "google", "openai", "ollama"]


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
    llm_provider: LLMProvider = "google"
    llm_model_capable: str = "gemini-2.5-pro"
    llm_model_fast: str = "gemini-2.5-flash"
    fallback_provider: LLMProvider = "anthropic"
    fallback_model: str = "claude-haiku-4-5-20251001"

    # Ollama (used when llm_provider=ollama or fallback_provider=ollama)
    ollama_base_url: str = "http://localhost:11434"

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
