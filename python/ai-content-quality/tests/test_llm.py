import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from llama_index.core.llms import ChatMessage
from pydantic import BaseModel, ValidationError

import content_quality.services.llm as llm_mod
from content_quality.pricing import PRICING, calculate_cost
from content_quality.services.llm import (
    LLMClient,
    _chat_and_parse,
    _extract_raw_usage,
    _extract_token_counts,
    _on_retry,
    _strip_markdown_json,
    create_llm,
)


class FakeResult(BaseModel):
    answer: str


def _make_llm(model_name: str = "gpt-4.1-nano", temperature: float = 0.3) -> MagicMock:
    llm = MagicMock()
    llm.metadata.model_name = model_name
    llm.temperature = temperature
    return llm


def _make_client(
    model_name: str = "gpt-4.1-nano",
    temperature: float = 0.3,
    provider: str = "openai",
) -> LLMClient:
    llm = _make_llm(model_name, temperature)
    return LLMClient(
        provider=provider,
        model=model_name,
        llm=llm,
        fallback_provider="google",
        fallback_model="gemini-2.5-flash-lite",
        fallback_llm=None,
    )


def _make_chat_response(
    content: str = '{"answer": "yes"}',
    input_tokens: int | None = 100,
    output_tokens: int | None = 50,
    response_model: str | None = None,
    response_id: str | None = None,
    finish_reason: str | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.message.content = content
    kwargs: dict[str, object] = {}
    if input_tokens is not None:
        kwargs["prompt_tokens"] = input_tokens
    if output_tokens is not None:
        kwargs["completion_tokens"] = output_tokens
    if response_model is not None:
        kwargs["model"] = response_model
    if response_id is not None:
        kwargs["id"] = response_id
    if finish_reason is not None:
        kwargs["finish_reason"] = finish_reason
    resp.additional_kwargs = kwargs
    resp.raw = None
    return resp


def _make_prompt_template(template: str = "Analyze: {content}") -> MagicMock:
    pt = MagicMock()
    pt.format.return_value = "Analyze: test content"
    return pt


# ---------------------------------------------------------------------------
# calculate_cost
# ---------------------------------------------------------------------------


def test_calculate_cost_known_model() -> None:
    assert calculate_cost("gpt-4.1", 1_000_000, 0) == pytest.approx(2.0)


def test_calculate_cost_dash_minor_anthropic_id() -> None:
    assert calculate_cost("claude-opus-4-6", 0, 0) == 0.0
    assert calculate_cost("claude-opus-4-6", 1_000_000, 0) == pytest.approx(
        PRICING["claude-opus-4.6"]["input"]
    )


def test_calculate_cost_unknown_model_is_zero() -> None:
    assert calculate_cost("qwen3.5:9B", 1000, 1000) == 0.0


def test_pricing_loaded_from_shared_json() -> None:
    assert PRICING["gpt-4.1"]["input"] == pytest.approx(2.0)
    assert PRICING["gpt-4.1"]["output"] == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# _extract_raw_usage / _raw_get - Anthropic-style raw dict responses
# ---------------------------------------------------------------------------


def test_extract_raw_usage_from_dict_with_dict_usage() -> None:
    raw = {"usage": {"input_tokens": 100, "output_tokens": 50}}
    assert _extract_raw_usage(raw) == {"input_tokens": 100, "output_tokens": 50}


def test_extract_raw_usage_from_dict_with_object_usage() -> None:
    usage = MagicMock()
    usage.input_tokens = 200
    usage.output_tokens = 80
    raw = {"usage": usage}
    result = _extract_raw_usage(raw)
    assert result["input_tokens"] == 200
    assert result["output_tokens"] == 80


def test_extract_raw_usage_from_object_with_usage() -> None:
    usage = MagicMock()
    usage.input_tokens = 300
    usage.output_tokens = 120
    raw = MagicMock()
    raw.usage = usage
    result = _extract_raw_usage(raw)
    assert result["input_tokens"] == 300
    assert result["output_tokens"] == 120


def test_extract_raw_usage_from_dict_with_prompt_completion_tokens() -> None:
    """Ollama's raw response nests usage as prompt_tokens/completion_tokens."""
    raw = {"usage": {"prompt_tokens": 40, "completion_tokens": 15, "total_tokens": 55}}
    assert _extract_raw_usage(raw) == {"input_tokens": 40, "output_tokens": 15}


def test_extract_raw_usage_returns_empty_for_none() -> None:
    assert _extract_raw_usage(None) == {}


def test_extract_raw_usage_returns_empty_for_dict_without_usage() -> None:
    assert _extract_raw_usage({"id": "msg_123", "model": "claude"}) == {}


# ---------------------------------------------------------------------------
# _extract_token_counts - zero-value handling
# ---------------------------------------------------------------------------


def test_extract_token_counts_returns_zero_not_none() -> None:
    """0 tokens is a valid value and must not be skipped by falsy or-chain."""
    additional = {"prompt_tokens": 0, "completion_tokens": 0}
    input_tokens, output_tokens = _extract_token_counts(additional, None)
    assert input_tokens == 0
    assert output_tokens == 0


def test_extract_token_counts_prefers_first_non_none_key() -> None:
    additional = {"prompt_tokens": 10, "input_tokens": 99}
    input_tokens, _ = _extract_token_counts(additional, None)
    assert input_tokens == 10


def test_extract_token_counts_falls_back_to_raw_usage() -> None:
    raw = {"usage": {"input_tokens": 42, "output_tokens": 21}}
    input_tokens, output_tokens = _extract_token_counts({}, raw)
    assert input_tokens == 42
    assert output_tokens == 21


def test_extract_token_counts_returns_none_when_absent() -> None:
    input_tokens, output_tokens = _extract_token_counts({}, None)
    assert input_tokens is None
    assert output_tokens is None


# ---------------------------------------------------------------------------
# _strip_markdown_json
# ---------------------------------------------------------------------------


def test_strip_markdown_json_with_json_fence() -> None:
    raw = '```json\n{"answer": "yes"}\n```'
    assert _strip_markdown_json(raw) == '{"answer": "yes"}'


def test_strip_markdown_json_with_plain_fence() -> None:
    raw = '```\n{"answer": "yes"}\n```'
    assert _strip_markdown_json(raw) == '{"answer": "yes"}'


def test_strip_markdown_json_passthrough_clean_json() -> None:
    raw = '{"answer": "yes"}'
    assert _strip_markdown_json(raw) == '{"answer": "yes"}'


def test_strip_markdown_json_strips_whitespace() -> None:
    raw = '  ```json\n  {"answer": "yes"}  \n```  '
    assert _strip_markdown_json(raw) == '{"answer": "yes"}'


# ---------------------------------------------------------------------------
# _on_retry
# ---------------------------------------------------------------------------


def test_on_retry_increments_counter_with_error_and_attempt() -> None:
    mock_counter = MagicMock()
    retry_state = MagicMock()
    retry_state.args = ()
    retry_state.kwargs = {"model_name": "gpt-4.1-mini", "provider": "openai"}
    retry_state.outcome.exception.return_value = httpx.ConnectError("conn refused")
    retry_state.attempt_number = 1

    with patch.object(llm_mod, "retry_counter", mock_counter):
        _on_retry(retry_state)

    attrs = mock_counter.add.call_args.args[1]
    assert attrs["gen_ai.request.model"] == "gpt-4.1-mini"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert attrs["error.type"] == "ConnectError"
    assert attrs["base14.retry.attempt"] == 1


def test_on_retry_handles_missing_kwargs() -> None:
    mock_counter = MagicMock()
    retry_state = MagicMock()
    retry_state.args = ()
    retry_state.kwargs = {}
    retry_state.outcome.exception.return_value = None
    retry_state.attempt_number = 2

    with patch.object(llm_mod, "retry_counter", mock_counter):
        _on_retry(retry_state)

    attrs = mock_counter.add.call_args.args[1]
    assert attrs["gen_ai.request.model"] == "unknown"
    assert attrs["base14.retry.attempt"] == 2


# ---------------------------------------------------------------------------
# generate_structured - behaviour over a mocked LlamaIndex LLM
# ---------------------------------------------------------------------------


def _client_with(llm: MagicMock, provider: str = "openai") -> LLMClient:
    return LLMClient(provider=provider, model=llm.metadata.model_name, llm=llm)


async def test_generate_returns_parsed_pydantic_model() -> None:
    llm = _make_llm()
    llm.achat = AsyncMock(return_value=_make_chat_response(content='{"answer": "42"}'))

    with patch.object(llm_mod, "cost_counter", MagicMock()):
        result = await _client_with(llm).generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    assert result.answer == "42"


async def test_generate_passes_system_prompt_and_schema_first() -> None:
    llm = _make_llm()
    llm.achat = AsyncMock(return_value=_make_chat_response())

    with patch.object(llm_mod, "cost_counter", MagicMock()):
        await _client_with(llm).generate_structured(
            _make_prompt_template(),
            FakeResult,
            "test",
            endpoint="/review",
            system_prompt="Be helpful",
        )

    messages = llm.achat.call_args.args[0]
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "Be helpful" in messages[0].content
    assert "JSON" in messages[0].content
    assert messages[1].role == "user"


async def test_generate_records_cost_counter() -> None:
    llm = _make_llm("gpt-4.1")
    llm.achat = AsyncMock(return_value=_make_chat_response(input_tokens=1_000_000, output_tokens=0))
    cost = MagicMock()

    with patch.object(llm_mod, "cost_counter", cost):
        await _client_with(llm).generate_structured(
            _make_prompt_template(), FakeResult, "test", content_type="blog", endpoint="/review"
        )

    value, attrs = cost.add.call_args.args
    assert value == pytest.approx(2.0)
    assert attrs["gen_ai.request.model"] == "gpt-4.1"
    assert attrs["base14.content.type"] == "blog"
    assert attrs["base14.endpoint"] == "/review"


async def test_generate_skips_cost_when_tokens_unavailable() -> None:
    llm = _make_llm()
    llm.achat = AsyncMock(return_value=_make_chat_response(input_tokens=None, output_tokens=None))
    cost = MagicMock()

    with patch.object(llm_mod, "cost_counter", cost):
        await _client_with(llm).generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    cost.add.assert_not_called()


async def test_generate_error_increments_error_counter() -> None:
    llm = _make_llm("gpt-4.1-mini")
    llm.achat = AsyncMock(side_effect=ValueError("bad response"))
    errors = MagicMock()

    with (
        patch.object(llm_mod, "error_counter", errors),
        patch.object(llm_mod, "_chat_and_parse_with_retry", _no_retry),
        pytest.raises(ValueError, match="bad response"),
    ):
        await _client_with(llm).generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    errors.add.assert_called_once_with(
        1,
        {
            "gen_ai.request.model": "gpt-4.1-mini",
            "gen_ai.provider.name": "openai",
            "error.type": "ValueError",
        },
    )


async def _no_retry(**kwargs: object) -> BaseModel:
    kwargs["messages"] = list(kwargs.pop("base_messages"))  # type: ignore[arg-type]
    return await _chat_and_parse(
        kwargs["llm"],  # type: ignore[arg-type]
        kwargs["messages"],  # type: ignore[arg-type]
        kwargs["achat_kwargs"],  # type: ignore[arg-type]
        kwargs["output_cls"],  # type: ignore[arg-type]
        kwargs["model_name"],  # type: ignore[arg-type]
        kwargs["provider"],  # type: ignore[arg-type]
        kwargs["content_type"],  # type: ignore[arg-type]
        kwargs["endpoint"],  # type: ignore[arg-type]
    )


async def test_generate_retry_increments_retry_counter() -> None:
    llm = _make_llm()
    llm.achat = AsyncMock(
        side_effect=[httpx.ConnectError("connection refused"), _make_chat_response()]
    )
    retries = MagicMock()

    with (
        patch.object(llm_mod, "retry_counter", retries),
        patch.object(llm_mod, "cost_counter", MagicMock()),
    ):
        result = await _client_with(llm).generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    retries.add.assert_called_once()
    retry_attrs = retries.add.call_args.args[1]
    assert retry_attrs["error.type"] == "ConnectError"
    assert retry_attrs["base14.retry.attempt"] == 1


async def test_generate_asks_again_on_validation_error() -> None:
    llm = _make_llm()
    llm.achat = AsyncMock(
        side_effect=[
            _make_chat_response(content='{"wrong_field": "oops"}'),
            _make_chat_response(content='{"answer": "fixed"}'),
        ]
    )

    with patch.object(llm_mod, "cost_counter", MagicMock()):
        result = await _client_with(llm).generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    assert result.answer == "fixed"
    assert llm.achat.call_count == 2
    correction = llm.achat.call_args.args[0]
    assert any(m.role == "user" and "schema" in str(m.content).lower() for m in correction)


async def test_chat_and_parse_raises_after_max_parse_retries() -> None:
    llm = _make_llm()
    llm.achat = AsyncMock(return_value=_make_chat_response(content='{"wrong": "data"}'))

    with patch.object(llm_mod, "cost_counter", MagicMock()), pytest.raises(ValidationError):
        await _chat_and_parse(
            llm,
            [ChatMessage(role="system", content="schema"), ChatMessage(role="user", content="x")],
            {},
            FakeResult,
            "gpt-4.1-nano",
            "openai",
            "general",
            "/review",
        )

    assert llm.achat.call_count == 3  # initial + 2 corrections


async def test_generate_uses_fallback_when_primary_fails() -> None:
    primary = _make_llm()
    primary.achat = AsyncMock(side_effect=RuntimeError("primary down"))
    fallback = _make_llm("gemini-2.5-flash-lite")
    fallback.achat = AsyncMock(
        return_value=_make_chat_response(content='{"answer": "from fallback"}')
    )
    client = LLMClient(
        provider="openai",
        model="gpt-4.1-nano",
        llm=primary,
        fallback_provider="google",
        fallback_model="gemini-2.5-flash-lite",
        fallback_llm=fallback,
    )
    fallbacks = MagicMock()

    with (
        patch.object(llm_mod, "fallback_counter", fallbacks),
        patch.object(llm_mod, "cost_counter", MagicMock()),
        patch.object(llm_mod, "_chat_and_parse_with_retry", _no_retry),
    ):
        result = await client.generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    assert result.answer == "from fallback"
    fallbacks.add.assert_called_once_with(
        1,
        {
            "gen_ai.provider.name": "openai",
            "base14.gen_ai.fallback.provider": "gcp.gemini",
            "error.type": "RuntimeError",
        },
    )


async def test_generate_raises_when_no_fallback_configured() -> None:
    llm = _make_llm()
    llm.achat = AsyncMock(side_effect=RuntimeError("primary down"))

    with (
        patch.object(llm_mod, "_chat_and_parse_with_retry", _no_retry),
        pytest.raises(RuntimeError, match="primary down"),
    ):
        await _client_with(llm).generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )


# ---------------------------------------------------------------------------
# create_llm
# ---------------------------------------------------------------------------


def test_create_llm_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm(provider="unknown_provider")


def test_create_llm_ollama_uses_the_openai_compatible_endpoint() -> None:
    llm = create_llm(
        provider="ollama",
        model="qwen3.5:9B",
        ollama_base_url="http://my-ollama:11434",
        ollama_context_window=16384,
    )
    assert type(llm).__name__ == "OpenAILike"
    assert llm.api_base == "http://my-ollama:11434/v1"
    assert llm.context_window == 16384
    assert llm.max_retries == 0
    assert llm.additional_kwargs == {"reasoning_effort": "none"}


def test_create_llm_ollama_keeps_reasoning_when_asked() -> None:
    llm = create_llm(provider="ollama", ollama_reasoning=True)
    assert llm.additional_kwargs == {}


# ---------------------------------------------------------------------------
# The OpenAI instrumentation's spans, through LlamaIndex and a mock transport
# ---------------------------------------------------------------------------


def _ollama_completion(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "qwen3.5:9B",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


def _ollama_llm(content: str) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ollama_completion(content))

    llm = create_llm(provider="ollama", model="qwen3.5:9B")
    llm._async_http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[attr-defined]
    return llm


async def test_chat_span_carries_request_context_and_ollama_provider(span_exporter) -> None:
    llm = _ollama_llm(json.dumps({"answer": "yes"}))
    client = LLMClient(provider="ollama", model="qwen3.5:9B", llm=llm)  # type: ignore[arg-type]

    with patch.object(llm_mod, "cost_counter", MagicMock()):
        await client.generate_structured(
            _make_prompt_template(),
            FakeResult,
            "four words of text",
            content_type="blog",
            endpoint="/review",
        )

    (span,) = [s for s in span_exporter.get_finished_spans() if s.name == "chat qwen3.5:9B"]
    assert span.instrumentation_scope.name.startswith("opentelemetry.instrumentation.genai.openai")
    assert span.attributes["gen_ai.provider.name"] == "ollama"
    assert span.attributes["gen_ai.usage.input_tokens"] == 120
    assert span.attributes["base14.endpoint"] == "/review"
    assert span.attributes["base14.content.type"] == "blog"
    assert span.attributes["base14.content.length"] == len("four words of text")
    assert span.attributes["base14.gen_ai.cost_usd"] == 0.0
    assert "gen_ai.input.messages" not in span.attributes


async def test_captured_content_is_scrubbed(span_exporter, capture_content) -> None:
    llm = _ollama_llm(json.dumps({"answer": "mail jane@example.com"}))
    client = LLMClient(provider="ollama", model="qwen3.5:9B", llm=llm)  # type: ignore[arg-type]
    template = MagicMock()
    template.format.return_value = "Review: reach me at john@example.com"

    with patch.object(llm_mod, "cost_counter", MagicMock()):
        await client.generate_structured(template, FakeResult, "x", endpoint="/review")

    (span,) = [s for s in span_exporter.get_finished_spans() if s.name == "chat qwen3.5:9B"]
    assert "[EMAIL]" in span.attributes["gen_ai.input.messages"]
    assert "john@example.com" not in span.attributes["gen_ai.input.messages"]
    assert "jane@example.com" not in span.attributes["gen_ai.output.messages"]
