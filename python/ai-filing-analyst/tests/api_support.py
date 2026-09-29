from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import FastAPI

from filing_analyst.agents import AgentConfig, Framework, QuestionRequest
from filing_analyst.api import Services
from filing_analyst.config import Settings
from filing_analyst.facts import FactRow, FactSource, parse_company_facts
from filing_analyst.prompts import load_prompt
from filing_analyst.store import Company
from tests.sec_support import FakeClock, RecordingHandler, sec_client
from tests.test_tools import FRAME
from tests.tools_support import AIRBNB, AMPLITUDE, MONDAY, WORKIVA, recorded


if TYPE_CHECKING:
    from filing_analyst.answer import FilingAnswer
    from filing_analyst.tools import ToolContext
    from filing_analyst.verifier import ToolResultCollector
    from tests.scripted_model import Scripts


PROMPTS = Path(__file__).parents[1] / "prompts"
ANALYST_MODEL = "qwen3.5:9B"
RANKING_MODEL = "gemma4:e2b"
KALTURA = 1432133
COMPANIES = {
    "WK": Company(WORKIVA, "Workiva Inc."),
    "MNDY": Company(MONDAY, "monday.com Ltd."),
    "KLTR": Company(KALTURA, "Kaltura Inc."),
    "AMPL": Company(AMPLITUDE, "Amplitude, Inc."),
    "ABNB": Company(AIRBNB, "Airbnb, Inc."),
}


class MemoryCompany:
    def __init__(self, store: MemoryStore, cik: int) -> None:
        self._store = store
        self._cik = cik

    def is_loaded(self) -> bool:
        return self._cik in self._store.rows

    def write(self, rows: Sequence[FactRow], source: FactSource) -> None:
        self._store.rows[self._cik] = list(rows)
        self._store.loads.append((self._cik, source))


class MemoryStore:
    def __init__(self, loaded: Sequence[int] = ()) -> None:
        self.rows = {cik: parse_company_facts(recorded(cik)) for cik in loaded}
        self.loads: list[tuple[int, FactSource]] = []

    def resolve_ticker(self, ticker: str) -> Company | None:
        return COMPANIES.get(ticker.strip().upper())

    def is_loaded(self, cik: int) -> bool:
        return cik in self.rows

    @contextmanager
    def locked(self, cik: int) -> Iterator[MemoryCompany]:
        yield MemoryCompany(self, cik)

    def facts(self, cik: int, taxonomy: str, concepts: Sequence[str]) -> list[FactRow]:
        return [
            row
            for row in self.rows.get(cik, [])
            if row.taxonomy == taxonomy and row.concept in concepts
        ]


class MemoryCache:
    def __init__(self, ciks: Sequence[int]) -> None:
        self._documents = {cik: recorded(cik) for cik in ciks}

    def read(self, cik: int) -> dict[str, Any] | None:
        return self._documents.get(cik)


def sec_responses(request: httpx.Request) -> httpx.Response:
    if "/frames/" in request.url.path:
        return httpx.Response(200, json=FRAME)
    if request.url.path.endswith(f"CIK{KALTURA:010d}.json"):
        return httpx.Response(200, json=recorded(AMPLITUDE))
    return httpx.Response(404)


def settings(**changes: Any) -> Settings:
    fields: dict[str, Any] = {
        "framework": "strands",
        "ollama_base_url": "http://ollama.invalid:11434",
        "analyst_model": ANALYST_MODEL,
        "ranking_model": RANKING_MODEL,
        "ollama_think": False,
        "analyst_prompt_version": None,
        "ranking_prompt_version": None,
        "db_dsn": "postgresql://unused",
        "fixtures_dir": Path("fixtures"),
        "sec_user_agent": "Example Co ops@example.com",
        "sec_requests_per_second": 5.0,
        "sec_backoff_seconds": 600,
        "sec_calls_per_question": 4,
        "call_budget": 24,
        "question_timeout_seconds": 30,
        "question_max_chars": 500,
        "faults_enabled": True,
    }
    return Settings(**{**fields, **changes})


class NoFramework:
    """For tests that never reach an agent."""

    name = "none"

    async def run(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
    ) -> FilingAnswer:
        raise AssertionError("no agent run expected")


class Rig:
    """The services an app runs on in tests: memory store and cache, a mock SEC transport on
    a fake clock, and a framework, by default Strands on scripted models."""

    def __init__(
        self,
        scripts: Scripts | None = None,
        framework: Framework | None = None,
        **setting_changes: Any,
    ) -> None:
        self.settings = settings(**setting_changes)
        self.store = MemoryStore(loaded=[WORKIVA])
        self.cache = MemoryCache([MONDAY, AIRBNB])
        self.clock = FakeClock()
        self.sec = RecordingHandler(sec_responses)
        self.scripts = scripts
        self.framework = framework

    def services(self, app_settings: Settings) -> Services:
        return Services(
            settings=self.settings,
            store=self.store,
            cache=self.cache,
            sec=sec_client(self.sec, self.clock),
            agents=AgentConfig(
                analyst_model=ANALYST_MODEL,
                ranking_model=RANKING_MODEL,
                analyst_prompt=load_prompt(PROMPTS, "analyst"),
                ranking_prompt=load_prompt(PROMPTS, "ranking"),
                digests={ANALYST_MODEL: "6488c96fa5fa", RANKING_MODEL: "7fbdbf8f5e45"},
                fixture_date="2026-09-26",
                ollama_base_url="http://ollama.test:11434",
            ),
            framework=self.framework or self._strands(),
        )

    def _strands(self) -> Framework:
        from filing_analyst.frameworks.strands import StrandsFramework
        from tests.scripted_model import Scripts

        return StrandsFramework(self.scripts or Scripts([]))

    def app(self) -> FastAPI:
        from filing_analyst import main

        return main.create_app(with_telemetry=False, services=self.services)
