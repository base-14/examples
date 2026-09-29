"""What every framework's adapter shares: the question and its configuration, the ranking
report, the attributes of one question, and the errors an adapter raises.

An adapter builds two agents per question: the analyst, and the ranking agent it calls as the
`rank_among_filers` tool. One call budget and one tool result collector are shared by both.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, BeforeValidator, Field, ValidationError

from filing_analyst.answer import Figure, FilingAnswer, RatioUsed
from filing_analyst.app_metrics import OUTCOME_ATTRIBUTE, RANKINGS, Outcome
from filing_analyst.model_digests import UNKNOWN_DIGEST
from filing_analyst.model_faults import ModelFault, faulted_answer
from filing_analyst.telemetry import AgentRunAttributes


if TYPE_CHECKING:
    from filing_analyst.prompts import Prompt
    from filing_analyst.tools import ToolContext
    from filing_analyst.verifier import ToolResultCollector


ANALYST_NAME = "analyst"
RANKING_NAME = "ranking"
RANKING_TOOL_NAME = "rank_among_filers"
RANKING_TOOL_DESCRIPTION = (
    "Rank the company among every SEC filer that reported a concept for one calendar year. "
    "Pass the company name, the concept (such as net_income or revenue) and the year."
)
PROVIDER_NAME = "ollama"
FRAMES_TOOL = "frame_values"
RANKING_UNAVAILABLE = "The ranking is unavailable because the SEC frames data could not be fetched."
OLLAMA_DEFAULT_PORT = 11434
TEMPERATURE = 0.1
TIMEOUT_GRACE_SECONDS = 2.0
MODEL_FAULTS = frozenset(ModelFault)

logger = logging.getLogger(__name__)


class QuestionTimedOut(Exception):
    pass


class BadOutput(Exception):
    """The analyst ended without a typed answer that passes validation."""


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


class Framework(Protocol):
    """Runs one question and returns the typed answer. Raises `BudgetExceeded`,
    `QuestionTimedOut`, `BadOutput` or `ConnectionError` for those outcomes."""

    name: str

    async def run(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
    ) -> FilingAnswer: ...


def question_prompt(request: QuestionRequest) -> str:
    return f"Company: {request.company_name} ({request.ticker}).\nQuestion: {request.question}"


def analyst_instructions(config: AgentConfig, finish_rule: str) -> str:
    """The analyst prompt ends with the rule for returning the answer, which each framework
    words for its own answer mechanism."""
    return f"{config.analyst_prompt.system}\n- {finish_rule}"


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


def count_ranking(collector: ToolResultCollector, *, failed: bool) -> None:
    """Counts each call to the ranking agent by outcome: answered when a frame placed the
    company, not_available when none did, error when the call failed."""
    if failed:
        outcome = Outcome.ERROR
    elif placed_frames(collector):
        outcome = Outcome.ANSWERED
    else:
        outcome = Outcome.NOT_AVAILABLE
    RANKINGS.add(1, {OUTCOME_ATTRIBUTE: str(outcome)})


def settled_ranking_reply(collector: ToolResultCollector, reply: str) -> str | None:
    """What the analyst reads from the ranking agent, or None to keep its reply. A failed frames
    fetch replaces the reply with a fixed line, and a placed company gets the frame's facts
    appended as the tool returned them. The small model's wording varies and can drop the frame
    or the accession."""
    if frames_fetch_failed(collector):
        return RANKING_UNAVAILABLE
    if placed := placed_frames(collector):
        return f"{reply}\n{frame_facts(placed[-1])}"
    return None


def server_attributes(config: AgentConfig) -> dict[str, str | int]:
    server = urlsplit(config.ollama_base_url)
    return {
        "server.address": server.hostname or "",
        "server.port": server.port or OLLAMA_DEFAULT_PORT,
    }


def question_attributes(request: QuestionRequest, config: AgentConfig) -> dict[str, str | int]:
    return {
        "gen_ai.conversation.id": request.question_id,
        "base14.filing.question_id": request.question_id,
        "base14.filing.ticker": request.ticker,
        "base14.filing.cik": request.cik,
        "base14.filing.fixture_date": config.fixture_date or "unknown",
    }


def agent_attributes(config: AgentConfig, prompt: Prompt, model_id: str) -> dict[str, str | int]:
    return {
        "base14.prompt.version": prompt.version,
        "base14.gen_ai.model.digest": config.digests.get(model_id, UNKNOWN_DIGEST),
    }


def run_attributes(request: QuestionRequest, config: AgentConfig) -> AgentRunAttributes:
    analyst = {
        **agent_attributes(config, config.analyst_prompt, config.analyst_model),
        **server_attributes(config),
    }
    ranking = {
        **agent_attributes(config, config.ranking_prompt, config.ranking_model),
        **server_attributes(config),
    }
    return AgentRunAttributes(
        question=question_attributes(request, config),
        by_agent={ANALYST_NAME: analyst, RANKING_NAME: ranking},
        by_model={config.analyst_model: analyst, config.ranking_model: ranking},
    )


ANSWER_TOOL = FilingAnswer.__name__
ANSWER_FINISH_RULE = f"Finish by calling the {ANSWER_TOOL} tool."
ANSWER_REMINDER = f"You did not call the {ANSWER_TOOL} tool. Call it now with your answer."


class AnswerSink:
    """Holds the arguments of the analyst's `FilingAnswer` call, for adapters whose framework
    has no structured output that works alongside tools on Ollama."""

    def __init__(self) -> None:
        self.answer: dict[str, Any] | None = None


def _decoded_list(value: Any) -> Any:
    """Smaller models sometimes send a list argument as its JSON text, such as `"[]"`, or a
    single item on its own."""
    if not isinstance(value, str):
        return value
    if value.strip().startswith("["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return [value]


# Type aliases, so the validator survives frameworks that keep only `Field` from `Annotated`.
type FigureList = Annotated[list[Figure], BeforeValidator(_decoded_list)]
type RatioList = Annotated[list[RatioUsed], BeforeValidator(_decoded_list)]
type TextList = Annotated[list[str], BeforeValidator(_decoded_list)]


def _plain(item: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Some frameworks pass nested arguments as models, others as dicts."""
    return item.model_dump() if isinstance(item, BaseModel) else item


def answer_tool(sink: AnswerSink) -> Callable[..., str]:
    fields = FilingAnswer.model_fields

    def record(
        answer: Annotated[str, Field(description=fields["answer"].description)],
        figures: Annotated[FigureList, Field(description=fields["figures"].description)],
        ratios: Annotated[RatioList | None, Field(description=fields["ratios"].description)] = None,
        caveats: Annotated[
            TextList | None, Field(description=fields["caveats"].description)
        ] = None,
    ) -> str:
        sink.answer = {
            "answer": answer,
            "figures": [_plain(figure) for figure in figures],
            "ratios": [_plain(ratio) for ratio in ratios or []],
            "caveats": caveats or [],
        }
        return "Answer recorded."

    record.__name__ = ANSWER_TOOL
    record.__doc__ = FilingAnswer.__doc__
    return record


def typed_answer(final: str | dict[str, Any] | None, fault: str | None) -> FilingAnswer:
    """Validate the analyst's final output, after rewriting it for an injected `bad_output`
    or `ungrounded_answer` fault."""
    if not final:
        raise BadOutput("The analyst returned no typed answer.")
    try:
        answer = json.loads(final) if isinstance(final, str) else final
        injected = ModelFault(fault) if fault in MODEL_FAULTS else None
        return FilingAnswer.model_validate(faulted_answer(injected, answer))
    except (ValueError, ValidationError) as error:
        logger.warning("Structured output failed validation: %s", str(error)[:500])
        raise BadOutput(str(error)) from error
