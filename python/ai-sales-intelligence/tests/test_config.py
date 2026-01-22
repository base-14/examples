"""Tests for configuration module."""

import os


def test_settings_defaults():
    """Test that settings have sensible defaults."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)

    from sales_intelligence.config import Settings

    settings = Settings()

    assert settings.app_name == "ai-sales-intelligence"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.llm_provider == "anthropic"
    assert settings.llm_model == "claude-sonnet-4-20250514"
    assert settings.fallback_provider == "google"
    assert settings.fallback_model == "gemini-3-flash"
    assert settings.otel_service_name == "ai-sales-intelligence"


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
