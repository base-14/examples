import json
import logging
import os
import re
import time
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from llama_index.core import PromptTemplate
from llama_index.core.llms import LLM, ChatMessage
from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from content_quality.pii import scrub_pii


logger = logging.getLogger(__name__)

MAX_PARSE_RETRIES = 2

PROMPT_MAX_CHARS = 1000
SYSTEM_MAX_CHARS = 500
COMPLETION_MAX_CHARS = 2000

_MARKDOWN_JSON_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def _strip_markdown_json(text: str) -> str:
    """Strip markdown code fences if present, pass through clean JSON as-is."""
    text = text.strip()
    m = _MARKDOWN_JSON_RE.match(text)
    return m.group(1).strip() if m else text


meter = metrics.get_meter("gen_ai.client")
tracer = trace.get_tracer("gen_ai.client")

token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    description="Number of tokens used",
    unit="{token}",
)

operation_duration = meter.create_histogram(
    name="gen_ai.client.operation.duration",
    description="GenAI operation duration",
    unit="s",
)

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

PROVIDER_SERVERS: dict[str, str] = {
    "openai": "api.openai.com",
    "gcp.gemini": "generativelanguage.googleapis.com",
    "anthropic": "api.anthropic.com",
    "ollama": "localhost",
}

PROVIDER_PORTS: dict[str, int] = {
    "openai": 443,
    "gcp.gemini": 443,
    "anthropic": 443,
    "ollama": 11434,
}


def _is_content_capture_enabled() -> bool:
    return (
        os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "").lower() == "true"
    )


def _load_pricing() -> dict[str, dict[str, float]]:
    this_file = Path(__file__)
    for depth in (5, 3):
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
    if provider == "openai":
        from llama_index.llms.openai import OpenAI

        return OpenAI(model=model, temperature=temperature, api_key=api_key, timeout=timeout)

    if provider == "google":
        from llama_index.llms.google_genai import GoogleGenAI

        return GoogleGenAI(model=model, temperature=temperature, api_key=api_key)

    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic

        return Anthropic(model=model, temperature=temperature, api_key=api_key, timeout=timeout)

    if provider == "ollama":
        from llama_index.llms.ollama import Ollama

        return Ollama(  # type: ignore[no-any-return]
            model=model,
            base_url=ollama_base_url,
            context_window=ollama_context_window,
            thinking=ollama_reasoning,
            temperature=temperature,
            request_timeout=timeout,
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


def _set_initial_span_attrs(
    span: trace.Span,
    llm: LLM,
    model_name: str,
    server_address: str,
    content_type: str,
    content: str,
    endpoint: str,
    provider: str = "",
) -> None:
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.request.model", model_name)
    span.set_attribute("gen_ai.provider.name", provider)
    if server_address:
        span.set_attribute("server.address", server_address)
    span.set_attribute("server.port", PROVIDER_PORTS.get(provider, 443))
    span.set_attribute("gen_ai.output.type", "json")
    temperature = getattr(llm, "temperature", None)
    if temperature is not None:
        span.set_attribute("gen_ai.request.temperature", float(temperature))
    span.set_attribute("base14.content.type", content_type)
    span.set_attribute("base14.content.length", len(content))
    span.set_attribute("base14.endpoint", endpoint)


def _emit_content_event(
    span: trace.Span,
    prompt: str,
    system_prompt: str,
    output_content: str | None,
) -> None:
    """Emit the inference content event when content capture is switched on.

    Content is PII-scrubbed and truncated. The system prompt goes on
    gen_ai.system_instructions, not into the input messages.
    """
    if not _is_content_capture_enabled():
        return

    attributes: dict[str, str] = {
        "gen_ai.input.messages": scrub_pii(prompt)[:PROMPT_MAX_CHARS],
    }
    if system_prompt:
        attributes["gen_ai.system_instructions"] = scrub_pii(system_prompt)[:SYSTEM_MAX_CHARS]
    if output_content is not None:
        attributes["gen_ai.output.messages"] = scrub_pii(output_content)[:COMPLETION_MAX_CHARS]

    span.add_event("gen_ai.client.inference.operation.details", attributes)


async def _chat_and_parse(
    llm: LLM,
    messages: list[ChatMessage],
    achat_kwargs: dict[str, Any],
    output_cls: type[BaseModel],
    span: trace.Span,
    model_name: str,
    server_address: str,
    provider: str,
    content_type: str,
    endpoint: str,
) -> tuple[BaseModel, str]:
    """Call the LLM and parse structured JSON, retrying on schema mismatch.

    Returns the parsed result and the last raw response content, for the
    inference content event.
    """
    chat_response = await llm.achat(messages, **achat_kwargs)
    output_content = str(chat_response.message.content)

    response_model, _ = _set_response_attrs(chat_response, span, model_name)
    common_attrs = _build_common_attrs(model_name, response_model, server_address, provider)
    _record_token_metrics(chat_response, common_attrs, model_name, content_type, endpoint, span)

    raw_content = _strip_markdown_json(output_content)
    for parse_attempt in range(MAX_PARSE_RETRIES + 1):
        try:
            return output_cls.model_validate_json(raw_content), output_content
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
            output_content = str(correction_response.message.content)
            raw_content = _strip_markdown_json(output_content)

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
    span: trace.Span,
    model_name: str,
    server_address: str,
    provider: str,
    content_type: str,
    endpoint: str,
) -> tuple[BaseModel, str]:
    """Retry the LLM call transparently within the caller's span.

    Each retry attempt gets a fresh copy of base_messages, so a schema
    correction appended during a failed attempt's parse-retry loop does not
    leak into the next network-level retry attempt.
    """
    return await _chat_and_parse(
        llm,
        list(base_messages),
        achat_kwargs,
        output_cls,
        span,
        model_name,
        server_address,
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
        server_address = PROVIDER_SERVERS.get(provider, "")

        with tracer.start_as_current_span(f"chat {model_name}", kind=SpanKind.CLIENT) as span:
            _set_initial_span_attrs(
                span,
                llm,
                model_name,
                server_address,
                content_type,
                content,
                endpoint,
                provider,
            )

            start = time.perf_counter()
            error_type: str | None = None
            formatted_prompt = ""
            output_content: str | None = None

            try:
                formatted_prompt = prompt_template.format(content=content)

                schema_json = json.dumps(output_cls.model_json_schema(), indent=2)
                json_instruction = (
                    f"Respond ONLY with valid JSON matching this schema:\n{schema_json}"
                )
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

                result, output_content = await _chat_and_parse_with_retry(
                    llm=llm,
                    base_messages=messages,
                    achat_kwargs=achat_kwargs,
                    output_cls=output_cls,
                    span=span,
                    model_name=model_name,
                    server_address=server_address,
                    provider=provider,
                    content_type=content_type,
                    endpoint=endpoint,
                )
                return result

            except Exception as e:
                error_type = type(e).__name__
                span.record_exception(e)
                span.set_attribute("error.type", error_type)
                span.set_status(StatusCode.ERROR, str(e))
                error_counter.add(
                    1,
                    {
                        "gen_ai.request.model": model_name,
                        "gen_ai.provider.name": provider,
                        "error.type": error_type,
                    },
                )
                raise

            finally:
                duration = time.perf_counter() - start
                duration_attrs: dict[str, str | int] = {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": provider,
                    "gen_ai.request.model": model_name,
                }
                if error_type:
                    duration_attrs["error.type"] = error_type
                operation_duration.record(duration, duration_attrs)
                _emit_content_event(span, formatted_prompt, system_prompt, output_content)


def _raw_get(raw: object) -> Callable[[str], Any]:
    """Return a getter that works whether raw is a dict or an object."""
    if isinstance(raw, dict):
        return raw.get
    return lambda key, default=None: getattr(raw, key, default)  # type: ignore[misc]


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


def _set_response_attrs(
    chat_response: object, span: trace.Span, model_name: str
) -> tuple[str, str | None]:
    additional = getattr(chat_response, "additional_kwargs", None) or {}
    raw = getattr(chat_response, "raw", None)
    raw_get = _raw_get(raw)
    response_model = additional.get("model") or raw_get("model") or model_name
    span.set_attribute("gen_ai.response.model", response_model)
    response_id = additional.get("id") or raw_get("id")
    if response_id:
        span.set_attribute("gen_ai.response.id", response_id)
    finish_reason = (
        additional.get("finish_reason") or additional.get("stop_reason") or raw_get("stop_reason")
    )
    if finish_reason:
        span.set_attribute("gen_ai.response.finish_reasons", [finish_reason])
    return response_model, finish_reason


def _build_common_attrs(
    model_name: str, response_model: str, server_address: str, provider: str = ""
) -> dict[str, str | int]:
    attrs: dict[str, str | int] = {
        "gen_ai.request.model": model_name,
        "gen_ai.provider.name": provider,
        "gen_ai.operation.name": "chat",
        "gen_ai.response.model": response_model,
    }
    if server_address:
        attrs["server.address"] = server_address
        attrs["server.port"] = PROVIDER_PORTS.get(provider, 443)
    return attrs


def _record_token_metrics(
    chat_response: object,
    common_attrs: dict[str, str | int],
    model_name: str,
    content_type: str,
    endpoint: str,
    span: trace.Span,
) -> None:
    additional = getattr(chat_response, "additional_kwargs", None) or {}
    raw = getattr(chat_response, "raw", None)
    input_tokens, output_tokens = _extract_token_counts(additional, raw)

    if input_tokens is None and output_tokens is None:
        logger.warning(
            "Token usage unavailable from additional_kwargs -- "
            "token and cost metrics will not be recorded for this call"
        )
        return

    if input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", int(input_tokens))
        token_usage.record(input_tokens, {**common_attrs, "gen_ai.token.type": "input"})
    if output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", int(output_tokens))
        token_usage.record(output_tokens, {**common_attrs, "gen_ai.token.type": "output"})

    cost = _calculate_cost(model_name, int(input_tokens or 0), int(output_tokens or 0))
    cost_counter.add(
        cost, {**common_attrs, "base14.content.type": content_type, "base14.endpoint": endpoint}
    )
    span.set_attribute("base14.gen_ai.cost_usd", cost)


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
    pricing = PRICING.get(model) or PRICING.get(
        _normalize_model_id(model), {"input": 0.0, "output": 0.0}
    )
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


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
