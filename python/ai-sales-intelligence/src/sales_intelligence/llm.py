"""LLM client with unified observability.

Provider-agnostic client for Anthropic, Gemini, OpenAI and Ollama, instrumented
to the OpenTelemetry GenAI semantic conventions.

httpx auto-instrumentation records the HTTP layer of every provider call. This
module adds what auto-instrumentation cannot know: the `chat {model}` span with
GenAI attributes, the inference content event, the token, duration and cost
metrics, and the retry, fallback and error counters.
"""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

from sales_intelligence.config import LLMProvider, get_settings
from sales_intelligence.pii import scrub_completion, scrub_prompt


logger = logging.getLogger(__name__)

PROMPT_MAX_CHARS = 1000
SYSTEM_MAX_CHARS = 500
COMPLETION_MAX_CHARS = 2000


def _load_pricing() -> dict[str, dict[str, float]]:
    this_file = Path(__file__)
    for depth in (4, 2):
        if depth < len(this_file.parents):
            candidate = this_file.parents[depth] / "_shared" / "pricing.json"
            if candidate.exists():
                with candidate.open() as f:
                    data = json.load(f)
                return {
                    model: {"input": info["input"], "output": info["output"]}
                    for model, info in data["models"].items()
                }
    raise FileNotFoundError(
        "pricing.json not found. Ensure _shared/pricing.json exists at the repo root "
        "and _shared/ is mounted into the container."
    )


PRICING: dict[str, dict[str, float]] = _load_pricing()

PROVIDER_SERVERS: dict[LLMProvider, str] = {
    "anthropic": "api.anthropic.com",
    "google": "generativelanguage.googleapis.com",
    "openai": "api.openai.com",
    "ollama": "localhost",
}

PROVIDER_PORTS: dict[LLMProvider, int] = {
    "anthropic": 443,
    "google": 443,
    "openai": 443,
    "ollama": 11434,
}

# The config value for Gemini is `google`, matching the gateway contract. The
# telemetry attribute uses the semantic convention name.
PROVIDER_SEMCONV_NAMES: dict[LLMProvider, str] = {
    "anthropic": "anthropic",
    "google": "gcp.gemini",
    "openai": "openai",
    "ollama": "ollama",
}

tracer = trace.get_tracer("gen_ai.client")
meter = metrics.get_meter("gen_ai.client")

_token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    description="Number of tokens used per LLM call",
    unit="{token}",
)
_operation_duration = meter.create_histogram(
    name="gen_ai.client.operation.duration",
    description="Duration of GenAI operations",
    unit="s",
)
_cost_counter = meter.create_counter(
    name="base14.gen_ai.cost",
    description="Cost of GenAI operations in USD",
    unit="usd",
)
_retry_counter = meter.create_counter(
    name="base14.gen_ai.retry.count",
    description="Number of retry attempts, excluding the initial attempt",
    unit="{retry}",
)
_fallback_counter = meter.create_counter(
    name="base14.gen_ai.fallback.count",
    description="Number of fallback triggers",
    unit="{fallback}",
)
_error_counter = meter.create_counter(
    name="base14.gen_ai.error.count",
    description="Number of errors by type",
    unit="{error}",
)


def _on_retry(retry_state: RetryCallState) -> None:
    provider = "unknown"
    if retry_state.args and hasattr(retry_state.args[0], "provider_name"):
        provider = PROVIDER_SEMCONV_NAMES[retry_state.args[0].provider_name]

    error_type = "unknown"
    if retry_state.outcome and retry_state.outcome.exception():
        error_type = type(retry_state.outcome.exception()).__qualname__

    _retry_counter.add(
        1,
        {
            "gen_ai.provider.name": provider,
            "error.type": error_type,
            "base14.retry.attempt": retry_state.attempt_number,
        },
    )


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    input_tokens: int
    output_tokens: int
    model: str
    response_id: str | None = None
    finish_reason: str | None = None


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""

    provider_name: LLMProvider
    server_address: str
    server_port: int

    @abstractmethod
    def __init__(self, api_key: str) -> None: ...

    @abstractmethod
    async def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse: ...


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    provider_name: LLMProvider = "anthropic"
    server_address: str = PROVIDER_SERVERS["anthropic"]
    server_port: int = PROVIDER_PORTS["anthropic"]

    def __init__(self, api_key: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
        reraise=True,
    )
    async def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        content = ""
        if response.content:
            block = response.content[0]
            if hasattr(block, "text"):
                content = block.text
        logger.info(
            "LLM response length: %d, stop_reason: %s",
            len(content),
            response.stop_reason,
        )
        return LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            response_id=response.id,
            finish_reason=response.stop_reason,
        )


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider."""

    provider_name: LLMProvider = "google"
    server_address: str = PROVIDER_SERVERS["google"]
    server_port: int = PROVIDER_PORTS["google"]

    def __init__(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
        reraise=True,
    )
    async def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        from google.genai.types import GenerateContentConfig

        config = GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        response = await self._client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        content = response.text or ""
        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count if usage and usage.prompt_token_count else 0
        output_tokens = (
            usage.candidates_token_count if usage and usage.candidates_token_count else 0
        )
        finish_reason = None
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = str(response.candidates[0].finish_reason)
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            response_id=None,
            finish_reason=finish_reason,
        )


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider."""

    provider_name: LLMProvider = "openai"
    server_address: str = PROVIDER_SERVERS["openai"]
    server_port: int = PROVIDER_PORTS["openai"]

    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
        reraise=True,
    )
    async def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message else ""
        finish_reason = choice.finish_reason if choice else None
        usage = response.usage
        return LLMResponse(
            content=content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=response.model,
            response_id=response.id,
            finish_reason=finish_reason,
        )


class OllamaProvider(BaseLLMProvider):
    """Ollama local model provider (OpenAI-compatible API)."""

    provider_name: LLMProvider = "ollama"

    def __init__(self, api_key: str, base_url: str = "http://localhost:11434") -> None:
        from openai import AsyncOpenAI

        parsed_base_url = urlparse(base_url)
        self.server_address = parsed_base_url.hostname or PROVIDER_SERVERS["ollama"]
        self.server_port = parsed_base_url.port or PROVIDER_PORTS["ollama"]
        # Ollama's OpenAI-compatible API lives at /v1
        if not base_url.endswith("/v1"):
            base_url = f"{base_url.rstrip('/')}/v1"
        self._client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
        reraise=True,
    )
    async def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message else ""
        finish_reason = choice.finish_reason if choice else None
        usage = response.usage
        return LLMResponse(
            content=content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=response.model,
            response_id=response.id,
            finish_reason=finish_reason,
        )


def _create_provider(provider: LLMProvider, api_key: str, base_url: str = "") -> BaseLLMProvider:
    if provider == "ollama":
        return OllamaProvider(api_key=api_key, base_url=base_url or "http://localhost:11434")
    providers: dict[LLMProvider, type[BaseLLMProvider]] = {
        "anthropic": AnthropicProvider,
        "google": GeminiProvider,
        "openai": OpenAIProvider,
    }
    return providers[provider](api_key)


def _get_api_key(provider: LLMProvider) -> str:
    """Get API key for provider from settings."""
    settings = get_settings()
    keys: dict[LLMProvider, str] = {
        "anthropic": settings.anthropic_api_key,
        "google": settings.google_api_key,
        "openai": settings.openai_api_key,
        "ollama": "",
    }
    return keys[provider]


_MODEL_DATE_SUFFIX = re.compile(r"-\d{8}$")
_MODEL_MINOR_VERSION = re.compile(r"^(claude-(?:sonnet|opus|haiku))-(\d+)-(\d+)$")


def _normalize_model_id(model: str) -> str:
    """Map a provider-returned model ID to its pricing.json key.

    Providers return dated IDs (claude-sonnet-4-5-20250929) and dash-minor
    forms (claude-opus-4-6); pricing keys are dot-form (claude-opus-4.6).
    """
    stripped = _MODEL_DATE_SUFFIX.sub("", model)
    return _MODEL_MINOR_VERSION.sub(r"\1-\2.\3", stripped)


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a model call. Unknown models cost 0.0."""
    pricing = PRICING.get(model) or PRICING.get(
        _normalize_model_id(model), {"input": 0.0, "output": 0.0}
    )
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def _emit_content_event(span: Span, prompt: str, system: str, response: LLMResponse | None) -> None:
    """Emit the inference content event when content capture is switched on.

    Content is PII-scrubbed and truncated. The system prompt goes on
    gen_ai.system_instructions, not into the input messages.
    """
    if not get_settings().otel_instrumentation_genai_capture_message_content:
        return

    attributes: dict[str, Any] = {
        "gen_ai.input.messages": scrub_prompt(prompt)[:PROMPT_MAX_CHARS],
    }
    system_instructions = scrub_prompt(system)[:SYSTEM_MAX_CHARS]
    if system_instructions:
        attributes["gen_ai.system_instructions"] = system_instructions
    if response is not None:
        attributes["gen_ai.output.messages"] = scrub_completion(response.content)[
            :COMPLETION_MAX_CHARS
        ]

    span.add_event("gen_ai.client.inference.operation.details", attributes=attributes)


def _record_duration(base_attrs: dict[str, Any], duration: float, error_type: str | None) -> None:
    attrs = dict(base_attrs)
    if error_type:
        attrs["error.type"] = error_type
    _operation_duration.record(duration, attrs)


def _record_usage(
    base_attrs: dict[str, Any],
    response: LLMResponse,
    model: str,
    agent_name: str | None,
    campaign_id: str | None,
    span: Span,
) -> None:
    usage_attrs = {**base_attrs, "gen_ai.response.model": response.model}

    _token_usage.record(response.input_tokens, {**usage_attrs, "gen_ai.token.type": "input"})
    _token_usage.record(response.output_tokens, {**usage_attrs, "gen_ai.token.type": "output"})

    cost = _calculate_cost(model, response.input_tokens, response.output_tokens)
    cost_attrs = dict(usage_attrs)
    if agent_name:
        cost_attrs["gen_ai.agent.name"] = agent_name
    if campaign_id:
        cost_attrs["base14.campaign_id"] = campaign_id
    _cost_counter.add(cost, cost_attrs)

    span.set_attribute("base14.gen_ai.cost_usd", cost)


class LLMClient:
    """Provider-agnostic LLM client with OTel GenAI instrumentation.

    Each call opens a CLIENT span named `chat {model}`. When the primary
    provider fails after its retries, the client switches to the fallback
    provider and records the switch on the calling span.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._primary_provider = settings.llm_provider
        self.model_capable = settings.llm_model_capable
        self.model_fast = settings.llm_model_fast
        self._fallback_provider = settings.fallback_provider
        self._fallback_model = settings.fallback_model
        self._temperature = settings.default_temperature
        self._max_tokens = settings.default_max_tokens
        self._ollama_base_url = settings.ollama_base_url
        self._providers: dict[LLMProvider, BaseLLMProvider] = {}

    def _get_provider(self, provider: LLMProvider) -> BaseLLMProvider:
        """Lazy-load provider instance."""
        if provider not in self._providers:
            api_key = _get_api_key(provider)
            self._providers[provider] = _create_provider(provider, api_key, self._ollama_base_url)
        return self._providers[provider]

    async def generate(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
        provider: LLMProvider | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        use_fallback: bool = True,
        agent_name: str | None = None,
        campaign_id: str | None = None,
    ) -> str:
        """Generate text, falling back to the secondary provider on failure.

        Args:
            prompt: User prompt
            system: System instruction
            provider: LLM provider (defaults to settings.llm_provider)
            model: Model to use (defaults to the capable model)
            temperature: Sampling temperature
            max_tokens: Max output tokens
            use_fallback: Whether to switch provider when the primary fails
            agent_name: Agent name for cost attribution
            campaign_id: Campaign ID for cost attribution

        Returns:
            Generated text content
        """
        provider = provider or self._primary_provider
        model = model or self.model_capable
        temperature = temperature if temperature is not None else self._temperature
        max_tokens = max_tokens or self._max_tokens

        try:
            return await self._chat(
                provider=provider,
                model=model,
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                agent_name=agent_name,
                campaign_id=campaign_id,
            )
        except Exception as exc:
            if not use_fallback or provider == self._fallback_provider:
                raise
            self._record_fallback(provider, exc)
            return await self._chat(
                provider=self._fallback_provider,
                model=self._fallback_model,
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                agent_name=agent_name,
                campaign_id=campaign_id,
            )

    def _record_fallback(self, provider: LLMProvider, exc: Exception) -> None:
        """Record the provider switch on the calling span without failing it."""
        error_type = type(exc).__qualname__
        attrs = {
            "gen_ai.provider.name": PROVIDER_SEMCONV_NAMES[provider],
            "base14.gen_ai.fallback.provider": PROVIDER_SEMCONV_NAMES[self._fallback_provider],
            "error.type": error_type,
        }

        span = trace.get_current_span()
        span.record_exception(exc)
        span.add_event("provider_fallback", attributes=attrs)
        span.set_attribute("gen_ai.fallback.triggered", True)

        _fallback_counter.add(1, attrs)

    async def _chat(
        self,
        provider: LLMProvider,
        model: str,
        prompt: str,
        system: str,
        temperature: float,
        max_tokens: int,
        agent_name: str | None,
        campaign_id: str | None,
    ) -> str:
        """Run one chat completion inside a `chat {model}` CLIENT span."""
        llm_provider = self._get_provider(provider)

        metric_attrs: dict[str, Any] = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": PROVIDER_SEMCONV_NAMES[provider],
            "gen_ai.request.model": model,
            "server.address": llm_provider.server_address,
            "server.port": llm_provider.server_port,
        }

        # Sampling-relevant attributes are set at span creation.
        span_attrs: dict[str, Any] = {
            **metric_attrs,
            "gen_ai.request.temperature": temperature,
            "gen_ai.request.max_tokens": max_tokens,
        }
        if agent_name:
            span_attrs["gen_ai.agent.name"] = agent_name
        if campaign_id:
            span_attrs["base14.campaign_id"] = campaign_id

        with tracer.start_as_current_span(
            f"chat {model}", kind=SpanKind.CLIENT, attributes=span_attrs
        ) as span:
            start_time = time.perf_counter()
            response: LLMResponse | None = None
            error_type: str | None = None

            try:
                response = await llm_provider.generate(
                    model=model,
                    system=system,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                span.set_attribute("gen_ai.response.model", response.model)
                if response.response_id:
                    span.set_attribute("gen_ai.response.id", response.response_id)
                if response.finish_reason:
                    span.set_attribute("gen_ai.response.finish_reasons", [response.finish_reason])
                span.set_attribute("gen_ai.usage.input_tokens", response.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.output_tokens)

                _record_usage(metric_attrs, response, model, agent_name, campaign_id, span)

                return response.content

            except Exception as exc:
                error_type = type(exc).__qualname__
                span.record_exception(exc)
                span.set_attribute("error.type", error_type)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                _error_counter.add(
                    1,
                    {
                        "gen_ai.provider.name": PROVIDER_SEMCONV_NAMES[provider],
                        "gen_ai.request.model": model,
                        "error.type": error_type,
                    },
                )
                raise

            finally:
                _record_duration(metric_attrs, time.perf_counter() - start_time, error_type)
                _emit_content_event(span, prompt, system, response)


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get singleton LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
