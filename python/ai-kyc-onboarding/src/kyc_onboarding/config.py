import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    temporal_address: str
    temporal_task_queue: str
    ollama_base_url: str
    extraction_model: str
    assessment_model: str
    extraction_prompt_version: str
    assessment_prompt_version: str
    kyc_db_dsn: str
    faults_enabled: bool
    document_deadline_days: int
    review_deadline_days: int
    request_budget: int


def get_settings() -> Settings:
    return Settings(
        temporal_address=os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        temporal_task_queue=os.environ.get("TEMPORAL_TASK_QUEUE", "kyc-onboarding"),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        extraction_model=os.environ.get("EXTRACTION_MODEL", "gemma4:e2b"),
        assessment_model=os.environ.get("ASSESSMENT_MODEL", "qwen3.5:9B"),
        extraction_prompt_version=os.environ.get("EXTRACTION_PROMPT_VERSION", "v1"),
        assessment_prompt_version=os.environ.get("ASSESSMENT_PROMPT_VERSION", "v3"),
        kyc_db_dsn=os.environ.get(
            "KYC_DB_DSN", "postgresql://temporal:temporal@localhost:5433/kyc"
        ),
        faults_enabled=os.environ.get("KYC_FAULTS_ENABLED", "false").lower() == "true",
        document_deadline_days=int(os.environ.get("DOCUMENT_DEADLINE_DAYS", "3")),
        review_deadline_days=int(os.environ.get("REVIEW_DEADLINE_DAYS", "2")),
        request_budget=int(os.environ.get("REQUEST_BUDGET", "40")),
    )
