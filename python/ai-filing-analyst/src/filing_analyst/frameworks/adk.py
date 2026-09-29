"""The filing analyst on Google ADK, reaching Ollama through LiteLLM's `ollama_chat` route.

ADK's callbacks carry the shared call budget, the ranking report and the injected faults. The
analyst's `output_schema` gives it ADK's `set_model_response` tool for the typed answer.
"""

import asyncio
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import litellm
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext as AdkToolContext
from google.genai import types
from opentelemetry import trace

from filing_analyst.agents import (
    ANALYST_NAME,
    MODEL_FAULTS,
    RANKING_NAME,
    RANKING_TOOL_DESCRIPTION,
    RANKING_TOOL_NAME,
    TEMPERATURE,
    AgentConfig,
    QuestionRequest,
    QuestionTimedOut,
    analyst_instructions,
    count_ranking,
    question_prompt,
    run_attributes,
    settled_ranking_reply,
    typed_answer,
)
from filing_analyst.answer import FilingAnswer
from filing_analyst.budget import BUDGET_ERROR_TYPE, CallBudget
from filing_analyst.model_faults import SLOW_MODEL_SECONDS, ModelFault, before_model_call
from filing_analyst.telemetry import (
    CAPTURE_CONTENT_VARIABLE,
    ERROR_TYPE_ATTRIBUTE,
    agent_run_attributes,
)
from filing_analyst.tools import bound_tools


if TYPE_CHECKING:
    from filing_analyst.config import Settings
    from filing_analyst.tools import ToolContext
    from filing_analyst.verifier import ToolResultCollector


APP_NAME = "ai-filing-analyst"
USER_ID = "filing-analyst"
MODEL_ROUTE = "ollama_chat"
ADK_CAPTURE_VARIABLE = "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"
ANSWER_TOOL = "set_model_response"
FINISH_RULE = f"Finish by calling the {ANSWER_TOOL} tool with the answer."

type ModelFactory = Callable[[str], BaseLlm]

logger = logging.getLogger(__name__)


def litellm_models(ollama_base_url: str, think: bool) -> ModelFactory:
    def build(model_id: str) -> BaseLlm:
        return LiteLlm(
            model=f"{MODEL_ROUTE}/{model_id}",
            api_base=ollama_base_url,
            reasoning_effort="medium" if think else "none",
        )

    return build


def answer_tool_last(llm_request: LlmRequest) -> None:
    """ADK lists `set_model_response` before the agent's own tools. Listed first, the year
    fields in its schema lead the model to pass years it assumes to `query_facts`."""
    for tool in llm_request.config.tools or []:
        if isinstance(tool, types.Tool) and tool.function_declarations:
            tool.function_declarations.sort(key=lambda declaration: declaration.name == ANSWER_TOOL)


def verbatim(text: str) -> Callable[[ReadonlyContext], str]:
    """ADK fills `{name}` in a string instruction from session state, and the ranking prompt
    holds `{rank}` as text. An instruction provider's text is used as it is."""
    return lambda _context: text


class Callbacks:
    """One question's callbacks, shared by both agents."""

    def __init__(
        self, budget: CallBudget, collector: ToolResultCollector, fault: ModelFault | None
    ) -> None:
        self._budget = budget
        self._collector = collector
        self._fault = fault

    async def before_model(
        self, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        answer_tool_last(llm_request)
        self._budget.count_model()
        if callback_context.agent_name == ANALYST_NAME:
            await before_model_call(self._fault, SLOW_MODEL_SECONDS)
        return None

    def before_tool(
        self, tool: BaseTool, args: dict[str, Any], tool_context: AdkToolContext
    ) -> dict[str, Any] | None:
        exceeded = self._budget.count_tool()
        if exceeded is None:
            return None
        trace.get_current_span().set_attribute(ERROR_TYPE_ATTRIBUTE, BUDGET_ERROR_TYPE)
        return {"error": "budget", "detail": str(exceeded)}

    def after_tool(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: AdkToolContext,
        tool_response: Any,
    ) -> dict[str, Any] | None:
        if tool.name != RANKING_TOOL_NAME:
            return None
        count_ranking(self._collector, failed=False)
        settled = settled_ranking_reply(self._collector, str(tool_response))
        return None if settled is None else {"result": settled}

    def on_tool_error(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: AdkToolContext,
        error: Exception,
    ) -> dict[str, Any] | None:
        """A failed tool goes back to the model as an error result, as in the other
        frameworks, rather than ending the run."""
        if tool.name == RANKING_TOOL_NAME:
            count_ranking(self._collector, failed=True)
        logger.warning("Tool %s failed: %s", tool.name, type(error).__name__)
        return {"error": type(error).__name__, "detail": str(error)}


class AdkFramework:
    name = "adk"

    def __init__(self, models: ModelFactory) -> None:
        self._models = models

    def build_analyst(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
        budget: CallBudget,
    ) -> LlmAgent:
        tools = bound_tools(context, collector)
        fault = ModelFault(request.fault) if request.fault in MODEL_FAULTS else None
        callbacks = Callbacks(budget, collector, fault)
        settings = types.GenerateContentConfig(temperature=TEMPERATURE)
        hooks: dict[str, Any] = {
            "before_model_callback": callbacks.before_model,
            "before_tool_callback": callbacks.before_tool,
            "after_tool_callback": callbacks.after_tool,
            "on_tool_error_callback": callbacks.on_tool_error,
        }
        ranking = LlmAgent(
            name=RANKING_NAME,
            model=self._models(config.ranking_model),
            description=RANKING_TOOL_DESCRIPTION,
            instruction=verbatim(config.ranking_prompt.system),
            tools=list(tools.ranking),
            generate_content_config=settings,
            **hooks,
        )
        ranking_tool = AgentTool(agent=ranking)
        ranking_tool.name = RANKING_TOOL_NAME
        return LlmAgent(
            name=ANALYST_NAME,
            model=self._models(config.analyst_model),
            instruction=verbatim(analyst_instructions(config, FINISH_RULE)),
            tools=[*tools.analyst, ranking_tool],
            output_schema=FilingAnswer,
            generate_content_config=settings,
            **hooks,
        )

    async def _final_text(self, runner: Runner, request: QuestionRequest) -> str | None:
        final = None
        message = types.Content(role="user", parts=[types.Part(text=question_prompt(request))])
        async for event in runner.run_async(
            user_id=USER_ID, session_id=request.question_id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final = "".join(part.text or "" for part in event.content.parts)
        return final

    async def run(
        self,
        request: QuestionRequest,
        config: AgentConfig,
        context: ToolContext,
        collector: ToolResultCollector,
    ) -> FilingAnswer:
        """The session ID is the question ID, so ADK records it as the conversation ID. The
        wall-clock budget cancels the run outright."""
        budget = CallBudget(request.call_budget)
        analyst = self.build_analyst(request, config, context, collector, budget)
        sessions = InMemorySessionService()
        await sessions.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=request.question_id
        )
        runner = Runner(agent=analyst, app_name=APP_NAME, session_service=sessions)
        try:
            with agent_run_attributes(run_attributes(request, config)):
                final = await asyncio.wait_for(
                    self._final_text(runner, request), timeout=request.timeout_seconds
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
        except litellm.exceptions.APIConnectionError as error:
            raise ConnectionError(str(error)) from error
        return typed_answer(final, request.fault)


def apply_capture_setting() -> None:
    """ADK's own spans follow `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS`, which is on by default,
    rather than the standard capture variable. This sets it to match."""
    capture = os.environ.get(CAPTURE_CONTENT_VARIABLE, "true").strip().lower() != "false"
    os.environ[ADK_CAPTURE_VARIABLE] = "true" if capture else "false"


def from_settings(settings: Settings) -> AdkFramework:
    apply_capture_setting()
    return AdkFramework(litellm_models(settings.ollama_base_url, settings.ollama_think))
