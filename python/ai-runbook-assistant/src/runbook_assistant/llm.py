"""Provider-agnostic LangChain chat model with retry and provider fallback.

`ResilientChatModel` wraps a primary and a fallback chat model. Retries run
inside one LangChain model run, so a transient failure stays invisible to the
trace and one provider attempt means one `chat` span. When the primary is
exhausted the call switches provider, and the switch is reported back to the
handler through `llm_output`, which closes the primary's span as failed and
opens a second one for the provider that answered.
"""

import time
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.language_models.base import LangSmithParams
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.runnables.config import set_config_context
from langchain_core.tools import BaseTool
from pydantic import Field
from tenacity import RetryCallState, Retrying, stop_after_attempt, wait_exponential

from runbook_assistant.config import LLMProvider, get_settings
from runbook_assistant.providers import semconv_name
from runbook_assistant.telemetry.metrics import get_metrics


RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT_S = 1
RETRY_MAX_WAIT_S = 10

SILENT_CONFIG: RunnableConfig = {"callbacks": []}

SERVED_PROVIDER = "base14.served.provider"
SERVED_MODEL = "base14.served.model"
FALLBACK = "base14.fallback"

ToolSpec = dict[str, Any] | type | Callable[..., Any] | BaseTool


def build_chat_model(provider: LLMProvider, model: str) -> BaseChatModel:
    s = get_settings()
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            temperature=s.default_temperature,
            num_predict=s.default_max_tokens,
            base_url=s.ollama_base_url,
            reasoning=s.ollama_reasoning,
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=s.default_temperature,
            max_tokens=s.default_max_tokens,
            api_key=s.anthropic_api_key,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=s.default_temperature,
            max_tokens=s.default_max_tokens,
            api_key=s.openai_api_key,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=s.default_temperature,
        max_output_tokens=s.default_max_tokens,
        google_api_key=s.google_api_key,
    )


def build_resilient_chat_model() -> BaseChatModel:
    s = get_settings()
    primary = build_chat_model(s.llm_provider, s.llm_model)
    fallback = None
    if s.fallback_provider != s.llm_provider or s.fallback_model != s.llm_model:
        fallback = build_chat_model(s.fallback_provider, s.fallback_model)
    return ResilientChatModel(
        primary=primary,
        primary_provider=semconv_name(s.llm_provider),
        primary_model=s.llm_model,
        fallback=fallback,
        fallback_provider=semconv_name(s.fallback_provider),
        fallback_model=s.fallback_model,
        temperature=s.default_temperature,
        max_tokens=s.default_max_tokens,
    )


def _retry_recorder(provider: str) -> Callable[[RetryCallState], None]:
    def record(state: RetryCallState) -> None:
        exc = state.outcome.exception() if state.outcome else None
        get_metrics().add_retry(
            {
                "gen_ai.provider.name": provider,
                "error.type": type(exc).__qualname__ if exc else "unknown",
                "base14.retry.attempt": state.attempt_number,
            }
        )

    return record


class ResilientChatModel(BaseChatModel):
    """Chat model that retries the primary provider and then switches to the fallback."""

    primary: BaseChatModel
    primary_provider: str
    primary_model: str
    fallback: BaseChatModel | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 4096
    bound_tools: list[Any] | None = None
    bound_kwargs: dict[str, Any] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "resilient"

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> LangSmithParams:
        return LangSmithParams(
            ls_provider=self.primary_provider,
            ls_model_name=self.primary_model,
            ls_model_type="chat",
            ls_temperature=self.temperature,
            ls_max_tokens=self.max_tokens,
        )

    def bind_tools(
        self,
        tools: Sequence[ToolSpec],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        bound_kwargs = dict(kwargs)
        if tool_choice is not None:
            bound_kwargs["tool_choice"] = tool_choice
        return self.model_copy(update={"bound_tools": list(tools), "bound_kwargs": bound_kwargs})

    def _target(self, model: BaseChatModel) -> Runnable[LanguageModelInput, BaseMessage]:
        if self.bound_tools is None:
            return model
        return model.bind_tools(self.bound_tools, **self.bound_kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        started = time.perf_counter()
        try:
            message = self._call(self.primary, self.primary_provider, messages, stop, kwargs)
        except Exception as exc:
            if self.fallback is None or self.fallback_provider is None:
                raise
            self._record_switch(exc)
            # The handler closes the primary's span at this instant and opens
            # the fallback's span from it, so it can split the duration between them.
            switch: dict[str, Any] = {
                "from": self.primary_provider,
                "to": self.fallback_provider,
                "error.type": type(exc).__qualname__,
                "exception": exc,
                "primary_seconds": time.perf_counter() - started,
                "switched_ns": time.time_ns(),
            }
            message = self._call(self.fallback, self.fallback_provider, messages, stop, kwargs)
            return _result(
                message, self.fallback_provider, self.fallback_model or "unknown", switch
            )
        return _result(message, self.primary_provider, self.primary_model)

    def _call(
        self,
        model: BaseChatModel,
        provider: str,
        messages: list[BaseMessage],
        stop: list[str] | None,
        kwargs: dict[str, Any],
    ) -> BaseMessage:
        """Invoke one provider, retrying inside the caller's model run.

        The inner call runs with no handlers, so the caller's handler sees one
        chat span for the logical call however many attempts it took. Clearing
        the ambient config matters as much as passing an empty `callbacks`:
        `bind_tools` returns a RunnableBinding, and its config merge re-inherits
        the ambient handlers, which would open a second span per attempt.
        """
        retrying = Retrying(
            stop=stop_after_attempt(RETRY_ATTEMPTS),
            wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT_S, max=RETRY_MAX_WAIT_S),
            before_sleep=_retry_recorder(provider),
            reraise=True,
        )
        target = self._target(model)

        def attempt() -> BaseMessage:
            return retrying(target.invoke, messages, config=SILENT_CONFIG, stop=stop, **kwargs)

        with set_config_context(SILENT_CONFIG) as context:
            return context.run(attempt)

    def _record_switch(self, exc: Exception) -> None:
        error_type = type(exc).__qualname__
        metrics = get_metrics()
        metrics.add_error(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": self.primary_provider,
                "gen_ai.request.model": self.primary_model,
                "error.type": error_type,
            }
        )
        metrics.add_fallback(
            {
                "gen_ai.provider.name": self.primary_provider,
                "base14.gen_ai.fallback.provider": self.fallback_provider,
                "error.type": error_type,
            }
        )

    def _combine_llm_outputs(self, llm_outputs: list[dict[str, Any] | None]) -> dict[str, Any]:
        return next((output for output in llm_outputs if output), {})


def _result(
    message: BaseMessage,
    provider: str,
    model: str,
    switch: dict[str, Any] | None = None,
) -> ChatResult:
    llm_output: dict[str, Any] = {SERVED_PROVIDER: provider, SERVED_MODEL: model}
    if switch is not None:
        llm_output[FALLBACK] = switch
    return ChatResult(
        generations=[ChatGeneration(message=message)],
        llm_output=llm_output,
    )
