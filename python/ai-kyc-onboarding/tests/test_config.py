import pytest

from kyc_onboarding.config import Settings, get_settings


class TestGetSettings:
    def test_model_and_prompt_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "OLLAMA_BASE_URL",
            "EXTRACTION_MODEL",
            "ASSESSMENT_MODEL",
            "EXTRACTION_PROMPT_VERSION",
            "ASSESSMENT_PROMPT_VERSION",
            "KYC_DB_DSN",
        ):
            monkeypatch.delenv(var, raising=False)

        settings = get_settings()

        assert settings.ollama_base_url == "http://localhost:11434"
        assert settings.extraction_model == "gemma4:e2b"
        assert settings.assessment_model == "qwen3.5:9B"
        assert settings.extraction_prompt_version == "v1"
        assert settings.assessment_prompt_version == "v3"
        assert settings.kyc_db_dsn == "postgresql://temporal:temporal@localhost:5433/kyc"

    def test_model_and_prompt_settings_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.internal:11434")
        monkeypatch.setenv("EXTRACTION_MODEL", "custom-extraction-model")
        monkeypatch.setenv("ASSESSMENT_MODEL", "custom-assessment-model")
        monkeypatch.setenv("EXTRACTION_PROMPT_VERSION", "v2")
        monkeypatch.setenv("ASSESSMENT_PROMPT_VERSION", "v3")
        monkeypatch.setenv("KYC_DB_DSN", "postgresql://user:pass@db/kyc")

        settings = get_settings()

        assert settings.ollama_base_url == "http://ollama.internal:11434"
        assert settings.extraction_model == "custom-extraction-model"
        assert settings.assessment_model == "custom-assessment-model"
        assert settings.extraction_prompt_version == "v2"
        assert settings.assessment_prompt_version == "v3"
        assert settings.kyc_db_dsn == "postgresql://user:pass@db/kyc"

    def test_faults_are_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KYC_FAULTS_ENABLED", raising=False)

        assert get_settings().faults_enabled is False

    def test_faults_enabled_reads_true_case_insensitively(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KYC_FAULTS_ENABLED", "TRUE")

        assert get_settings().faults_enabled is True

    def test_deadline_and_budget_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("DOCUMENT_DEADLINE_DAYS", "REVIEW_DEADLINE_DAYS", "REQUEST_BUDGET"):
            monkeypatch.delenv(var, raising=False)

        settings = get_settings()

        assert settings.document_deadline_days == 3
        assert settings.review_deadline_days == 2
        assert settings.request_budget == 40

    def test_deadline_and_budget_settings_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DOCUMENT_DEADLINE_DAYS", "5")
        monkeypatch.setenv("REVIEW_DEADLINE_DAYS", "1")
        monkeypatch.setenv("REQUEST_BUDGET", "100")

        settings = get_settings()

        assert settings.document_deadline_days == 5
        assert settings.review_deadline_days == 1
        assert settings.request_budget == 100

    def test_settings_hold_no_service_name_endpoint_or_bind_address(self) -> None:
        fields = set(Settings.__dataclass_fields__)

        assert fields.isdisjoint(
            {"service_name", "otlp_endpoint", "host", "port", "hosted_providers_enabled"}
        )
