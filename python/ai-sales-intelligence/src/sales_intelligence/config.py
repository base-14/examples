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
    llm_provider: LLMProvider = "ollama"
    llm_model_capable: str = "qwen3.5:9B"
    llm_model_fast: str = "qwen3.5:9B"
    fallback_provider: LLMProvider = "ollama"
    fallback_model: str = "qwen3.5:9B"

    # Ollama (used when llm_provider=ollama or fallback_provider=ollama)
    ollama_base_url: str = "http://localhost:11434"

    # LLM API Keys (only the configured provider's key is required)
    anthropic_api_key: str = Field(default="")
    google_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")

    # LLM Generation Settings
    default_temperature: float = 0.7
    # Large enough that a reasoning model's thinking does not exhaust the budget
    # before it emits the answer.
    default_max_tokens: int = 4096

    # OpenTelemetry / Base14 Scout
    otel_service_name: str = "ai-sales-intelligence"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    scout_environment: str = "development"

    # Records prompt and completion content on the GenAI inference event.
    # Off by default: the content may contain PII.
    otel_instrumentation_genai_capture_message_content: bool = False

    # Feature flags
    otel_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
