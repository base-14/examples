"""The filing analyst on the OpenAI Agents SDK, reaching Ollama through its OpenAI-compatible
`/v1` endpoint.

Run hooks carry the shared call budget and the injected faults; the ranking tool's output
extractor carries the ranking report. The analyst answers by calling a `FilingAnswer` tool,
which ends the run, rather than through `output_type`: Ollama applies the resulting
`response_format` on every call, which leaves the model no way to call a tool. The instrumentor replaces the SDK's own trace exporter,
so no trace goes to OpenAI.
"""

import asyncio
import functools
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import openai
from agents import (
    Agent,
    ModelBehaviorError,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunContextWrapper,
    RunHooks,
    Runner,
    RunResult,
    RunResultStreaming,
    StopAtTools,
    Tool,
    function_tool,
)
from agents.items import TResponseInputItem
from agents.models.interface import Model
from openai import AsyncOpenAI
from openai.types.shared import Reasoning
from opentelemetry import trace
from opentelemetry.instrumentation.genai.openai import OpenAIInstrumentor
from opentelemetry.instrumentation.genai.openai_agents import OpenAIAgentsInstrumentor

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
    BadOutput,
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
OLLAMA_API_KEY = "ollama"
MAX_TURNS = 100

type ModelFactory = Callable[[str], Model]

logger = logging.getLogger(__name__)


def ollama_models(ollama_base_url: str) -> ModelFactory:
    client = AsyncOpenAI(base_url=f"{ollama_base_url.rstrip('/')}/v1", api_key=OLLAMA_API_KEY)

    def build(model_id: str) -> Model:
        return OpenAIChatCompletionsModel(model=model_id, openai_client=client)

    return build


def openai_tools(
    tools: list[BoundTool] | list[Callable[..., str]], budget: CallBudget
) -> list[Tool]:
    """Strict schemas mark every parameter required, and a small model then fills an
    optional year with the text `None`, which fails validation. Non-strict schemas leave
    optional parameters out of `required`."""
    return [
        function_tool(within_budget(bound, budget), name_override=bound.__name__, strict_mode=False)
        for bound in tools
    ]


def within_budget(bound: Callable[..., Any], budget: CallBudget) -> Callable[..., Any]:
    """A tool past the budget returns the stop as its result instead of running, as Strands'
    `cancel_tool` does. The run hooks cannot cancel a tool, and one that raises at tool start
    leaves the stop on the tool span rather than on `invoke_agent`."""

    @functools.wraps(bound)
    def call(*args: Any, **kwargs: Any) -> Any:
        if budget.exceeded is not None:
            return {"error": "budget", "message": str(budget.exceeded)}
        return bound(*args, **kwargs)

    return call


class Hooks(RunHooks[Any]):
    """One question's run hooks, which see both agents' model and tool calls."""

    def __init__(self, budget: CallBudget, fault: ModelFault | None) -> None:
        self._budget = budget
        self._fault = fault

    async def on_llm_start(
        self,
        context: RunContextWrapper[Any],
        agent: Agent[Any],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """The instrumentation ends a failed `invoke_agent` with `error.type` `_OTHER` and no
        exception, so a hook that stops the run records the exception on it, which the
        exporter reads the type from."""
        try:
            self._budget.count_model()
            if agent.name == ANALYST_NAME:
                await before_model_call(self._fault, SLOW_MODEL_SECONDS)
        except Exception as error:
            trace.get_current_span().record_exception(error)
            raise

    async def on_tool_start(
        self, context: RunContextWrapper[Any], agent: Agent[Any], tool: Tool
    ) -> None:
        self._budget.count_tool()


class OpenAIAgentsFramework:
    name = "openai-agents"

    def __init__(self, models: ModelFactory, think: bool) -> None:
        self._models = models
        self._settings = ModelSettings(
            temperature=TEMPERATURE, reasoning=Reasoning(effort="medium" if think else "none")
        )

    def build_analyst(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
        sink: AnswerSink,
        budget: CallBudget,
    ) -> Agent[Any]:
        tools = bound_tools(context, collector)

        async def ranking_report(result: RunResult | RunResultStreaming) -> str:
            reply = str(result.final_output)
            count_ranking(collector, failed=False)
            return settled_ranking_reply(collector, reply) or reply

        ranking = Agent(
            name=RANKING_NAME,
            instructions=config.ranking_prompt.system,
            model=self._models(config.ranking_model),
            model_settings=self._settings,
            tools=openai_tools(tools.ranking, budget),
        )
        return Agent(
            name=ANALYST_NAME,
            instructions=analyst_instructions(config, FINISH_RULE),
            model=self._models(config.analyst_model),
            model_settings=self._settings,
            tools=[
                *openai_tools(tools.analyst, budget),
                *openai_tools([answer_tool(sink)], budget),
                ranking.as_tool(
                    tool_name=RANKING_TOOL_NAME,
                    tool_description=RANKING_TOOL_DESCRIPTION,
                    custom_output_extractor=ranking_report,
                ),
            ],
            tool_use_behavior=StopAtTools(stop_at_tool_names=[ANSWER_TOOL]),
        )

    async def _answered(
        self, analyst: Agent[Any], request: QuestionRequest, hooks: Hooks, sink: AnswerSink
    ) -> None:
        """A run that ends in text gets one reminder to call the answer tool, as Strands does."""
        result = await Runner.run(
            analyst, question_prompt(request), hooks=hooks, max_turns=MAX_TURNS
        )
        if sink.answer is None:
            reminder: TResponseInputItem = {"role": "user", "content": ANSWER_REMINDER}
            await Runner.run(
                analyst, [*result.to_input_list(), reminder], hooks=hooks, max_turns=MAX_TURNS
            )

    async def run(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
    ) -> FilingAnswer:
        """The wall-clock budget cancels the run outright. The SDK raises `ModelBehaviorError`
        for a call to a tool it does not have."""
        budget = CallBudget(request.call_budget)
        fault = ModelFault(request.fault) if request.fault in MODEL_FAULTS else None
        sink = AnswerSink()
        analyst = self.build_analyst(request, config, context, collector, sink, budget)
        try:
            with agent_run_attributes(run_attributes(request, config)):
                await asyncio.wait_for(
                    self._answered(analyst, request, Hooks(budget, fault), sink),
                    timeout=request.timeout_seconds,
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
        except ModelBehaviorError as error:
            logger.warning("Structured output failed validation: %s", str(error)[:500])
            raise BadOutput(str(error)) from error
        except openai.APIConnectionError as error:
            raise ConnectionError(str(error)) from error
        return typed_answer(sink.answer, request.fault)


def apply_capture_mode() -> None:
    """The GenAI instrumentations take a capture mode, not `true`. `SPAN_ONLY` records content
    on the spans, as the other frameworks here do."""
    capture = os.environ.get(CAPTURE_CONTENT_VARIABLE, "true").strip().lower() != "false"
    os.environ[CAPTURE_CONTENT_VARIABLE] = "SPAN_ONLY" if capture else "NO_CONTENT"


def from_settings(settings: Settings) -> OpenAIAgentsFramework:
    apply_capture_mode()
    OpenAIAgentsInstrumentor().instrument(disable_openai_trace_export=True)
    OpenAIInstrumentor().instrument()  # type: ignore[no-untyped-call]
    return OpenAIAgentsFramework(ollama_models(settings.ollama_base_url), settings.ollama_think)
