import pytest


def _settings_env_names() -> set[str]:
    """Env var names that map to Settings fields (so unit tests can isolate
    from a developer's ambient shell, e.g. an exported SCOUT_ENVIRONMENT)."""
    from runbook_assistant.config import Settings

    names: set[str] = set()
    for name, field in Settings.model_fields.items():
        names.add(name.upper())
        alias = getattr(field, "alias", None)
        if alias:
            names.add(alias)
            names.add(alias.upper())
    return names


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    from runbook_assistant.config import Settings, get_settings

    for env_name in _settings_env_names():
        monkeypatch.delenv(env_name, raising=False)
    # ignore a local .env so unit tests assert code defaults
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anthropic_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
