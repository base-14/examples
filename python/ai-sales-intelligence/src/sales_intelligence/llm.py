"""LLM client with unified observability.

Provider-agnostic design supporting Anthropic, Google, and OpenAI with full
OpenTelemetry GenAI semantic conventions instrumentation.

Auto-instrumentation via opentelemetry-instrumentation-httpx captures HTTP-level
spans automatically. This module adds CUSTOM instrumentation for:
- GenAI-specific span attributes (model, tokens, cost) - enables LLM cost tracking
- GenAI metrics (token usage, duration, cost) - enables usage dashboards
- Business context (agent name, campaign ID) - enables cost attribution
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opentelemetry import metrics, trace
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

from sales_intelligence.config import LLMProvider, get_settings
from sales_intelligence.pii import scrub_completion, scrub_prompt


def _load_pricing() -> dict[str, dict[str, float]]:
    pricing_path = Path(__file__).parents[4] / "_shared" / "pricing.json"
    try:
        with pricing_path.open() as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"pricing.json not found at {pricing_path}. "
            "Ensure _shared/pricing.json exists at the repo root."
        ) from None
    return {
        model: {"input": info["input"], "output": info["output"]}
        for model, info in data["models"].items()
    }


PRICING: dict[str, dict[str, float]] = _load_pricing()

# Provider server addresses for OTel server.address attribute
PROVIDER_SERVERS: dict[LLMProvider, str] = {
    "anthropic": "api.anthropic.com",
    "google": "generativelanguage.googleapis.com",
    "openai": "api.openai.com",
}

tracer = trace.get_tracer("gen_ai.client")
meter = metrics.get_meter("gen_ai.client")

# GenAI metrics per OpenTelemetry semantic conventions
# These are CUSTOM metrics - auto-instrumentation only provides HTTP metrics
# Custom metrics enable: token usage dashboards, cost tracking, model comparison
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
    name="gen_ai.client.cost",
    description="Cost of GenAI operations in USD",
    unit="usd",
)

# Additional metrics for Error & Retry Analysis dashboard
_retry_counter = meter.create_counter(
    name="gen_ai.client.retry.count",
    description="Number of retry attempts",
    unit="{retry}",
)
_fallback_counter = meter.create_counter(
    name="gen_ai.client.fallback.count",
    description="Number of fallback triggers",
    unit="{fallback}",
)
_error_counter = meter.create_counter(
    name="gen_ai.client.error.count",
    description="Number of errors by type",
    unit="{error}",
)


def _on_retry(retry_state: RetryCallState) -> None:
    """Callback invoked before each retry attempt."""
    provider = "unknown"
    if retry_state.args and len(retry_state.args) > 0:
        self_arg = retry_state.args[0]
        if hasattr(self_arg, "provider_name"):
            provider = self_arg.provider_name

    error_type = "unknown"
    if retry_state.outcome and retry_state.outcome.exception():
        error_type = type(retry_state.outcome.exception()).__name__

    _retry_counter.add(
        1,
        {
            "gen_ai.provider.name": provider,
            "error.type": error_type,
            "retry.attempt": retry_state.attempt_number,
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

    @abstractmethod
    def __init__(self, api_key: str) -> None:
        """Initialize provider with API key."""
        ...

    @abstractmethod
    async def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Generate completion from the LLM."""
        ...


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    provider_name: LLMProvider = "anthropic"
    server_address: str = PROVIDER_SERVERS["anthropic"]

    def __init__(self, api_key: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
    )
    async def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        import logging

        logger = logging.getLogger(__name__)

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
            "LLM response length: %d, stop_reason: %s, first100: %s",
            len(content),
            response.stop_reason,
            repr(content[:100]),
        )
        return LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            response_id=response.id,
            finish_reason=response.stop_reason,
        )


class GoogleProvider(BaseLLMProvider):
    """Google Gemini provider."""

    provider_name: LLMProvider = "google"
    server_address: str = PROVIDER_SERVERS["google"]

    def __init__(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
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

    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
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


def _create_provider(provider: LLMProvider, api_key: str) -> BaseLLMProvider:
    """Factory to create provider instance."""
    providers: dict[LLMProvider, type[BaseLLMProvider]] = {
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
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
    }
    return keys[provider]


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a model call."""
    pricing = PRICING.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


class LLMClient:
    """Provider-agnostic LLM client with full OTel GenAI instrumentation.

    Custom instrumentation is added on top of auto-instrumentation because:
    1. Auto (httpx): Captures HTTP request/response spans only
    2. Custom: Adds GenAI semantic attributes for model, tokens, cost tracking
    3. Custom: Records GenAI-specific metrics for dashboards and alerts
    4. Custom: Enables business context attribution (agent, campaign)
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._primary_provider = settings.llm_provider
        self._primary_model = settings.llm_model
        self._fallback_provider = settings.fallback_provider
        self._fallback_model = settings.fallback_model
        self._temperature = settings.default_temperature
        self._max_tokens = settings.default_max_tokens
        self._providers: dict[LLMProvider, BaseLLMProvider] = {}

    def _get_provider(self, provider: LLMProvider) -> BaseLLMProvider:
        """Lazy-load provider instance."""
        if provider not in self._providers:
            api_key = _get_api_key(provider)
            self._providers[provider] = _create_provider(provider, api_key)
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
        """Generate text with full OTel GenAI observability.

        Args:
            prompt: User prompt
            system: System instruction
            provider: LLM provider (defaults to settings.llm_provider)
            model: Model to use (defaults to settings.llm_model)
            temperature: Sampling temperature
            max_tokens: Max output tokens
            use_fallback: Whether to fallback to secondary provider on failure
            agent_name: Agent name for attribution (recorded in spans/metrics)
            campaign_id: Campaign ID for cost attribution

        Returns:
            Generated text content
        """
        provider = provider or self._primary_provider
        model = model or self._primary_model
        temperature = temperature if temperature is not None else self._temperature
        max_tokens = max_tokens or self._max_tokens

        llm_provider = self._get_provider(provider)

        # CUSTOM SPAN: OTel GenAI semantic conventions
        # Auto-instrumentation (httpx) only captures HTTP-level details
        # This span adds LLM-specific context for debugging and cost analysis
        with tracer.start_as_current_span(f"gen_ai.chat {model}") as span:
            # === REQUIRED attributes (OTel GenAI semconv) ===
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.provider.name", provider)

            # === CONDITIONALLY REQUIRED attributes ===
            span.set_attribute("gen_ai.request.model", model)

            # === RECOMMENDED attributes ===
            # server.address helps identify which endpoint was called
            span.set_attribute("server.address", llm_provider.server_address)
            span.set_attribute("gen_ai.request.temperature", temperature)
            span.set_attribute("gen_ai.request.max_tokens", max_tokens)

            # === CUSTOM attributes for business context ===
            # These enable cost attribution by agent and campaign in dashboards
            if agent_name:
                span.set_attribute("gen_ai.agent.name", agent_name)
            if campaign_id:
                span.set_attribute("campaign_id", campaign_id)

            # === OTel GenAI Prompt Event ===
            # Record prompt with PII scrubbed for safe telemetry
            # Per GenAI semconv: gen_ai.user.message event
            span.add_event(
                "gen_ai.user.message",
                attributes={
                    "gen_ai.prompt": scrub_prompt(prompt)[:1000],
                    "gen_ai.system_instructions": scrub_prompt(system)[:500],
                },
            )

            import time

            start_time = time.perf_counter()

            try:
                response = await llm_provider.generate(
                    model=model,
                    system=system,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                duration = time.perf_counter() - start_time

                # === RECOMMENDED response attributes ===
                # These help debug model behavior and track actual model used
                span.set_attribute("gen_ai.response.model", response.model)
                if response.response_id:
                    span.set_attribute("gen_ai.response.id", response.response_id)
                if response.finish_reason:
                    span.set_attribute("gen_ai.response.finish_reasons", [response.finish_reason])

                # === RECOMMENDED usage attributes ===
                # Critical for token tracking and cost calculation
                span.set_attribute("gen_ai.usage.input_tokens", response.input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.output_tokens)

                # === OTel GenAI Completion Event ===
                # Record completion with PII scrubbed for safe telemetry
                # Per GenAI semconv: gen_ai.assistant.message event
                span.add_event(
                    "gen_ai.assistant.message",
                    attributes={
                        "gen_ai.completion": scrub_completion(response.content)[:2000],
                    },
                )

                # Record metrics with proper attributes
                self._record_metrics(
                    provider=provider,
                    model=model,
                    response=response,
                    duration=duration,
                    agent_name=agent_name,
                    campaign_id=campaign_id,
                    span=span,
                )

                return response.content

            except Exception as e:
                span.record_exception(e)
                error_type = type(e).__name__
                span.set_attribute("error.type", error_type)

                # Track error metrics
                _error_counter.add(
                    1,
                    {
                        "gen_ai.provider.name": provider,
                        "gen_ai.request.model": model,
                        "error.type": error_type,
                    },
                )

                if use_fallback and provider != self._fallback_provider:
                    span.set_attribute("gen_ai.fallback.triggered", True)

                    # Track fallback trigger
                    _fallback_counter.add(
                        1,
                        {
                            "gen_ai.provider.name": provider,
                            "gen_ai.fallback.provider": self._fallback_provider,
                            "error.type": error_type,
                        },
                    )

                    return await self.generate(
                        prompt=prompt,
                        system=system,
                        provider=self._fallback_provider,
                        model=self._fallback_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        use_fallback=False,
                        agent_name=agent_name,
                        campaign_id=campaign_id,
                    )
                raise

    def _record_metrics(
        self,
        provider: LLMProvider,
        model: str,
        response: LLMResponse,
        duration: float,
        agent_name: str | None,
        campaign_id: str | None,
        span: Any,
    ) -> None:
        """Record GenAI metrics per OTel semantic conventions.

        CUSTOM METRICS: Auto-instrumentation provides HTTP metrics only.
        These GenAI-specific metrics enable:
        - Token usage dashboards (by model, agent, campaign)
        - Cost tracking and attribution
        - Operation duration analysis for optimization
        """
        # === REQUIRED metric attributes (OTel GenAI semconv) ===
        base_attrs: dict[str, Any] = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": provider,
        }

        # === CONDITIONALLY REQUIRED ===
        base_attrs["gen_ai.request.model"] = model

        # === RECOMMENDED ===
        base_attrs["server.address"] = PROVIDER_SERVERS[provider]
        base_attrs["gen_ai.response.model"] = response.model

        # Token usage histogram - separate input/output for analysis
        _token_usage.record(
            response.input_tokens,
            {**base_attrs, "gen_ai.token.type": "input"},
        )
        _token_usage.record(
            response.output_tokens,
            {**base_attrs, "gen_ai.token.type": "output"},
        )

        # Operation duration histogram
        _operation_duration.record(duration, base_attrs)

        # Cost tracking with business context for attribution
        cost = _calculate_cost(model, response.input_tokens, response.output_tokens)
        cost_attrs = {**base_attrs}
        if agent_name:
            cost_attrs["gen_ai.agent.name"] = agent_name
        if campaign_id:
            cost_attrs["campaign_id"] = campaign_id
        _cost_counter.add(cost, cost_attrs)

        # Also record cost on span for per-request visibility
        span.set_attribute("gen_ai.usage.cost_usd", cost)


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get singleton LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
