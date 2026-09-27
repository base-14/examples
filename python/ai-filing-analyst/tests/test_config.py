import pytest

from filing_analyst.config import PLACEHOLDER_USER_AGENT, SettingsError, get_settings


VALID_AGENT = "Example Co ops@example.com"


def test_defaults_when_only_the_user_agent_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", VALID_AGENT)
    settings = get_settings()
    assert settings.sec_user_agent == VALID_AGENT
    assert settings.analyst_model == "qwen3.5:9B"
    assert settings.ranking_model == "gemma4:e2b"
    assert settings.ollama_think is False
    assert settings.faults_enabled is False
    assert settings.sec_backoff_seconds == 600
    assert settings.call_budget > 0
    assert settings.question_timeout_seconds > 0


def test_missing_user_agent_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(SettingsError, match="SEC_USER_AGENT"):
        get_settings()


def test_placeholder_user_agent_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", PLACEHOLDER_USER_AGENT)
    with pytest.raises(SettingsError, match="SEC_USER_AGENT"):
        get_settings()


def test_user_agent_without_an_email_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Example Co")
    with pytest.raises(SettingsError, match="email"):
        get_settings()


def test_flags_and_numbers_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", VALID_AGENT)
    monkeypatch.setenv("OLLAMA_THINK", "true")
    monkeypatch.setenv("FILING_FAULTS_ENABLED", "TRUE")
    monkeypatch.setenv("SEC_BACKOFF_SECONDS", "30")
    monkeypatch.setenv("CALL_BUDGET", "7")
    settings = get_settings()
    assert settings.ollama_think is True
    assert settings.faults_enabled is True
    assert settings.sec_backoff_seconds == 30
    assert settings.call_budget == 7
