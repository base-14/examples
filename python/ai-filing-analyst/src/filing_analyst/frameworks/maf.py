"""The filing analyst on Microsoft Agent Framework, with its Ollama chat client.

Chat middleware carries the shared call budget and the injected faults; function middleware
carries the tool budget and the ranking report. The analyst answers by calling a
`FilingAnswer` tool, which ends the run, rather than through the `response_format` option:
Ollama applies that option as `format` on every call, which leaves the model no way to call a
tool.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from agent_framework import (
    Agent,
    ChatContext,
    FunctionInvocationContext,
    MiddlewareTermination,
    chat_middleware,
    function_middleware,
    tool,
)
from agent_framework.observability import enable_instrumentation
from agent_framework_ollama import OllamaChatClient
from ollama import AsyncClient

from filing_analyst.agents import (
    ANALYST_NAME,
    ANSWER_FINISH_RULE,
    ANSWER_REMINDER,
    ANSWER_TOOL,
    MODEL_FAULTS,
    RANKING_NAME,
    RANKING_TOOL_DESCRIPTION,
    RANKING_TOOL_NAME,
    TEMPERATURE,
    AgentConfig,
    AnswerSink,
    QuestionRequest,
    QuestionTimedOut,
    analyst_instructions,
    answer_tool,
    count_ranking,
    question_prompt,
    run_attributes,
    settled_ranking_reply,
    typed_answer,
)
from filing_analyst.budget import CallBudget
from filing_analyst.model_faults import SLOW_MODEL_SECONDS, ModelFault, before_model_call
from filing_analyst.telemetry import CAPTURE_CONTENT_VARIABLE, agent_run_attributes
from filing_analyst.tools import BoundTool, bound_tools


if TYPE_CHECKING:
    from filing_analyst.answer import FilingAnswer
    from filing_analyst.config import Settings
    from filing_analyst.tools import ToolContext
    from filing_analyst.verifier import ToolResultCollector


FINISH_RULE = ANSWER_FINISH_RULE

type ClientFactory = Callable[[str], OllamaChatClient]
type Next = Callable[[], Awaitable[None]]

logger = logging.getLogger(__name__)


def ollama_clients(host: str, client: AsyncClient | None = None) -> ClientFactory:
    def build(model_id: str) -> OllamaChatClient:
        return OllamaChatClient(host=host, model=model_id, client=client)

    return build


def maf_tools(tools: list[BoundTool] | list[Callable[..., str]]) -> list[Any]:
    return [tool(bound, name=bound.__name__, approval_mode="never_require") for bound in tools]


def result_text(result: Any) -> str:
    """A function result is a string, or a list of content items holding the text."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "".join(str(getattr(item, "text", None) or "") for item in result)
    return str(result)


class Middleware:
    """One question's middleware, shared by both agents."""

    def __init__(
        self, budget: CallBudget, collector: ToolResultCollector, fault: ModelFault | None
    ) -> None:
        self._budget = budget
        self._collector = collector
        self._fault = fault

    def chat(self, *, analyst: bool) -> Any:
        @chat_middleware
        async def on_chat(context: ChatContext, call_next: Next) -> None:
            self._budget.count_model()
            if analyst:
                await before_model_call(self._fault, SLOW_MODEL_SECONDS)
            await call_next()

        return on_chat

    def function(self) -> Any:
        @function_middleware
        async def on_function(context: FunctionInvocationContext, call_next: Next) -> None:
            exceeded = self._budget.count_tool()
            if exceeded is not None:
                raise exceeded
            if context.function.name == ANSWER_TOOL:
                await call_next()
                raise MiddlewareTermination
            ranking = context.function.name == RANKING_TOOL_NAME
            try:
                await call_next()
            except Exception:
                if ranking:
                    count_ranking(self._collector, failed=True)
                raise
            if ranking:
                count_ranking(self._collector, failed=False)
                settled = settled_ranking_reply(self._collector, result_text(context.result))
                if settled is not None:
                    context.result = settled

        return on_function


def _connection_error(error: BaseException) -> ConnectionError | None:
    """The Ollama client wraps a refused connection in the framework's client exception."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, ConnectionError):
            return current
        if type(current).__name__ == "ConnectError":
            return ConnectionError(str(current))
        current = current.__cause__
    return None


class MafFramework:
    name = "maf"

    def __init__(self, clients: ClientFactory, think: bool) -> None:
        self._clients = clients
        self._think = think

    def build_analyst(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
        budget: CallBudget,
        sink: AnswerSink,
    ) -> Agent[Any]:
        tools = bound_tools(context, collector)
        fault = ModelFault(request.fault) if request.fault in MODEL_FAULTS else None
        middleware = Middleware(budget, collector, fault)
        options: Any = {"temperature": TEMPERATURE, "think": self._think}
        ranking = Agent(
            self._clients(config.ranking_model),
            config.ranking_prompt.system,
            name=RANKING_NAME,
            description=RANKING_TOOL_DESCRIPTION,
            tools=maf_tools(tools.ranking),
            default_options=options,
            middleware=[middleware.chat(analyst=False), middleware.function()],
        )
        return Agent(
            self._clients(config.analyst_model),
            analyst_instructions(config, FINISH_RULE),
            name=ANALYST_NAME,
            tools=[
                *maf_tools(tools.analyst),
                *maf_tools([answer_tool(sink)]),
                ranking.as_tool(name=RANKING_TOOL_NAME, description=RANKING_TOOL_DESCRIPTION),
            ],
            default_options=options,
            middleware=[middleware.chat(analyst=True), middleware.function()],
        )

    async def _answered(
        self, analyst: Agent[Any], request: QuestionRequest, sink: AnswerSink
    ) -> None:
        """A run that ends in text gets one reminder to call the answer tool, as Strands does."""
        session = analyst.create_session()
        await analyst.run(question_prompt(request), session=session)
        if sink.answer is None:
            await analyst.run(ANSWER_REMINDER, session=session)

    async def run(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
    ) -> FilingAnswer:
        """The wall-clock budget cancels the run outright."""
        budget = CallBudget(request.call_budget)
        sink = AnswerSink()
        analyst = self.build_analyst(request, config, context, collector, budget, sink)
        try:
            with agent_run_attributes(run_attributes(request, config)):
                await asyncio.wait_for(
                    self._answered(analyst, request, sink), timeout=request.timeout_seconds
                )
        except TimeoutError:
            logger.warning(
                "Question %s passed its %.0f second budget after %d model and %d tool calls",
                request.question_id,
                request.timeout_seconds,
                budget.model_calls,
                budget.tool_calls,
            )
            raise QuestionTimedOut(f"no answer within {request.timeout_seconds} seconds") from None
        except Exception as error:
            refused = _connection_error(error)
            if refused is not None and not isinstance(error, ConnectionError):
                raise refused from error
            raise
        return typed_answer(sink.answer, request.fault)


def from_settings(settings: Settings) -> MafFramework:
    """MAF records message content only with sensitive data on, which follows the standard
    capture variable here."""
    capture = os.environ.get(CAPTURE_CONTENT_VARIABLE, "true").strip().lower() != "false"
    enable_instrumentation(enable_sensitive_data=capture)
    return MafFramework(ollama_clients(settings.ollama_base_url), settings.ollama_think)
