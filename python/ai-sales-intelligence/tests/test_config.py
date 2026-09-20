"""Tests for configuration module."""

import os


def test_settings_defaults():
    """Test that settings have sensible defaults."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("LLM_MODEL_CAPABLE", None)
    os.environ.pop("LLM_MODEL_FAST", None)
    os.environ.pop("FALLBACK_PROVIDER", None)
    os.environ.pop("FALLBACK_MODEL", None)

    from sales_intelligence.config import Settings

    settings = Settings(_env_file=None)

    assert settings.app_name == "ai-sales-intelligence"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.llm_provider == "ollama"
    assert settings.llm_model_capable == "qwen3.5:9B"
    assert settings.llm_model_fast == "qwen3.5:9B"
    assert settings.fallback_provider == "ollama"
    assert settings.fallback_model == "qwen3.5:9B"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.otel_service_name == "ai-sales-intelligence"
    assert settings.otel_instrumentation_genai_capture_message_content is False


def test_settings_from_env():
    """Test that settings can be loaded from environment."""
    os.environ["APP_NAME"] = "test-app"
    os.environ["DEBUG"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"

    from sales_intelligence.config import Settings

    settings = Settings()

    assert settings.app_name == "test-app"
    assert settings.debug is True
    assert settings.log_level == "DEBUG"

    os.environ.pop("APP_NAME", None)
    os.environ.pop("DEBUG", None)
    os.environ.pop("LOG_LEVEL", None)


def test_get_settings_cached():
    """Test that get_settings returns cached instance."""
    from sales_intelligence.config import get_settings

    get_settings.cache_clear()

    settings1 = get_settings()
    settings2 = get_settings()

    assert settings1 is settings2


def test_gemini_provider_is_selected_by_its_contract_key():
    """LLM_PROVIDER uses the gateway contract key, google, not the semconv name."""
    os.environ["LLM_PROVIDER"] = "google"
    try:
        from sales_intelligence.config import Settings

        settings = Settings()
        assert settings.llm_provider == "google"
    finally:
        os.environ.pop("LLM_PROVIDER", None)


def test_content_capture_from_env():
    """OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT switches content capture on."""
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
    try:
        from sales_intelligence.config import Settings

        settings = Settings()
        assert settings.otel_instrumentation_genai_capture_message_content is True
    finally:
        os.environ.pop("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", None)


def test_ollama_base_url_from_env():
    """OLLAMA_BASE_URL env var is picked up by settings."""
    os.environ["OLLAMA_BASE_URL"] = "http://host.docker.internal:11434"
    try:
        from sales_intelligence.config import Settings

        settings = Settings()
        assert settings.ollama_base_url == "http://host.docker.internal:11434"
    finally:
        os.environ.pop("OLLAMA_BASE_URL", None)
