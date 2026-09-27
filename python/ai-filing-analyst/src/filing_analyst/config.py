import os
import re
from dataclasses import dataclass
from pathlib import Path


PLACEHOLDER_USER_AGENT = "Your Company Name your.email@example.com"
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    analyst_model: str
    ranking_model: str
    ollama_think: bool
    analyst_prompt_version: str | None
    ranking_prompt_version: str | None
    db_dsn: str
    fixtures_dir: Path
    sec_user_agent: str
    sec_requests_per_second: float
    sec_backoff_seconds: int
    sec_calls_per_question: int
    call_budget: int
    question_timeout_seconds: int
    question_max_chars: int
    faults_enabled: bool


def _flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() == "true"


def _sec_user_agent() -> str:
    value = os.environ.get("SEC_USER_AGENT", "").strip()
    if not value or value == PLACEHOLDER_USER_AGENT:
        raise SettingsError(
            "SEC_USER_AGENT must name you and a contact email, for example "
            "'Example Co ops@example.com'. The SEC refuses requests without one."
        )
    if not _EMAIL.search(value):
        raise SettingsError("SEC_USER_AGENT must include a contact email address.")
    return value


def get_settings() -> Settings:
    return Settings(
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        analyst_model=os.environ.get("ANALYST_MODEL", "qwen3.5:9B"),
        ranking_model=os.environ.get("RANKING_MODEL", "gemma4:e2b"),
        ollama_think=_flag("OLLAMA_THINK"),
        analyst_prompt_version=os.environ.get("ANALYST_PROMPT_VERSION") or None,
        ranking_prompt_version=os.environ.get("RANKING_PROMPT_VERSION") or None,
        db_dsn=os.environ.get("FILING_DB_DSN", "postgresql://filing:filing@localhost:5433/filing"),
        fixtures_dir=Path(os.environ.get("FIXTURES_DIR", "fixtures")),
        sec_user_agent=_sec_user_agent(),
        sec_requests_per_second=float(os.environ.get("SEC_REQUESTS_PER_SECOND", "5")),
        sec_backoff_seconds=int(os.environ.get("SEC_BACKOFF_SECONDS", "600")),
        sec_calls_per_question=int(os.environ.get("SEC_CALLS_PER_QUESTION", "4")),
        call_budget=int(os.environ.get("CALL_BUDGET", "24")),
        question_timeout_seconds=int(os.environ.get("QUESTION_TIMEOUT_SECONDS", "240")),
        question_max_chars=int(os.environ.get("QUESTION_MAX_CHARS", "500")),
        faults_enabled=_flag("FILING_FAULTS_ENABLED"),
    )
