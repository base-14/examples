"""Application configuration using Pydantic settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LLMProvider = Literal["ollama", "anthropic", "openai", "google"]
InstrumentationMode = Literal["auto", "callback", "off"]


class Settings(BaseSettings):
    """Settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ai-runbook-assistant"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/runbooks"
    )

    instrumentation_mode: InstrumentationMode = "callback"

    llm_provider: LLMProvider = "ollama"
    llm_model: str = "qwen3.5:9B"
    ollama_base_url: str = "http://localhost:11434"
    ollama_reasoning: bool = False
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    google_api_key: str = Field(default="")
    default_temperature: float = 0.0
    default_max_tokens: int = 1024

    embedding_model: str = "embeddinggemma"
    data_source_id: str = "runbooks"

    otel_enabled: bool = True
    otel_service_name: str = "ai-runbook-assistant"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    scout_environment: str = "development"

    capture_content: bool = Field(
        default=False, alias="OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
