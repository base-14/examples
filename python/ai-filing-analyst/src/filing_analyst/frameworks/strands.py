"""The filing analyst on Strands Agents.

Both agents are built per request, so their `trace_attributes` carry the question and the
conversation starts clean.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from strands import Agent, tool
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.hooks import (
    AfterToolCallEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)
from strands.models.model import Model
from strands.models.ollama import OllamaModel
from strands.types.exceptions import EventLoopException, StructuredOutputException
from strands.types.tools import ToolResultContent

from filing_analyst.agents import (
    ANALYST_NAME,
    ANSWER_FINISH_RULE,
    ANSWER_TOOL,
    MODEL_FAULTS,
    PROVIDER_NAME,
    RANKING_NAME,
    RANKING_TOOL_DESCRIPTION,
    RANKING_TOOL_NAME,
    RANKING_UNAVAILABLE,
    TEMPERATURE,
    TIMEOUT_GRACE_SECONDS,
    AgentConfig,
    BadOutput,
    QuestionRequest,
    QuestionTimedOut,
    agent_attributes,
    analyst_instructions,
    count_ranking,
    frame_facts,
    frames_fetch_failed,
    placed_frames,
    question_attributes,
    question_prompt,
    server_attributes,
)
from filing_analyst.answer import FilingAnswer
from filing_analyst.budget import BUDGET_ERROR_TYPE, CallBudget
from filing_analyst.frameworks.strands_faults import FaultInjectingModel
from filing_analyst.model_faults import ModelFault
from filing_analyst.telemetry import ERROR_TYPE_ATTRIBUTE
from filing_analyst.tools import BoundTool, bound_tools


if TYPE_CHECKING:
    from filing_analyst.config import Settings
    from filing_analyst.prompts import Prompt
    from filing_analyst.tools import ToolContext
    from filing_analyst.verifier import ToolResultCollector


WINDOW_SIZE = 16
FINISH_RULE = ANSWER_FINISH_RULE

type ModelFactory = Callable[[str], Model]

logger = logging.getLogger(__name__)


def ollama_models(host: str, think: bool) -> ModelFactory:
    def build(model_id: str) -> Model:
        return OllamaModel(
            host=host,
            model_id=model_id,
            temperature=TEMPERATURE,
            additional_args={"think": think},
        )

    return build


def strands_tools(tools: list[BoundTool]) -> list[Any]:
    return [tool(name=bound.__name__)(bound) for bound in tools]


def _log_answer_retry(event: AfterToolCallEvent) -> None:
    if event.tool_use["name"] == ANSWER_TOOL and event.result["status"] == "error":
        detail = " ".join(block.get("text", "") for block in event.result["content"])
        logger.warning("Structured output failed validation, retrying: %s", detail[:500])


class BudgetHook(HookProvider):
    """Strands' native `limits` count one agent and end the run without error status. A tool
    call past the budget is cancelled rather than raised, because Strands never ends the
    `execute_tool` span when a tool hook raises."""

    def __init__(self, budget: CallBudget) -> None:
        self._budget = budget

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeModelCallEvent, self._on_model_call)
        registry.add_callback(BeforeToolCallEvent, self._on_tool_call)

    def _on_model_call(self, event: BeforeModelCallEvent) -> None:
        self._budget.count_model()

    def _on_tool_call(self, event: BeforeToolCallEvent) -> None:
        exceeded = self._budget.count_tool()
        if exceeded is not None:
            trace.get_current_span().set_attribute(ERROR_TYPE_ATTRIBUTE, BUDGET_ERROR_TYPE)
            event.cancel_tool = str(exceeded)


class RankingHook(HookProvider):
    """Counts each ranking call and settles what the analyst reads from the ranking agent."""

    def __init__(self, collector: ToolResultCollector) -> None:
        self._collector = collector

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.report)

    def report(self, event: AfterToolCallEvent) -> None:
        if event.tool_use["name"] != RANKING_TOOL_NAME:
            return
        count_ranking(self._collector, failed=event.result["status"] == "error")
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
    return {
        "gen_ai.provider.name": PROVIDER_NAME,
        **server_attributes(config),
        **question_attributes(request, config),
        **agent_attributes(config, prompt, model_id),
    }


def build_analyst(
    request: QuestionRequest,
    config: AgentConfig,
    context: ToolContext,
    collector: ToolResultCollector,
    budget: CallBudget,
    models: ModelFactory,
) -> Agent:
    tools = bound_tools(context, collector)
    budget_hook = BudgetHook(budget)
    ranking = Agent(
        name=RANKING_NAME,
        model=models(config.ranking_model),
        tools=strands_tools(tools.ranking),
        system_prompt=config.ranking_prompt.system,
        hooks=[budget_hook],
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
            *strands_tools(tools.analyst),
            ranking.as_tool(name=RANKING_TOOL_NAME, description=RANKING_TOOL_DESCRIPTION),
        ],
        structured_output_model=FilingAnswer,
        system_prompt=analyst_instructions(config, FINISH_RULE),
        hooks=[budget_hook, RankingHook(collector)],
        trace_attributes=_attributes(request, config, config.analyst_prompt, config.analyst_model),
        conversation_manager=SlidingWindowConversationManager(window_size=WINDOW_SIZE),
        callback_handler=None,
    )
    analyst.add_hook(_log_answer_retry, AfterToolCallEvent)
    return analyst


class StrandsFramework:
    name = "strands"

    def __init__(self, models: ModelFactory) -> None:
        self._models = models

    async def run(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
    ) -> FilingAnswer:
        """Run the analyst under the call budget and the wall-clock budget. The wall-clock
        budget sets Strands' cancel signal, which ends the run with a cancelled stop reason and
        no error status; this raises `QuestionTimedOut` for it. Strands reads the signal only
        between stream chunks, cycles and tools, so a model call or tool that stalls is
        cancelled outright after `TIMEOUT_GRACE_SECONDS` more. Strands wraps a failure inside
        its event loop in `EventLoopException`; the cause is raised instead, so callers map it
        by type."""
        budget = CallBudget(request.call_budget)
        analyst = build_analyst(request, config, context, collector, budget, self._models)
        cancel = threading.Event()
        timer = threading.Timer(request.timeout_seconds, cancel.set)
        timer.daemon = True
        timer.start()
        try:
            result = await asyncio.wait_for(
                analyst.invoke_async(question_prompt(request), cancel_signal=cancel),
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
            if isinstance(failure.__cause__, StructuredOutputException):
                raise BadOutput(str(failure.__cause__)) from failure.__cause__
            if isinstance(failure.__cause__, Exception):
                raise failure.__cause__ from None
            raise
        except StructuredOutputException as failure:
            raise BadOutput(str(failure)) from failure
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
            raise BadOutput("The analyst returned no typed answer.")
        return answer


def from_settings(settings: Settings) -> StrandsFramework:
    return StrandsFramework(ollama_models(settings.ollama_base_url, settings.ollama_think))
