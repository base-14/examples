"""The question flow behind `POST /questions`, and the stored facts behind
`GET /companies/{ticker}/facts`."""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from fastapi.responses import JSONResponse
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field

from filing_analyst.agents import (
    MODEL_FAULTS,
    RANKING_UNAVAILABLE,
    AgentConfig,
    BadOutput,
    Framework,
    QuestionRequest,
    QuestionTimedOut,
    frames_fetch_failed,
    placed_frames,
)
from filing_analyst.app_metrics import (
    OUTCOME_ATTRIBUTE,
    QUESTION_DURATION,
    QUESTIONS,
    Outcome,
)
from filing_analyst.budget import BudgetExceeded
from filing_analyst.loader import CompanyFactsCache, FactStore, LoadResult, ensure_facts
from filing_analyst.sec_client import (
    SecBackoff,
    SecClient,
    SecError,
    SecFault,
    sec_question_scope,
)
from filing_analyst.telemetry import QUESTION_ID_ATTRIBUTE, question_logging
from filing_analyst.tools import FactReader, ToolContext, query_facts
from filing_analyst.verifier import ToolResultCollector, Verdict, verify_answer


if TYPE_CHECKING:
    from filing_analyst.answer import FilingAnswer
    from filing_analyst.config import Settings
    from filing_analyst.store import Company


TICKER_ATTRIBUTE = "base14.filing.ticker"
SEC_CALLS_ATTRIBUTE = "base14.filing.sec_calls"
VERIFY_SPAN = "filing.verify_answer"
TIGHT_BUDGET_FAULT = "tight_budget"
TIGHT_BUDGET = 3
FAULTS = frozenset({*SecFault, *MODEL_FAULTS, TIGHT_BUDGET_FAULT})
MAX_TICKER_CHARS = 10

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("filing_analyst")


class QuestionStore(FactStore, FactReader, Protocol):
    def resolve_ticker(self, ticker: str) -> Company | None: ...


@dataclass(frozen=True)
class Services:
    settings: Settings
    store: QuestionStore
    cache: CompanyFactsCache
    sec: SecClient
    agents: AgentConfig
    framework: Framework


class QuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=MAX_TICKER_CHARS)
    question: str = Field(min_length=1)
    fault: str | None = None
    call_budget: int | None = Field(default=None, ge=1, le=200)
    timeout_seconds: float | None = Field(default=None, gt=0, le=3600)


class Refused(Exception):
    def __init__(self, status: int, outcome: Outcome, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.outcome = outcome
        self.reason = reason
        self.detail = detail


def _check_options(body: QuestionBody, settings: Settings) -> None:
    overrides = (body.fault, body.call_budget, body.timeout_seconds)
    if not settings.faults_enabled and any(value is not None for value in overrides):
        raise Refused(
            422,
            Outcome.REJECTED,
            "faults_disabled",
            "fault, call_budget and timeout_seconds need FILING_FAULTS_ENABLED=true.",
        )
    if body.fault is not None and body.fault not in FAULTS:
        raise Refused(
            422, Outcome.REJECTED, "unknown_fault", f"fault is one of {', '.join(sorted(FAULTS))}."
        )
    if len(body.question) > settings.question_max_chars:
        raise Refused(
            422,
            Outcome.REJECTED,
            "question_too_long",
            f"The question is limited to {settings.question_max_chars} characters.",
        )


async def _resolve(services: Services, ticker: str) -> Company:
    company = await asyncio.to_thread(services.store.resolve_ticker, ticker)
    if company is None:
        logger.warning("Unknown ticker %s", ticker)
        raise Refused(404, Outcome.REJECTED, "unknown_ticker", f"No company has ticker {ticker}.")
    return company


async def _load(services: Services, cik: int) -> LoadResult:
    try:
        return await asyncio.to_thread(
            ensure_facts, services.store, services.cache, services.sec, cik
        )
    except SecBackoff as error:
        logger.warning("SEC back-off in force; question refused for CIK %d", cik)
        raise Refused(503, Outcome.ERROR, error.reason, str(error)) from error
    except SecError as error:
        raise Refused(502, Outcome.ERROR, error.reason, str(error)) from error


def _request(
    services: Services, body: QuestionBody, question_id: str, company: Company
) -> QuestionRequest:
    settings = services.settings
    call_budget = body.call_budget or settings.call_budget
    if body.fault == TIGHT_BUDGET_FAULT:
        call_budget = TIGHT_BUDGET
    return QuestionRequest(
        question_id=question_id,
        ticker=body.ticker.strip().upper(),
        cik=company.cik,
        company_name=company.name,
        question=body.question,
        fault=body.fault,
        call_budget=call_budget,
        timeout_seconds=body.timeout_seconds or settings.question_timeout_seconds,
    )


async def _run(
    services: Services, request: QuestionRequest, collector: ToolResultCollector
) -> FilingAnswer:
    context = ToolContext(facts=services.store, sec=services.sec, cik=request.cik)
    try:
        return await services.framework.run(request, services.agents, context, collector)
    except BudgetExceeded as error:
        raise Refused(504, Outcome.BUDGET, "budget", str(error)) from error
    except QuestionTimedOut as error:
        raise Refused(504, Outcome.TIMEOUT, "timeout", str(error)) from error
    except ConnectionError as error:
        logger.error("Run failed for question %s: %s", request.question_id, error)
        raise Refused(502, Outcome.ERROR, "model_unavailable", str(error)) from error
    except BadOutput as error:
        logger.error("Run failed for question %s: %s", request.question_id, error)
        raise Refused(502, Outcome.ERROR, "bad_output", str(error)) from error
    except Exception as error:
        logger.exception("Run failed for question %s", request.question_id)
        raise Refused(502, Outcome.ERROR, "run_failed", type(error).__name__) from error


def _verify(answer: FilingAnswer, collector: ToolResultCollector) -> Verdict:
    with tracer.start_as_current_span(VERIFY_SPAN) as span:
        verdict = verify_answer(answer, collector.results)
        span.set_attribute("base14.filing.figure_count", verdict.figure_count)
        span.set_attribute("base14.filing.citations_verified", verdict.citations_verified)
        if not verdict.passed:
            span.set_attribute("base14.filing.rejection_reason", verdict.reason or "unknown")
    if not verdict.passed:
        logger.warning("Answer rejected by the verifier: %s", verdict.reason)
        raise Refused(502, Outcome.UNGROUNDED, "ungrounded", verdict.reason or "ungrounded")
    return verdict


RANKING_FIELDS = ("concept", "frame", "rank", "filer_count", "value", "accession")


def _rankings(collector: ToolResultCollector) -> list[dict[str, Any]]:
    """The frames that placed the company, as the ranking tool returned them."""
    return [
        {field: frame.get(field) for field in RANKING_FIELDS} for frame in placed_frames(collector)
    ]


def ranking_scope(frame: dict[str, Any]) -> str:
    return (
        f"The ranking is among every filer in frame {frame['frame']}, which admits "
        f"{frame['admits']}, not among industry peers."
    )


def _caveats(answer: FilingAnswer, collector: ToolResultCollector) -> list[str]:
    """What a ranking compares, and a failed frames fetch, are named in the caveats whatever
    the model wrote, so the answer does not read as a peer comparison or as data the filings
    lack."""
    caveats = list(answer.caveats)
    added = [ranking_scope(frame) for frame in placed_frames(collector)]
    if frames_fetch_failed(collector):
        added.append(RANKING_UNAVAILABLE)
    for caveat in added:
        if caveat not in caveats:
            caveats.append(caveat)
    return caveats


def _outcome(answer: FilingAnswer, collector: ToolResultCollector) -> Outcome:
    if answer.figures or answer.ratios or _rankings(collector):
        return Outcome.ANSWERED
    return Outcome.NOT_AVAILABLE


async def _answer(
    services: Services, body: QuestionBody, question_id: str, sec_calls: Callable[[], int]
) -> tuple[Outcome, dict[str, Any]]:
    _check_options(body, services.settings)
    company = await _resolve(services, body.ticker)
    loaded = await _load(services, company.cik)
    request = _request(services, body, question_id, company)
    collector = ToolResultCollector()
    answer = await _run(services, request, collector)
    verdict = _verify(answer, collector)
    outcome = _outcome(answer, collector)
    return outcome, {
        "question_id": question_id,
        "ticker": request.ticker,
        "company": company.name,
        "outcome": str(outcome),
        **answer.model_dump(mode="json"),
        "caveats": _caveats(answer, collector),
        "rankings": _rankings(collector),
        "citations_verified": verdict.citations_verified,
        "facts_source": loaded.source,
        "sec_calls": sec_calls(),
    }


async def answer_question(services: Services, body: QuestionBody) -> JSONResponse:
    """Every path sets the outcome on the server span and records the questions counter."""
    question_id = f"q-{uuid.uuid4().hex[:12]}"
    ticker = body.ticker.strip().upper()
    span = trace.get_current_span()
    span.set_attribute(QUESTION_ID_ATTRIBUTE, question_id)
    span.set_attribute(TICKER_ATTRIBUTE, ticker)
    started = time.perf_counter()
    sec_fault = body.fault if body.fault in set(SecFault) else None
    with (
        question_logging(question_id),
        sec_question_scope(services.settings.sec_calls_per_question, sec_fault) as scope,
    ):
        logger.info("Question %s received for %s", question_id, ticker)
        try:
            outcome, content = await _answer(services, body, question_id, lambda: scope.calls)
            status = 200
            logger.info(
                "Answer for question %s returned with %d figures: %s",
                question_id,
                len(content["figures"]),
                outcome,
            )
        except Refused as refused:
            outcome, status = refused.outcome, refused.status
            content = {
                "question_id": question_id,
                "outcome": str(outcome),
                "reason": refused.reason,
                "detail": refused.detail,
            }
        except Exception as error:
            logger.exception("Question %s failed", question_id)
            outcome, status = Outcome.ERROR, 500
            content = {
                "question_id": question_id,
                "outcome": str(outcome),
                "reason": "internal",
                "detail": type(error).__name__,
            }
        span.set_attribute(SEC_CALLS_ATTRIBUTE, scope.calls)
    span.set_attribute(OUTCOME_ATTRIBUTE, str(outcome))
    QUESTIONS.add(1, {OUTCOME_ATTRIBUTE: str(outcome)})
    QUESTION_DURATION.record(time.perf_counter() - started, {OUTCOME_ATTRIBUTE: str(outcome)})
    return JSONResponse(status_code=status, content=content)


def _refusal(status: int, reason: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"reason": reason, "detail": detail})


async def stored_facts(services: Services, ticker: str, concept: str) -> JSONResponse:
    company = await asyncio.to_thread(services.store.resolve_ticker, ticker)
    if company is None:
        return _refusal(404, "unknown_ticker", f"No company has ticker {ticker}.")
    if not await asyncio.to_thread(services.store.is_loaded, company.cik):
        return _refusal(
            404, "not_loaded", f"No facts are loaded for {ticker}; ask a question first."
        )
    result = await asyncio.to_thread(query_facts, services.store, company.cik, concept)
    if "error" in result:
        return _refusal(422, result["error"], result.get("detail", ""))
    return JSONResponse(
        content={
            "ticker": ticker.strip().upper(),
            "cik": company.cik,
            "company": company.name,
            **result,
        }
    )
