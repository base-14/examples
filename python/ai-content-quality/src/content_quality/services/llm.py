import json
import logging
import os
import re
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from llama_index.core import PromptTemplate
from llama_index.core.llms import LLM, ChatMessage
from opentelemetry import metrics, trace
from opentelemetry.trace import StatusCode
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
    name="gen_ai.client.cost",
    description="Cost of GenAI operations",
    unit="usd",
)

error_counter = meter.create_counter(
    name="gen_ai.client.error.count",
    description="GenAI operation errors",
    unit="1",
)

retry_counter = meter.create_counter(
    name="gen_ai.client.retry.count",
    description="GenAI operation retries",
    unit="1",
)

PROVIDER_SEMCONV_NAMES: dict[str, str] = {
    "openai": "openai",
    "google": "gcp.gemini",
    "anthropic": "anthropic",
}

PROVIDER_SERVERS: dict[str, str] = {
    "openai": "api.openai.com",
    "gcp.gemini": "generativelanguage.googleapis.com",
    "anthropic": "api.anthropic.com",
}


def _is_content_capture_enabled() -> bool:
    return (
        os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "").lower() == "true"
    )


PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-5.2": {"input": 1.75, "output": 14.0},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    # Google Gemini
    "gemini-3.0-flash-preview": {"input": 0.50, "output": 3.0},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # Anthropic
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
    "claude-opus-4-1-20250805": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.0},
}


def create_llm(
    provider: str = "openai",
    model: str = "gpt-4.1-nano",
    temperature: float = 0.3,
    api_key: str = "",
    timeout: float = 30.0,
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

    raise ValueError(f"Unknown LLM provider: {provider!r}. Choose from: openai, google, anthropic")


def _on_retry(retry_state: RetryCallState) -> None:
    client = retry_state.args[0] if retry_state.args else None
    model = getattr(client, "model", "unknown") if client else "unknown"
    provider = getattr(client, "provider", "unknown") if client else "unknown"
    attrs: dict[str, str | int] = {
        "gen_ai.request.model": model,
        "gen_ai.provider.name": provider,
    }
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is not None:
        attrs["error.type"] = type(exc).__name__
    attrs["retry.attempt"] = retry_state.attempt_number
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
    span.set_attribute("server.port", 443)
    span.set_attribute("gen_ai.output.type", "json")
    temperature = getattr(llm, "temperature", None)
    if temperature is not None:
        span.set_attribute("gen_ai.request.temperature", float(temperature))
    span.set_attribute("content.type", content_type)
    span.set_attribute("content.length", len(content))
    span.set_attribute("endpoint", endpoint)


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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_on_retry,
        reraise=True,
    )
    async def generate_structured(
        self,
        prompt_template: PromptTemplate,
        output_cls: type[BaseModel],
        content: str,
        content_type: str = "general",
        endpoint: str = "",
        system_prompt: str = "",
    ) -> BaseModel:
        model_name = self.llm.metadata.model_name
        server_address = PROVIDER_SERVERS.get(self.provider, "")

        with tracer.start_as_current_span(f"gen_ai.chat {model_name}") as span:
            _set_initial_span_attrs(
                span,
                self.llm,
                model_name,
                server_address,
                content_type,
                content,
                endpoint,
                self.provider,
            )

            start = time.perf_counter()

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
                if self.provider == "gcp.gemini":
                    achat_kwargs["generation_config"] = {
                        "response_mime_type": "application/json",
                        "response_schema": output_cls,
                    }
                chat_response = await self.llm.achat(messages, **achat_kwargs)

                duration = time.perf_counter() - start

                response_model, finish_reason = _set_response_attrs(chat_response, span, model_name)

                common_attrs = _build_common_attrs(
                    model_name, response_model, server_address, self.provider
                )
                span.set_attribute("gen_ai.client.operation.duration", duration)

                operation_duration.record(duration, common_attrs)
                _record_token_metrics(
                    chat_response, common_attrs, model_name, content_type, endpoint, span
                )
                if _is_content_capture_enabled():
                    _record_span_event(
                        span,
                        system_prompt,
                        formatted_prompt,
                        str(chat_response.message.content),
                        finish_reason,
                        event_attrs=_build_event_metadata(
                            model_name, response_model, server_address, chat_response, finish_reason
                        ),
                    )

                raw_content = _strip_markdown_json(str(chat_response.message.content))
                for parse_attempt in range(MAX_PARSE_RETRIES + 1):
                    try:
                        return output_cls.model_validate_json(raw_content)
                    except ValidationError as ve:
                        if parse_attempt < MAX_PARSE_RETRIES:
                            logger.warning(
                                "Structured output parse failed (attempt %d): %s",
                                parse_attempt + 1,
                                ve,
                            )
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
                            correction_response = await self.llm.achat(messages, **achat_kwargs)
                            raw_content = _strip_markdown_json(
                                str(correction_response.message.content)
                            )
                            continue
                        raise

                raise RuntimeError("Unreachable: parse loop exhausted")  # pragma: no cover

            except Exception as e:
                span.record_exception(e)
                span.set_status(StatusCode.ERROR, str(e))
                span.set_attribute("error.type", type(e).__name__)
                error_counter.add(
                    1,
                    {
                        "gen_ai.request.model": self.llm.metadata.model_name,
                        "gen_ai.provider.name": self.provider,
                        "error.type": type(e).__name__,
                    },
                )
                raise


def _raw_get(raw: object) -> Callable[[str], Any]:
    """Return a getter that works whether raw is a dict or an object."""
    if isinstance(raw, dict):
        return raw.get
    return lambda key, default=None: getattr(raw, key, default)


def _extract_raw_usage(raw: object) -> dict[str, Any]:
    """Extract usage dict from raw response (dict or object)."""
    if isinstance(raw, dict):
        usage = raw.get("usage")
        if isinstance(usage, dict):
            return usage
        if usage is not None:
            return {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
    elif raw is not None:
        usage = getattr(raw, "usage", None)
        if usage is not None:
            return {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
    return {}


def _extract_token_counts(additional: dict[str, Any], raw: object) -> tuple[int | None, int | None]:
    raw_usage = _extract_raw_usage(raw)
    input_tokens = (
        additional.get("prompt_tokens")
        or additional.get("input_tokens")
        or (additional.get("usage") or {}).get("input_tokens")
        or raw_usage.get("input_tokens")
    )
    output_tokens = (
        additional.get("completion_tokens")
        or additional.get("output_tokens")
        or (additional.get("usage") or {}).get("output_tokens")
        or raw_usage.get("output_tokens")
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
        attrs["server.port"] = 443
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

    if input_tokens is not None and output_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", int(input_tokens))
        span.set_attribute("gen_ai.usage.output_tokens", int(output_tokens))

        token_usage.record(input_tokens, {**common_attrs, "gen_ai.token.type": "input"})
        token_usage.record(output_tokens, {**common_attrs, "gen_ai.token.type": "output"})
        cost = _calculate_cost(model_name, int(input_tokens), int(output_tokens))
        cost_counter.add(cost, {**common_attrs, "content.type": content_type, "endpoint": endpoint})
        span.set_attribute("gen_ai.usage.cost_usd", cost)
    else:
        logger.warning(
            "Token usage unavailable from additional_kwargs -- "
            "token and cost metrics will not be recorded for this call"
        )


def _build_event_metadata(
    model_name: str,
    response_model: str,
    server_address: str,
    chat_response: object,
    finish_reason: str | None,
) -> dict[str, str | int | list[str]]:
    additional = getattr(chat_response, "additional_kwargs", None) or {}
    raw = getattr(chat_response, "raw", None)
    raw_get = _raw_get(raw)
    attrs: dict[str, str | int | list[str]] = {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": model_name,
        "gen_ai.response.model": response_model,
        "server.port": 443,
    }
    if server_address:
        attrs["server.address"] = server_address
    response_id = additional.get("id") or raw_get("id")
    if response_id:
        attrs["gen_ai.response.id"] = response_id
    if finish_reason:
        attrs["gen_ai.response.finish_reasons"] = [finish_reason]
    input_toks, output_toks = _extract_token_counts(additional, raw)
    if input_toks is not None:
        attrs["gen_ai.usage.input_tokens"] = int(input_toks)
    if output_toks is not None:
        attrs["gen_ai.usage.output_tokens"] = int(output_toks)
    return attrs


def _record_span_event(
    span: trace.Span,
    system_prompt: str,
    user_prompt: str,
    assistant_content: str,
    finish_reason: str | None = None,
    *,
    event_attrs: dict[str, str | int | list[str]] | None = None,
) -> None:
    attrs: dict[str, str | int | list[str]] = {}
    if event_attrs:
        attrs.update(event_attrs)
    if system_prompt:
        attrs["gen_ai.system_instructions"] = json.dumps(
            [{"type": "text", "content": scrub_pii(system_prompt)[:500]}]
        )
    attrs["gen_ai.input.messages"] = json.dumps(
        [{"role": "user", "parts": [{"type": "text", "content": scrub_pii(user_prompt)[:500]}]}]
    )
    output_msg: dict[str, object] = {
        "role": "assistant",
        "parts": [{"type": "text", "content": scrub_pii(assistant_content)[:500]}],
    }
    if finish_reason:
        output_msg["finish_reason"] = finish_reason
    attrs["gen_ai.output.messages"] = json.dumps([output_msg])
    span.add_event("gen_ai.client.inference.operation.details", attrs)


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = PRICING.get(model, {"input": 0.0, "output": 0.0})
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
    )
    fallback_llm: LLM | None = None
    if settings.fallback_provider and settings.fallback_provider != settings.llm_provider:
        fallback_llm = create_llm(
            provider=settings.fallback_provider,
            model=settings.fallback_model,
            temperature=settings.llm_temperature,
            api_key=api_keys.get(settings.fallback_provider, ""),
            timeout=settings.llm_timeout,
        )
    return LLMClient(
        provider=settings.llm_provider,
        model=settings.llm_model,
        llm=llm,
        fallback_provider=settings.fallback_provider,
        fallback_model=settings.fallback_model,
        fallback_llm=fallback_llm,
    )
