import logging
import time

import httpx
from llama_index.core import PromptTemplate
from llama_index.core.llms import LLM, ChatMessage
from opentelemetry import metrics, trace
from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from content_quality.pii import scrub_pii


logger = logging.getLogger(__name__)

MAX_PARSE_RETRIES = 2

_provider: str = "openai"

meter = metrics.get_meter("gen_ai.client")

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
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-3-5-20241022": {"input": 0.80, "output": 4.0},
}


def create_llm(
    provider: str = "openai",
    model: str = "gpt-4.1-nano",
    temperature: float = 0.3,
    api_key: str = "",
) -> LLM:
    global _provider
    _provider = provider

    if provider == "openai":
        from llama_index.llms.openai import OpenAI

        return OpenAI(model=model, temperature=temperature, api_key=api_key, timeout=30.0)

    if provider == "google":
        from llama_index.llms.google_genai import GoogleGenAI

        return GoogleGenAI(model=model, temperature=temperature, api_key=api_key)

    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic

        return Anthropic(model=model, temperature=temperature, api_key=api_key, timeout=30.0)

    raise ValueError(f"Unknown LLM provider: {provider!r}. Choose from: openai, google, anthropic")


def _on_retry(retry_state: RetryCallState) -> None:
    model = "unknown"
    if retry_state.args:
        metadata = getattr(retry_state.args[0], "metadata", None)
        if metadata is not None:
            model = str(metadata.model_name)
    retry_counter.add(
        1,
        {
            "gen_ai.request.model": model,
            "gen_ai.provider.name": _provider,
        },
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(
        (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)
    ),
    before_sleep=_on_retry,
    reraise=True,
)
async def generate_structured(
    llm: LLM,
    prompt_template: PromptTemplate,
    output_cls: type[BaseModel],
    content: str,
    content_type: str = "general",
    endpoint: str = "",
    system_prompt: str = "",
) -> BaseModel:
    tracer = trace.get_tracer("gen_ai.client")

    with tracer.start_as_current_span(f"content_analysis {endpoint.strip('/')}") as span:
        span.set_attribute("gen_ai.operation.name", "content_analysis")
        span.set_attribute("content.type", content_type)
        span.set_attribute("content.length", len(content))
        span.set_attribute("endpoint", endpoint)

        start = time.perf_counter()

        try:
            formatted_prompt = prompt_template.format(content=content)

            sllm = llm.as_structured_llm(output_cls=output_cls)
            messages: list[ChatMessage] = []
            if system_prompt:
                messages.append(ChatMessage(role="system", content=system_prompt))
            messages.append(ChatMessage(role="user", content=formatted_prompt))
            chat_response = await sllm.achat(messages)

            duration = time.perf_counter() - start

            model_name = llm.metadata.model_name
            common_attrs = {
                "gen_ai.request.model": model_name,
                "gen_ai.provider.name": _provider,
                "gen_ai.operation.name": "chat",
            }

            span.set_attribute("gen_ai.request.model", model_name)
            span.set_attribute("gen_ai.provider.name", _provider)
            span.set_attribute("gen_ai.client.operation.duration", duration)

            operation_duration.record(duration, common_attrs)
            _record_token_metrics(
                chat_response, common_attrs, model_name, content_type, endpoint, span
            )
            _record_span_events(
                span, system_prompt, formatted_prompt, str(chat_response.message.content)
            )

            raw_content = str(chat_response.message.content)
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
                        correction_response = await sllm.achat(messages)
                        raw_content = str(correction_response.message.content)
                        continue
                    raise

            raise RuntimeError("Unreachable: parse loop exhausted")  # pragma: no cover

        except Exception as e:
            span.record_exception(e)
            span.set_attribute("error.type", type(e).__name__)
            error_counter.add(
                1,
                {
                    "gen_ai.request.model": llm.metadata.model_name,
                    "error.type": type(e).__name__,
                },
            )
            raise


def _record_token_metrics(
    chat_response: object,
    common_attrs: dict[str, str],
    model_name: str,
    content_type: str,
    endpoint: str,
    span: trace.Span,
) -> None:
    additional = getattr(chat_response, "additional_kwargs", None) or {}
    input_tokens = additional.get("prompt_tokens") or additional.get("input_tokens")
    output_tokens = additional.get("completion_tokens") or additional.get("output_tokens")

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


def _record_span_events(
    span: trace.Span, system_prompt: str, user_prompt: str, assistant_content: str
) -> None:
    if system_prompt:
        span.add_event("gen_ai.system.message", {"content": scrub_pii(system_prompt)[:500]})
    span.add_event("gen_ai.user.message", {"content": scrub_pii(user_prompt)[:500]})
    span.add_event("gen_ai.assistant.message", {"content": scrub_pii(assistant_content)[:500]})


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = PRICING.get(model, {"input": 0.10, "output": 0.40})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
