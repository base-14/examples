"""Provider-agnostic LangChain chat models, with retry and provider fallback as agent middleware.

`ResilienceMiddleware` retries the primary model and then switches to the fallback
through `create_agent`'s `wrap_model_call` hook. Every attempt runs the real chat
model, so the OpenTelemetry LangChain instrumentation records one `chat {model}` span
per attempt and names the model that answered. The middleware adds what the
instrumentation does not record: the retry, fallback, error and cost metrics, and the
`provider_fallback` event.

LangChain also ships `ModelRetryMiddleware` and `ModelFallbackMiddleware`. This one
exists because the example counts retries and fallbacks.
"""

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from opentelemetry import trace
from tenacity import RetryCallState, Retrying, stop_after_attempt, wait_exponential

from runbook_assistant.config import LLMProvider, get_settings
from runbook_assistant.cost import calculate_cost
from runbook_assistant.providers import semconv_name
from runbook_assistant.telemetry.metrics import get_metrics


RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT_S = 1
RETRY_MAX_WAIT_S = 10


def build_chat_model(provider: LLMProvider, model: str) -> BaseChatModel:
    """The provider SDKs' own retries are off, so each attempt is one span."""
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
            max_retries=0,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=s.default_temperature,
            max_tokens=s.default_max_tokens,
            api_key=s.openai_api_key,
            max_retries=0,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=s.default_temperature,
        max_output_tokens=s.default_max_tokens,
        google_api_key=s.google_api_key,
        max_retries=0,
    )


class ResilienceMiddleware(AgentMiddleware):
    """Retries the model call, then switches to the fallback model, recording both."""

    def __init__(
        self,
        primary_provider: str,
        primary_model: str,
        fallback: BaseChatModel | None = None,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__()
        self.primary_provider = primary_provider
        self.primary_model = primary_model
        self.fallback = fallback
        self.fallback_provider = fallback_provider
        self.fallback_model = fallback_model

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        try:
            response = self._attempt(handler, request, self.primary_provider)
        except Exception as exc:
            if self.fallback is None or self.fallback_provider is None:
                self._record_error(exc)
                raise
            self._record_switch(exc)
            response = self._attempt(
                handler, request.override(model=self.fallback), self.fallback_provider
            )
            self._record_cost(response, self.fallback_provider, self.fallback_model)
            return response
        self._record_cost(response, self.primary_provider, self.primary_model)
        return response

    def _attempt(
        self,
        handler: Callable[[ModelRequest], ModelResponse],
        request: ModelRequest,
        provider: str,
    ) -> ModelResponse:
        retrying = Retrying(
            stop=stop_after_attempt(RETRY_ATTEMPTS),
            wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT_S, max=RETRY_MAX_WAIT_S),
            before_sleep=_retry_recorder(provider),
            reraise=True,
        )
        return retrying(handler, request)

    def _record_error(self, exc: Exception) -> None:
        get_metrics().add_error(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": self.primary_provider,
                "gen_ai.request.model": self.primary_model,
                "error.type": type(exc).__qualname__,
            }
        )

    def _record_switch(self, exc: Exception) -> None:
        """The switch is an event on the agent's span, which does not fail if the fallback answers."""
        self._record_error(exc)
        attrs = {
            "gen_ai.provider.name": self.primary_provider,
            "base14.gen_ai.fallback.provider": self.fallback_provider or "unknown",
            "error.type": type(exc).__qualname__,
        }
        get_metrics().add_fallback(attrs)
        span = trace.get_current_span()
        span.add_event("provider_fallback", attrs)
        span.set_attribute("gen_ai.fallback.triggered", True)

    def _record_cost(self, response: ModelResponse, provider: str, model: str | None) -> None:
        message = next((m for m in response.result if isinstance(m, AIMessage)), None)
        usage = message.usage_metadata if message is not None else None
        if usage is None or model is None:
            return
        get_metrics().add_cost(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": provider,
                "gen_ai.request.model": model,
            },
            calculate_cost(model, usage["input_tokens"], usage["output_tokens"]),
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


def build_models() -> tuple[BaseChatModel, ResilienceMiddleware]:
    """The primary chat model, and the middleware that retries it and falls back."""
    s = get_settings()
    primary = build_chat_model(s.llm_provider, s.llm_model)
    fallback = None
    if s.fallback_provider != s.llm_provider or s.fallback_model != s.llm_model:
        fallback = build_chat_model(s.fallback_provider, s.fallback_model)
    middleware = ResilienceMiddleware(
        primary_provider=semconv_name(s.llm_provider),
        primary_model=s.llm_model,
        fallback=fallback,
        fallback_provider=semconv_name(s.fallback_provider),
        fallback_model=s.fallback_model,
    )
    return primary, middleware
