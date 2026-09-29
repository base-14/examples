from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from filing_analyst import health
from filing_analyst.agents import AgentConfig
from filing_analyst.api import QuestionBody, Services, answer_question, stored_facts
from filing_analyst.config import Settings, get_settings
from filing_analyst.fixtures import TICKERS_NAME, FactsCache, read_tickers
from filing_analyst.frameworks import load_framework
from filing_analyst.model_digests import read_model_digests
from filing_analyst.prompts import PROMPTS_DIR, load_prompt
from filing_analyst.sec_client import SecClient
from filing_analyst.store import PostgresStore
from filing_analyst.telemetry import configure_telemetry, instrument_fastapi_app


OLLAMA_TAGS_TIMEOUT_SECONDS = 5.0

type ServicesFactory = Callable[[Settings], Services]


def build_services(settings: Settings) -> Services:
    """Load the ticker list into Postgres, read the model digests and the prompts, and open
    the SEC client."""
    store = PostgresStore(settings.db_dsn)
    store.load_tickers(read_tickers(settings.fixtures_dir / TICKERS_NAME))
    models = [settings.analyst_model, settings.ranking_model]
    with httpx.Client(
        base_url=settings.ollama_base_url, timeout=OLLAMA_TAGS_TIMEOUT_SECONDS
    ) as ollama:
        digests = read_model_digests(ollama, models)
    return Services(
        settings=settings,
        store=store,
        cache=FactsCache(settings.fixtures_dir),
        sec=SecClient(
            settings.sec_user_agent, settings.sec_requests_per_second, settings.sec_backoff_seconds
        ),
        agents=AgentConfig(
            analyst_model=settings.analyst_model,
            ranking_model=settings.ranking_model,
            analyst_prompt=load_prompt(PROMPTS_DIR, "analyst", settings.analyst_prompt_version),
            ranking_prompt=load_prompt(PROMPTS_DIR, "ranking", settings.ranking_prompt_version),
            digests=digests,
            fixture_date=health.fixture_date(settings.fixtures_dir),
            ollama_base_url=settings.ollama_base_url,
        ),
        framework=load_framework(settings),
    )


def create_app(
    *, with_telemetry: bool = True, services: ServicesFactory = build_services
) -> FastAPI:
    """`with_telemetry=False` leaves the process-wide providers to the tests, and `services`
    lets them run the app on memory stores and scripted models."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        if with_telemetry:
            configure_telemetry()
        app.state.services = services(settings)
        yield
        app.state.services.sec.close()

    app = FastAPI(title="Filing Analyst Agent", lifespan=lifespan)

    @app.post("/questions")
    async def post_question(body: QuestionBody) -> JSONResponse:
        return await answer_question(app.state.services, body)

    @app.get("/companies/{ticker}/facts")
    async def get_facts(ticker: str, concept: Annotated[str, Query(min_length=1)]) -> JSONResponse:
        return await stored_facts(app.state.services, ticker, concept)

    @app.get("/health")
    def get_health() -> JSONResponse:
        settings: Settings = app.state.services.settings
        try:
            facts = health.count_facts(settings.db_dsn)
        except Exception as error:
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "reason": type(error).__name__},
            )
        return JSONResponse(
            content={
                "status": "ok",
                "facts": facts,
                "fixture_date": health.fixture_date(settings.fixtures_dir),
                "framework": settings.framework,
            }
        )

    if with_telemetry:
        instrument_fastapi_app(app)
    return app


app = create_app()
