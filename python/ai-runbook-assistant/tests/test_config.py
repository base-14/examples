from runbook_assistant.config import Settings, get_settings


def test_defaults():
    s = Settings()
    assert s.instrumentation_mode == "callback"
    assert s.llm_provider == "ollama"
    assert s.llm_model == "qwen3.5:9B"
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_reasoning is False
    assert s.capture_content is False
    assert s.otel_exporter_otlp_endpoint == "http://localhost:4318"
    assert s.scout_environment == "development"


def test_get_settings_cached():
    assert get_settings() is get_settings()
