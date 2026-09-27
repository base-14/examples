"""The two agents of one question: the analyst, and the ranking agent it calls as a tool.

Both are built per request, so their `trace_attributes` carry the question and the conversation
starts clean. One call budget and one tool result collector are shared by both.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry
from strands.models.model import Model
from strands.models.ollama import OllamaModel
from strands.types.exceptions import EventLoopException, StructuredOutputException
from strands.types.tools import ToolResultContent

from filing_analyst.answer import FilingAnswer
from filing_analyst.app_metrics import OUTCOME_ATTRIBUTE, RANKINGS, Outcome
from filing_analyst.budget import CallBudget
from filing_analyst.model_digests import UNKNOWN_DIGEST
from filing_analyst.model_faults import FaultInjectingModel, ModelFault
from filing_analyst.tools import ToolContext, analyst_tools, ranking_tools


if TYPE_CHECKING:
    from filing_analyst.prompts import Prompt
    from filing_analyst.verifier import ToolResultCollector


ANALYST_NAME = "analyst"
RANKING_NAME = "ranking"
RANKING_TOOL_NAME = "rank_among_filers"
RANKING_TOOL_DESCRIPTION = (
    "Rank the company among every SEC filer that reported a concept for one calendar year. "
    "Pass the company name, the concept (such as net_income or revenue) and the year."
)
WINDOW_SIZE = 16
PROVIDER_NAME = "ollama"
FRAMES_TOOL = "frame_values"
RANKING_UNAVAILABLE = "The ranking is unavailable because the SEC frames data could not be fetched."
OLLAMA_DEFAULT_PORT = 11434
TEMPERATURE = 0.1
TIMEOUT_GRACE_SECONDS = 2.0
ANSWER_TOOL = FilingAnswer.__name__
MODEL_FAULTS = frozenset(ModelFault)

type ModelFactory = Callable[[str], Model]

logger = logging.getLogger(__name__)


class QuestionTimedOut(Exception):
    pass


@dataclass(frozen=True)
class AgentConfig:
    analyst_model: str
    ranking_model: str
    analyst_prompt: Prompt
    ranking_prompt: Prompt
    digests: dict[str, str]
    fixture_date: str | None
    ollama_base_url: str


@dataclass(frozen=True)
class QuestionRequest:
    question_id: str
    ticker: str
    cik: int
    company_name: str
    question: str
    fault: str | None
    call_budget: int
    timeout_seconds: float


def ollama_models(host: str, think: bool) -> ModelFactory:
    def build(model_id: str) -> Model:
        return OllamaModel(
            host=host,
            model_id=model_id,
            temperature=TEMPERATURE,
            additional_args={"think": think},
        )

    return build


def _log_answer_retry(event: AfterToolCallEvent) -> None:
    if event.tool_use["name"] == ANSWER_TOOL and event.result["status"] == "error":
        detail = " ".join(block.get("text", "") for block in event.result["content"])
        logger.warning("Structured output failed validation, retrying: %s", detail[:500])


class RankingCounter(HookProvider):
    """Counts each call to the ranking agent by outcome: answered when a frame placed the
    company, not_available when none did, error when the call failed."""

    def __init__(self, collector: ToolResultCollector) -> None:
        self._collector = collector

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.count)

    def count(self, event: AfterToolCallEvent) -> None:
        if event.tool_use["name"] != RANKING_TOOL_NAME:
            return
        if event.result["status"] == "error":
            outcome = Outcome.ERROR
        elif placed_frames(self._collector):
            outcome = Outcome.ANSWERED
        else:
            outcome = Outcome.NOT_AVAILABLE
        RANKINGS.add(1, {OUTCOME_ATTRIBUTE: str(outcome)})


def frames_fetch_failed(collector: ToolResultCollector) -> bool:
    return FRAMES_TOOL in collector.failed_tools and not any(
        "frame" in result for result in collector.results
    )


def placed_frames(collector: ToolResultCollector) -> list[dict[str, Any]]:
    """The frame results of this run that placed the company."""
    return [
        result
        for result in collector.results
        if "frame" in result and result.get("value") is not None
    ]


def frame_facts(frame: dict[str, Any]) -> str:
    return (
        f"Frame {frame['frame']}, which admits {frame['admits']}: rank {frame['rank']} of "
        f"{frame['filer_count']} filers, value {frame['value']}, accession {frame['accession']}."
    )


class RankingReport(HookProvider):
    """Settles what the analyst reads from the ranking agent. A failed frames fetch replaces the
    reply with a fixed line, and a placed company gets the frame's facts appended as the tool
    returned them. The small model's wording varies and can drop the frame or the accession."""

    def __init__(self, collector: ToolResultCollector) -> None:
        self._collector = collector

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.report)

    def report(self, event: AfterToolCallEvent) -> None:
        if event.tool_use["name"] != RANKING_TOOL_NAME:
            return
        content: list[ToolResultContent]
        if frames_fetch_failed(self._collector):
            content = [{"text": RANKING_UNAVAILABLE}]
        elif placed := placed_frames(self._collector):
            content = [*event.result["content"], {"text": frame_facts(placed[-1])}]
        else:
            return
        event.result = {
            "toolUseId": event.result["toolUseId"],
            "status": event.result["status"],
            "content": content,
        }


def _attributes(
    request: QuestionRequest, config: AgentConfig, prompt: Prompt, model_id: str
) -> dict[str, str | int]:
    """Strands applies these after its own attributes, so they replace its
    `gen_ai.provider.name` of `strands-agents` and add the server it never records."""
    server = urlsplit(config.ollama_base_url)
    return {
        "gen_ai.provider.name": PROVIDER_NAME,
        "server.address": server.hostname or "",
        "server.port": server.port or OLLAMA_DEFAULT_PORT,
        "gen_ai.conversation.id": request.question_id,
        "base14.filing.question_id": request.question_id,
        "base14.filing.ticker": request.ticker,
        "base14.filing.cik": request.cik,
        "base14.filing.fixture_date": config.fixture_date or "unknown",
        "base14.prompt.version": prompt.version,
        "base14.gen_ai.model.digest": config.digests.get(model_id, UNKNOWN_DIGEST),
    }


def build_analyst(
    request: QuestionRequest,
    config: AgentConfig,
    context: ToolContext,
    collector: ToolResultCollector,
    budget: CallBudget,
    models: ModelFactory,
) -> Agent:
    ranking = Agent(
        name=RANKING_NAME,
        model=models(config.ranking_model),
        tools=list(ranking_tools(context)),
        system_prompt=config.ranking_prompt.system,
        hooks=[budget, collector],
        trace_attributes=_attributes(request, config, config.ranking_prompt, config.ranking_model),
        conversation_manager=SlidingWindowConversationManager(window_size=WINDOW_SIZE),
        callback_handler=None,
    )
    model = models(config.analyst_model)
    if request.fault in MODEL_FAULTS:
        model = FaultInjectingModel(model, ModelFault(request.fault), ANSWER_TOOL)
    analyst = Agent(
        name=ANALYST_NAME,
        model=model,
        tools=[
            *analyst_tools(context),
            ranking.as_tool(name=RANKING_TOOL_NAME, description=RANKING_TOOL_DESCRIPTION),
        ],
        structured_output_model=FilingAnswer,
        system_prompt=config.analyst_prompt.system,
        hooks=[budget, collector, RankingCounter(collector), RankingReport(collector)],
        trace_attributes=_attributes(request, config, config.analyst_prompt, config.analyst_model),
        conversation_manager=SlidingWindowConversationManager(window_size=WINDOW_SIZE),
        callback_handler=None,
    )
    analyst.add_hook(_log_answer_retry, AfterToolCallEvent)
    return analyst


async def run_question(
    request: QuestionRequest,
    config: AgentConfig,
    context: ToolContext,
    collector: ToolResultCollector,
    models: ModelFactory,
) -> FilingAnswer:
    """Run the analyst under the call budget and the wall-clock budget. The wall-clock budget
    sets Strands' cancel signal, which ends the run with a cancelled stop reason and no error
    status; this raises `QuestionTimedOut` for it. Strands reads the signal only between stream
    chunks, cycles and tools, so a model call or tool that stalls is cancelled outright after
    `TIMEOUT_GRACE_SECONDS` more. Strands wraps a failure inside its event loop
    in `EventLoopException`; the cause is raised instead, so callers map it by type."""
    budget = CallBudget(request.call_budget)
    analyst = build_analyst(request, config, context, collector, budget, models)
    prompt = f"Company: {request.company_name} ({request.ticker}).\nQuestion: {request.question}"
    cancel = threading.Event()
    timer = threading.Timer(request.timeout_seconds, cancel.set)
    timer.daemon = True
    timer.start()
    try:
        result = await asyncio.wait_for(
            analyst.invoke_async(prompt, cancel_signal=cancel),
            timeout=request.timeout_seconds + TIMEOUT_GRACE_SECONDS,
        )
    except TimeoutError:
        logger.warning(
            "Question %s stalled past its %.0f second budget",
            request.question_id,
            request.timeout_seconds,
        )
        raise QuestionTimedOut(f"no answer within {request.timeout_seconds} seconds") from None
    except EventLoopException as failure:
        if isinstance(failure.__cause__, Exception):
            raise failure.__cause__ from None
        raise
    finally:
        timer.cancel()
    if result.stop_reason == "cancelled":
        logger.warning(
            "Question %s passed its %.0f second budget after %d model and %d tool calls",
            request.question_id,
            request.timeout_seconds,
            budget.model_calls,
            budget.tool_calls,
        )
        raise QuestionTimedOut(f"no answer within {request.timeout_seconds} seconds")
    answer = result.structured_output
    if not isinstance(answer, FilingAnswer):
        raise StructuredOutputException("The analyst returned no typed answer.")
    return answer
