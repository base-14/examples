"""LLM client over LlamaIndex, for Ollama, OpenAI, Anthropic and Gemini.

LlamaIndex's integrations call the provider SDKs, and the OpenTelemetry GenAI
instrumentations for those SDKs record a `chat {model}` span and the
`gen_ai.client.*` metrics for every call. Ollama is reached through its
OpenAI-compatible `/v1` endpoint, so the OpenAI instrumentation covers it. This
module adds what the instrumentations cannot know: the endpoint and content
behind a call, its cost, and the retry, fallback and error counters.
"""

import json
import logging
import re
from functools import lru_cache
from typing import Any

from llama_index.core import PromptTemplate
from llama_index.core.llms import LLM, ChatMessage
from opentelemetry import metrics, trace
from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from content_quality.genai_spans import LLMCallAttributes, llm_call_attributes
from content_quality.pricing import calculate_cost


logger = logging.getLogger(__name__)

MAX_PARSE_RETRIES = 2

_MARKDOWN_JSON_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def _strip_markdown_json(text: str) -> str:
    """Strip markdown code fences if present, pass through clean JSON as-is."""
    text = text.strip()
    m = _MARKDOWN_JSON_RE.match(text)
    return m.group(1).strip() if m else text


meter = metrics.get_meter("gen_ai.client")

cost_counter = meter.create_counter(
    name="base14.gen_ai.cost",
    description="Cost of GenAI operations",
    unit="usd",
)

error_counter = meter.create_counter(
    name="base14.gen_ai.error.count",
    description="GenAI operation errors",
    unit="{error}",
)

retry_counter = meter.create_counter(
    name="base14.gen_ai.retry.count",
    description="GenAI operation retries, excluding the initial attempt",
    unit="{retry}",
)

fallback_counter = meter.create_counter(
    name="base14.gen_ai.fallback.count",
    description="GenAI provider fallback count",
    unit="{fallback}",
)

PROVIDER_SEMCONV_NAMES: dict[str, str] = {
    "openai": "openai",
    "google": "gcp.gemini",
    "anthropic": "anthropic",
    "ollama": "ollama",
}


def create_llm(
    provider: str = "ollama",
    model: str = "qwen3.5:9B",
    temperature: float = 0.3,
    api_key: str = "",
    timeout: float = 30.0,
    ollama_base_url: str = "http://localhost:11434",
    ollama_context_window: int = 32768,
    ollama_reasoning: bool = False,
) -> LLM:
    """The SDKs' own retries are off, so each attempt is one span."""
    if provider == "openai":
        from llama_index.llms.openai import OpenAI

        return OpenAI(
            model=model, temperature=temperature, api_key=api_key, timeout=timeout, max_retries=0
        )

    if provider == "google":
        from llama_index.llms.google_genai import GoogleGenAI

        return GoogleGenAI(model=model, temperature=temperature, api_key=api_key, max_retries=0)

    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic

        return Anthropic(
            model=model, temperature=temperature, api_key=api_key, timeout=timeout, max_retries=0
        )

    if provider == "ollama":
        from llama_index.llms.openai_like import OpenAILike

        # Ollama's OpenAI-compatible endpoint, so the OpenAI instrumentation traces it.
        return OpenAILike(  # type: ignore[no-any-return]
            model=model,
            api_base=f"{ollama_base_url.rstrip('/')}/v1",
            api_key="ollama",
            is_chat_model=True,
            context_window=ollama_context_window,
            temperature=temperature,
            timeout=timeout,
            max_retries=0,
            additional_kwargs={} if ollama_reasoning else {"reasoning_effort": "none"},
        )

    raise ValueError(
        f"Unknown LLM provider: {provider!r}. Choose from: openai, google, anthropic, ollama"
    )


def _on_retry(retry_state: RetryCallState) -> None:
    kwargs = retry_state.kwargs or {}
    model = kwargs.get("model_name", "unknown")
    provider = kwargs.get("provider", "unknown")
    attrs: dict[str, str | int] = {
        "gen_ai.request.model": model,
        "gen_ai.provider.name": provider,
    }
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is not None:
        attrs["error.type"] = type(exc).__name__
    attrs["base14.retry.attempt"] = retry_state.attempt_number
    retry_counter.add(1, attrs)


async def _chat_and_parse(
    llm: LLM,
    messages: list[ChatMessage],
    achat_kwargs: dict[str, Any],
    output_cls: type[BaseModel],
    model_name: str,
    provider: str,
    content_type: str,
    endpoint: str,
) -> BaseModel:
    """Call the LLM and parse structured JSON, asking again on schema mismatch.

    Every call, including a correction, is its own `chat` span and its own cost.
    """
    chat_response = await llm.achat(messages, **achat_kwargs)
    output_content = str(chat_response.message.content)
    _record_cost(chat_response, model_name, provider, content_type, endpoint)

    raw_content = _strip_markdown_json(output_content)
    for parse_attempt in range(MAX_PARSE_RETRIES + 1):
        try:
            return output_cls.model_validate_json(raw_content)
        except ValidationError as ve:
            if parse_attempt >= MAX_PARSE_RETRIES:
                raise
            logger.warning("Structured output parse failed (attempt %d): %s", parse_attempt + 1, ve)
            messages.append(ChatMessage(role="assistant", content=raw_content))
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        f"Your response did not match the required schema. "
                        f"Error: {ve}\n"
                        "Please try again with valid JSON matching the schema."
                    ),
                )
            )
            correction_response = await llm.achat(messages, **achat_kwargs)
            _record_cost(correction_response, model_name, provider, content_type, endpoint)
            raw_content = _strip_markdown_json(str(correction_response.message.content))

    raise RuntimeError("Unreachable: parse loop exhausted")  # pragma: no cover


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=_on_retry,
    reraise=True,
)
async def _chat_and_parse_with_retry(
    *,
    llm: LLM,
    base_messages: list[ChatMessage],
    achat_kwargs: dict[str, Any],
    output_cls: type[BaseModel],
    model_name: str,
    provider: str,
    content_type: str,
    endpoint: str,
) -> BaseModel:
    """Retry the LLM call. Each attempt is its own `chat` span.

    Each retry attempt gets a fresh copy of base_messages, so a schema
    correction appended during a failed attempt's parse-retry loop does not
    leak into the next network-level retry attempt.
    """
    return await _chat_and_parse(
        llm,
        list(base_messages),
        achat_kwargs,
        output_cls,
        model_name,
        provider,
        content_type,
        endpoint,
    )


class LLMClient:
    def __init__(
        self,
        provider: str,
        model: str,
        llm: LLM,
        fallback_provider: str = "",
        fallback_model: str = "",
        fallback_llm: LLM | None = None,
    ) -> None:
        self.provider = PROVIDER_SEMCONV_NAMES.get(provider, provider)
        self.model = model
        self.llm = llm
        self.fallback_provider = (
            PROVIDER_SEMCONV_NAMES.get(fallback_provider, fallback_provider)
            if fallback_provider
            else ""
        )
        self.fallback_model = fallback_model
        self.fallback_llm = fallback_llm

    async def generate_structured(
        self,
        prompt_template: PromptTemplate,
        output_cls: type[BaseModel],
        content: str,
        content_type: str = "general",
        endpoint: str = "",
        system_prompt: str = "",
    ) -> BaseModel:
        try:
            return await self._generate_with_retry(
                prompt_template, output_cls, content, content_type, endpoint, system_prompt
            )
        except Exception as exc:
            if self.fallback_llm is None:
                raise
            self._record_fallback(exc)
            return await self._generate_with_retry(
                prompt_template,
                output_cls,
                content,
                content_type,
                endpoint,
                system_prompt,
                _override_llm=self.fallback_llm,
                _override_provider=self.fallback_provider,
            )

    def _record_fallback(self, exc: Exception) -> None:
        """Record the provider switch on the calling span without failing it."""
        error_type = type(exc).__qualname__
        attrs = {
            "gen_ai.provider.name": self.provider,
            "base14.gen_ai.fallback.provider": self.fallback_provider,
            "error.type": error_type,
        }

        span = trace.get_current_span()
        span.record_exception(exc)
        span.add_event("provider_fallback", attributes=attrs)
        span.set_attribute("gen_ai.fallback.triggered", True)

        fallback_counter.add(1, attrs)

    async def _generate_with_retry(
        self,
        prompt_template: PromptTemplate,
        output_cls: type[BaseModel],
        content: str,
        content_type: str = "general",
        endpoint: str = "",
        system_prompt: str = "",
        *,
        _override_llm: LLM | None = None,
        _override_provider: str = "",
    ) -> BaseModel:
        llm = _override_llm if _override_llm is not None else self.llm
        provider = _override_provider or self.provider
        model_name = llm.metadata.model_name

        formatted_prompt = prompt_template.format(content=content)
        schema_json = json.dumps(output_cls.model_json_schema(), indent=2)
        json_instruction = f"Respond ONLY with valid JSON matching this schema:\n{schema_json}"
        full_system = (
            f"{system_prompt}\n\n{json_instruction}" if system_prompt else json_instruction
        )
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=full_system),
            ChatMessage(role="user", content=formatted_prompt),
        ]
        achat_kwargs: dict[str, Any] = {}
        if provider == "gcp.gemini":
            achat_kwargs["generation_config"] = {
                "response_mime_type": "application/json",
                "response_schema": output_cls,
            }

        call = LLMCallAttributes(
            provider=provider,
            endpoint=endpoint,
            content_type=content_type,
            content_length=len(content),
        )
        try:
            with llm_call_attributes(call):
                return await _chat_and_parse_with_retry(
                    llm=llm,
                    base_messages=messages,
                    achat_kwargs=achat_kwargs,
                    output_cls=output_cls,
                    model_name=model_name,
                    provider=provider,
                    content_type=content_type,
                    endpoint=endpoint,
                )
        except Exception as e:
            error_counter.add(
                1,
                {
                    "gen_ai.request.model": model_name,
                    "gen_ai.provider.name": provider,
                    "error.type": type(e).__name__,
                },
            )
            raise


def _extract_raw_usage(raw: object) -> dict[str, Any]:
    """Extract a normalized {input_tokens, output_tokens} dict from a raw response.

    Providers name usage fields differently: Ollama and OpenAI-style raw dicts use
    prompt_tokens/completion_tokens, Anthropic's usage object uses
    input_tokens/output_tokens. Both are normalized to the same two keys here.
    """
    usage = raw.get("usage") if isinstance(raw, dict) else getattr(raw, "usage", None)
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return {
            "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
            "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
        }
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def _extract_token_counts(additional: dict[str, Any], raw: object) -> tuple[int | None, int | None]:
    raw_usage = _extract_raw_usage(raw)
    nested_usage: dict[str, Any] = additional.get("usage") or {}
    input_tokens = next(
        (
            v
            for v in (
                additional.get("prompt_tokens"),
                additional.get("input_tokens"),
                nested_usage.get("input_tokens"),
                raw_usage.get("input_tokens"),
            )
            if v is not None
        ),
        None,
    )
    output_tokens = next(
        (
            v
            for v in (
                additional.get("completion_tokens"),
                additional.get("output_tokens"),
                nested_usage.get("output_tokens"),
                raw_usage.get("output_tokens"),
            )
            if v is not None
        ),
        None,
    )
    return input_tokens, output_tokens


def _record_cost(
    chat_response: object,
    model_name: str,
    provider: str,
    content_type: str,
    endpoint: str,
) -> None:
    """Record the call's cost for dashboards. The span gets its cost in the exporter."""
    additional = getattr(chat_response, "additional_kwargs", None) or {}
    raw = getattr(chat_response, "raw", None)
    input_tokens, output_tokens = _extract_token_counts(additional, raw)
    if input_tokens is None and output_tokens is None:
        return
    cost_counter.add(
        calculate_cost(model_name, int(input_tokens or 0), int(output_tokens or 0)),
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": model_name,
            "base14.content.type": content_type,
            "base14.endpoint": endpoint,
        },
    )


@lru_cache
def get_llm_client() -> LLMClient:
    from content_quality.config import get_settings

    settings = get_settings()
    api_keys = {
        "openai": settings.openai_api_key,
        "google": settings.google_api_key,
        "anthropic": settings.anthropic_api_key,
    }
    llm = create_llm(
        provider=settings.llm_provider,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=api_keys.get(settings.llm_provider, ""),
        timeout=settings.llm_timeout,
        ollama_base_url=settings.ollama_base_url,
        ollama_context_window=settings.ollama_context_window,
        ollama_reasoning=settings.ollama_reasoning,
    )
    fallback_llm: LLM | None = None
    if settings.fallback_provider and settings.fallback_provider != settings.llm_provider:
        fallback_llm = create_llm(
            provider=settings.fallback_provider,
            model=settings.fallback_model,
            temperature=settings.llm_temperature,
            api_key=api_keys.get(settings.fallback_provider, ""),
            timeout=settings.llm_timeout,
            ollama_base_url=settings.ollama_base_url,
            ollama_context_window=settings.ollama_context_window,
            ollama_reasoning=settings.ollama_reasoning,
        )
    return LLMClient(
        provider=settings.llm_provider,
        model=settings.llm_model,
        llm=llm,
        fallback_provider=settings.fallback_provider,
        fallback_model=settings.fallback_model,
        fallback_llm=fallback_llm,
    )
