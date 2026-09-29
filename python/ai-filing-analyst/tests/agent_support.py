"""Turns for scripted models, and the question and configuration the framework tests share."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filing_analyst.agents import AgentConfig, QuestionRequest
from filing_analyst.prompts import load_prompt
from tests.tools_support import WORKIVA


@dataclass(frozen=True)
class Call:
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Stall:
    """A model call that never returns and never reads the cancel signal, like a hung server."""


type Turn = Call | Say | Stall

PROMPTS = Path(__file__).parents[1] / "prompts"
ANALYST_MODEL = "qwen3.5:9B"
RANKING_MODEL = "gemma4:e2b"
NI_2019 = {
    "concept": "NetIncomeLoss",
    "value": -47479000,
    "unit": "USD",
    "fiscal_year": 2019,
    "form": "10-K",
    "accession": "0001445305-22-000041",
}
GOOD_ANSWER = {
    "answer": "Workiva reported a net loss of $47.5 million for fiscal 2019.",
    "figures": [NI_2019],
    "ratios": [],
    "caveats": [],
}
LOOKUP = Call(
    "query_facts", {"concept": "net_income", "fiscal_year_from": 2019, "fiscal_year_to": 2019}
)
FRAME_CALL = Call("frame_values", {"concept": "net_income", "year": 2024})


def config() -> AgentConfig:
    return AgentConfig(
        analyst_model=ANALYST_MODEL,
        ranking_model=RANKING_MODEL,
        analyst_prompt=load_prompt(PROMPTS, "analyst"),
        ranking_prompt=load_prompt(PROMPTS, "ranking"),
        digests={ANALYST_MODEL: "6488c96fa5fa", RANKING_MODEL: "7fbdbf8f5e45"},
        fixture_date="2026-09-26",
        ollama_base_url="http://ollama.test:11434",
    )


def request(**changes: Any) -> QuestionRequest:
    fields: dict[str, Any] = {
        "question_id": "q-test-1",
        "ticker": "WK",
        "cik": WORKIVA,
        "company_name": "WORKIVA INC",
        "question": "What was net income in fiscal 2019?",
        "fault": None,
        "call_budget": 24,
        "timeout_seconds": 30.0,
    }
    return QuestionRequest(**{**fields, **changes})
