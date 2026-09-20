from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "ai-content-quality"

    llm_provider: str = "ollama"
    llm_model: str = "qwen3.5:9B"
    llm_temperature: float = 0.3
    llm_timeout: float = 300.0
    openai_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""
    fallback_provider: str = "ollama"
    fallback_model: str = "qwen3.5:9B"
    ollama_base_url: str = "http://localhost:11434"
    ollama_context_window: int = 32768
    ollama_reasoning: bool = False

    request_timeout: float = 600.0

    review_prompt_version: str = "v1"
    improve_prompt_version: str = "v1"
    score_prompt_version: str = "v1"

    otlp_endpoint: str = "http://otel-collector:4318"
    otel_sdk_disabled: bool = False
    scout_environment: str = "development"

    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
