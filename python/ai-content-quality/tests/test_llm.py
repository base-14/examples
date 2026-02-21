import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

import content_quality.services.llm as llm_mod
from content_quality.services.llm import (
    LLMClient,
    _calculate_cost,
    _extract_raw_usage,
    _is_content_capture_enabled,
    _on_retry,
    _raw_get,
    _record_token_metrics,
    _set_initial_span_attrs,
    _set_response_attrs,
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
        fallback_model="gemini-2.0-flash",
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
# _calculate_cost
# ---------------------------------------------------------------------------


def test_calculate_cost_known_model() -> None:
    cost = _calculate_cost("gpt-4.1-nano", 1000, 500)
    expected = (1000 * 0.10 + 500 * 0.40) / 1_000_000
    assert cost == pytest.approx(expected)


def test_calculate_cost_anthropic_model() -> None:
    cost = _calculate_cost("claude-sonnet-4-20250514", 1000, 200)
    expected = (1000 * 3.0 + 200 * 15.0) / 1_000_000
    assert cost == pytest.approx(expected)


def test_calculate_cost_opus_4_6() -> None:
    cost = _calculate_cost("claude-opus-4-6", 1000, 500)
    expected = (1000 * 5.0 + 500 * 25.0) / 1_000_000
    assert cost == pytest.approx(expected)


def test_calculate_cost_unknown_model_uses_fallback() -> None:
    cost = _calculate_cost("unknown-model-xyz", 1000, 500)
    assert cost == 0.0


def test_calculate_cost_zero_tokens() -> None:
    assert _calculate_cost("gpt-4.1-nano", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# _is_content_capture_enabled
# ---------------------------------------------------------------------------


def test_content_capture_disabled_by_default() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", None)
        assert _is_content_capture_enabled() is False


def test_content_capture_enabled_when_true() -> None:
    with patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"}):
        assert _is_content_capture_enabled() is True


def test_content_capture_enabled_case_insensitive() -> None:
    with patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "True"}):
        assert _is_content_capture_enabled() is True


def test_content_capture_disabled_when_false() -> None:
    with patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"}):
        assert _is_content_capture_enabled() is False


# ---------------------------------------------------------------------------
# _record_token_metrics
# ---------------------------------------------------------------------------


def test_token_metrics_records_when_tokens_available() -> None:
    span = MagicMock()
    mock_histogram = MagicMock()
    mock_cost = MagicMock()
    chat_resp = _make_chat_response(input_tokens=150, output_tokens=80)
    common_attrs = {
        "gen_ai.request.model": "gpt-4.1-nano",
        "gen_ai.provider.name": "openai",
        "gen_ai.response.model": "gpt-4.1-nano",
        "server.address": "api.openai.com",
        "server.port": 443,
    }

    with (
        patch.object(llm_mod, "token_usage", mock_histogram),
        patch.object(llm_mod, "cost_counter", mock_cost),
    ):
        _record_token_metrics(chat_resp, common_attrs, "gpt-4.1-nano", "blog", "/review", span)

    span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 150)
    span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 80)

    histogram_calls = mock_histogram.record.call_args_list
    assert len(histogram_calls) == 2
    assert histogram_calls[0].args[0] == 150
    assert histogram_calls[0].args[1]["gen_ai.token.type"] == "input"
    assert histogram_calls[1].args[0] == 80
    assert histogram_calls[1].args[1]["gen_ai.token.type"] == "output"

    mock_cost.add.assert_called_once()
    cost_attrs = mock_cost.add.call_args.args[1]
    assert cost_attrs["content.type"] == "blog"
    assert cost_attrs["endpoint"] == "/review"


def test_token_metrics_skipped_when_tokens_unavailable() -> None:
    span = MagicMock()
    mock_histogram = MagicMock()
    chat_resp = _make_chat_response(input_tokens=None, output_tokens=None)
    common_attrs = {
        "gen_ai.request.model": "gpt-4.1-nano",
        "gen_ai.provider.name": "openai",
        "gen_ai.response.model": "gpt-4.1-nano",
        "server.address": "api.openai.com",
        "server.port": 443,
    }

    with patch.object(llm_mod, "token_usage", mock_histogram):
        _record_token_metrics(chat_resp, common_attrs, "gpt-4.1-nano", "blog", "/review", span)

    mock_histogram.record.assert_not_called()
    span.set_attribute.assert_not_called()


def test_token_metrics_uses_alternate_key_names() -> None:
    span = MagicMock()
    resp = MagicMock()
    resp.additional_kwargs = {"input_tokens": 200, "output_tokens": 100}
    common_attrs = {
        "gen_ai.request.model": "gemini-2.0-flash",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.response.model": "gemini-2.0-flash",
        "server.address": "generativelanguage.googleapis.com",
        "server.port": 443,
    }

    with (
        patch.object(llm_mod, "token_usage", MagicMock()),
        patch.object(llm_mod, "cost_counter", MagicMock()),
    ):
        _record_token_metrics(resp, common_attrs, "gemini-2.0-flash", "technical", "/score", span)

    span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 200)
    span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 100)


def test_token_metrics_records_cost_on_span() -> None:
    span = MagicMock()
    chat_resp = _make_chat_response(input_tokens=1000, output_tokens=500)
    common_attrs = {
        "gen_ai.request.model": "gpt-4.1-nano",
        "gen_ai.provider.name": "openai",
        "gen_ai.response.model": "gpt-4.1-nano",
        "server.address": "api.openai.com",
        "server.port": 443,
    }

    with (
        patch.object(llm_mod, "token_usage", MagicMock()),
        patch.object(llm_mod, "cost_counter", MagicMock()),
    ):
        _record_token_metrics(chat_resp, common_attrs, "gpt-4.1-nano", "general", "/review", span)

    expected_cost = _calculate_cost("gpt-4.1-nano", 1000, 500)
    span.set_attribute.assert_any_call("gen_ai.usage.cost_usd", expected_cost)


# ---------------------------------------------------------------------------
# _extract_raw_usage / _raw_get — Anthropic-style raw dict responses
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


def test_extract_raw_usage_returns_empty_for_none() -> None:
    assert _extract_raw_usage(None) == {}


def test_extract_raw_usage_returns_empty_for_dict_without_usage() -> None:
    assert _extract_raw_usage({"id": "msg_123", "model": "claude"}) == {}


def test_raw_get_from_dict() -> None:
    raw = {"model": "claude-3-5-haiku", "id": "msg_abc", "stop_reason": "end_turn"}
    get = _raw_get(raw)
    assert get("model") == "claude-3-5-haiku"
    assert get("id") == "msg_abc"
    assert get("stop_reason") == "end_turn"
    assert get("missing") is None


def test_raw_get_from_object() -> None:
    raw = MagicMock()
    raw.model = "gpt-4.1-nano"
    get = _raw_get(raw)
    assert get("model") == "gpt-4.1-nano"


def test_raw_get_from_none() -> None:
    get = _raw_get(None)
    assert get("model") is None


# ---------------------------------------------------------------------------
# _record_token_metrics — Anthropic-style (tokens in raw dict)
# ---------------------------------------------------------------------------


def test_token_metrics_from_anthropic_raw_dict() -> None:
    span = MagicMock()
    resp = MagicMock()
    resp.additional_kwargs = {}
    resp.raw = {"usage": {"input_tokens": 400, "output_tokens": 150}, "id": "msg_123"}

    common_attrs = {
        "gen_ai.request.model": "claude-3-5-haiku-20241022",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.response.model": "claude-3-5-haiku-20241022",
        "server.address": "api.anthropic.com",
        "server.port": 443,
    }

    with (
        patch.object(llm_mod, "token_usage", MagicMock()),
        patch.object(llm_mod, "cost_counter", MagicMock()),
    ):
        _record_token_metrics(
            resp, common_attrs, "claude-3-5-haiku-20241022", "marketing", "/review", span
        )

    span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 400)
    span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 150)


# ---------------------------------------------------------------------------
# _set_response_attrs — Anthropic-style (attrs in raw dict)
# ---------------------------------------------------------------------------


def test_set_response_attrs_from_anthropic_raw_dict() -> None:
    span = MagicMock()
    resp = MagicMock()
    resp.additional_kwargs = {}
    resp.raw = {
        "model": "claude-3-5-haiku-20241022",
        "id": "msg_abc123",
        "stop_reason": "end_turn",
    }

    response_model, finish_reason = _set_response_attrs(resp, span, "claude-3-5-haiku-20241022")

    assert response_model == "claude-3-5-haiku-20241022"
    assert finish_reason == "end_turn"
    span.set_attribute.assert_any_call("gen_ai.response.model", "claude-3-5-haiku-20241022")
    span.set_attribute.assert_any_call("gen_ai.response.id", "msg_abc123")
    span.set_attribute.assert_any_call("gen_ai.response.finish_reasons", ["end_turn"])


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
    client = _make_client("gpt-4.1-mini", provider="openai")
    retry_state = MagicMock()
    retry_state.args = (client,)
    retry_state.outcome.exception.return_value = httpx.ConnectError("conn refused")
    retry_state.attempt_number = 1

    with patch.object(llm_mod, "retry_counter", mock_counter):
        _on_retry(retry_state)

    attrs = mock_counter.add.call_args.args[1]
    assert attrs["gen_ai.request.model"] == "gpt-4.1-mini"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert attrs["error.type"] == "ConnectError"
    assert attrs["retry.attempt"] == 1


def test_on_retry_handles_missing_args() -> None:
    mock_counter = MagicMock()
    retry_state = MagicMock()
    retry_state.args = ()
    retry_state.outcome.exception.return_value = None
    retry_state.attempt_number = 2

    with patch.object(llm_mod, "retry_counter", mock_counter):
        _on_retry(retry_state)

    attrs = mock_counter.add.call_args.args[1]
    assert attrs["gen_ai.request.model"] == "unknown"
    assert attrs["retry.attempt"] == 2


# ---------------------------------------------------------------------------
# generate_structured — span creation & attributes
# ---------------------------------------------------------------------------


def _setup_generate_mocks(
    content: str = '{"answer": "yes"}',
    input_tokens: int | None = 100,
    output_tokens: int | None = 50,
    model_name: str = "gpt-4.1-nano",
    provider: str = "openai",
    response_model: str | None = None,
    response_id: str | None = None,
    finish_reason: str | None = None,
) -> tuple[LLMClient, MagicMock, MagicMock]:
    llm = _make_llm(model_name)
    chat_resp = _make_chat_response(
        content,
        input_tokens,
        output_tokens,
        response_model=response_model,
        response_id=response_id,
        finish_reason=finish_reason,
    )
    llm.achat = AsyncMock(return_value=chat_resp)

    client = LLMClient(
        provider=provider,
        model=model_name,
        llm=llm,
        fallback_provider="google",
        fallback_model="gemini-2.0-flash",
        fallback_llm=None,
    )

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)

    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span

    return client, tracer, span


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_creates_span_with_correct_name() -> None:
    client, tracer, _span = _setup_generate_mocks()

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    tracer.start_as_current_span.assert_called_once_with("gen_ai.chat gpt-4.1-nano")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_sets_content_attributes_on_span() -> None:
    client, tracer, span = _setup_generate_mocks()

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client,
            _make_prompt_template(),
            FakeResult,
            "hello world",
            content_type="marketing",
            endpoint="/review",
        )

    span.set_attribute.assert_any_call("content.type", "marketing")
    span.set_attribute.assert_any_call("content.length", 11)
    span.set_attribute.assert_any_call("endpoint", "/review")
    span.set_attribute.assert_any_call("gen_ai.operation.name", "chat")
    span.set_attribute.assert_any_call("gen_ai.output.type", "json")
    span.set_attribute.assert_any_call("server.address", "api.openai.com")
    span.set_attribute.assert_any_call("server.port", 443)


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_sets_model_attributes_on_span() -> None:
    client, tracer, span = _setup_generate_mocks(model_name="gemini-2.0-flash", provider="google")

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/score"
        )

    span.set_attribute.assert_any_call("gen_ai.request.model", "gemini-2.0-flash")
    span.set_attribute.assert_any_call("gen_ai.provider.name", "gcp.gemini")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_sets_temperature_on_span() -> None:
    client, tracer, span = _setup_generate_mocks()
    client.llm.temperature = 0.7

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    span.set_attribute.assert_any_call("gen_ai.request.temperature", 0.7)


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_skips_temperature_when_not_available() -> None:
    client, tracer, span = _setup_generate_mocks()
    del client.llm.temperature

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    temp_calls = [
        c for c in span.set_attribute.call_args_list if c.args[0] == "gen_ai.request.temperature"
    ]
    assert len(temp_calls) == 0


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
async def test_generate_records_operation_duration() -> None:
    client, tracer, span = _setup_generate_mocks()
    mock_duration = MagicMock()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.object(llm_mod, "operation_duration", mock_duration),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    mock_duration.record.assert_called_once()
    duration_val = mock_duration.record.call_args.args[0]
    assert duration_val > 0
    span.set_attribute.assert_any_call("gen_ai.client.operation.duration", duration_val)


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_records_token_histograms() -> None:
    client, tracer, _span = _setup_generate_mocks(input_tokens=200, output_tokens=100)
    mock_tokens = MagicMock()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.object(llm_mod, "token_usage", mock_tokens),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert mock_tokens.record.call_count == 2
    input_call, output_call = mock_tokens.record.call_args_list
    assert input_call.args[0] == 200
    assert input_call.args[1]["gen_ai.token.type"] == "input"
    assert output_call.args[0] == 100
    assert output_call.args[1]["gen_ai.token.type"] == "output"


@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_records_cost() -> None:
    client, tracer, _span = _setup_generate_mocks(input_tokens=1000, output_tokens=500)
    mock_cost = MagicMock()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.object(llm_mod, "cost_counter", mock_cost),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client,
            _make_prompt_template(),
            FakeResult,
            "test",
            content_type="technical",
            endpoint="/score",
        )

    mock_cost.add.assert_called_once()
    cost_val = mock_cost.add.call_args.args[0]
    expected = _calculate_cost("gpt-4.1-nano", 1000, 500)
    assert cost_val == pytest.approx(expected)
    attrs = mock_cost.add.call_args.args[1]
    assert attrs["content.type"] == "technical"
    assert attrs["endpoint"] == "/score"


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_emits_user_and_assistant_span_events() -> None:
    client, tracer, span = _setup_generate_mocks()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"}),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client,
            _make_prompt_template(),
            FakeResult,
            "test",
            system_prompt="Contact john@test.com",
            endpoint="/review",
        )

    assert span.add_event.call_count == 2
    assert span.add_event.call_args_list[0].args[0] == "gen_ai.user.message"
    assert span.add_event.call_args_list[1].args[0] == "gen_ai.assistant.message"

    user_attrs = span.add_event.call_args_list[0].args[1]
    assert "gen_ai.prompt" in user_attrs
    assert "[EMAIL]" in user_attrs["gen_ai.system_instructions"]
    assert "john@test.com" not in user_attrs["gen_ai.system_instructions"]

    asst_attrs = span.add_event.call_args_list[1].args[1]
    assert "gen_ai.completion" in asst_attrs


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_user_event_omits_system_instructions_when_no_system_prompt() -> None:
    client, tracer, span = _setup_generate_mocks()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"}),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    user_attrs = span.add_event.call_args_list[0].args[1]
    assert "gen_ai.system_instructions" not in user_attrs
    assert "gen_ai.prompt" in user_attrs


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_span_events_truncate_content() -> None:
    client, tracer, span = _setup_generate_mocks()
    long_response = _make_chat_response(content='{"answer": "' + "x" * 2500 + '"}')
    client.llm.achat = AsyncMock(return_value=long_response)

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"}),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client,
            _make_prompt_template(),
            FakeResult,
            "test",
            system_prompt="y" * 1000,
            endpoint="/review",
        )

    user_attrs = span.add_event.call_args_list[0].args[1]
    assert len(user_attrs["gen_ai.system_instructions"]) <= 500
    asst_attrs = span.add_event.call_args_list[1].args[1]
    assert len(asst_attrs["gen_ai.completion"]) <= 2000


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_skips_span_event_when_content_capture_disabled() -> None:
    client, tracer, span = _setup_generate_mocks()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", None)
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    span.add_event.assert_not_called()


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_sets_response_model_on_span() -> None:
    client, tracer, span = _setup_generate_mocks(
        model_name="gpt-4.1-nano", response_model="gpt-4.1-nano-2025-04-14"
    )

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    span.set_attribute.assert_any_call("gen_ai.response.model", "gpt-4.1-nano-2025-04-14")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_response_model_falls_back_to_request_model() -> None:
    client, tracer, span = _setup_generate_mocks(model_name="gpt-4.1-nano")

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    span.set_attribute.assert_any_call("gen_ai.response.model", "gpt-4.1-nano")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_common_attrs_include_server_address_and_response_model() -> None:
    client, tracer, _span = _setup_generate_mocks(input_tokens=100, output_tokens=50)
    mock_tokens = MagicMock()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.object(llm_mod, "token_usage", mock_tokens),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    token_attrs = mock_tokens.record.call_args_list[0].args[1]
    assert token_attrs["server.address"] == "api.openai.com"
    assert token_attrs["server.port"] == 443
    assert token_attrs["gen_ai.response.model"] == "gpt-4.1-nano"


# ---------------------------------------------------------------------------
# generate_structured — error path
# ---------------------------------------------------------------------------


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_error_records_exception_on_span() -> None:
    client = _make_client()
    client.llm.achat = AsyncMock(side_effect=RuntimeError("LLM crashed"))

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span

    with (
        patch.object(llm_mod, "tracer", tracer),
        pytest.raises(RuntimeError, match="LLM crashed"),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    span.record_exception.assert_called_once()
    span.set_status.assert_called_once()
    status_args = span.set_status.call_args.args
    from opentelemetry.trace import StatusCode

    assert status_args[0] == StatusCode.ERROR
    span.set_attribute.assert_any_call("error.type", "RuntimeError")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_error_increments_error_counter() -> None:
    client = _make_client("gpt-4.1-mini")
    client.llm.achat = AsyncMock(side_effect=ValueError("bad response"))

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span
    mock_errors = MagicMock()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.object(llm_mod, "error_counter", mock_errors),
        pytest.raises(ValueError, match="bad response"),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    mock_errors.add.assert_called_once_with(
        1,
        {
            "gen_ai.request.model": "gpt-4.1-mini",
            "gen_ai.provider.name": "openai",
            "error.type": "ValueError",
        },
    )


# ---------------------------------------------------------------------------
# generate_structured — retry triggers retry_counter via @retry decorator
# ---------------------------------------------------------------------------


async def test_generate_retry_increments_retry_counter() -> None:
    client = _make_client()
    chat_resp = _make_chat_response()

    call_count = 0

    async def flaky_achat(*args: object, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection refused")
        return chat_resp

    client.llm.achat = flaky_achat

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span
    mock_retries = MagicMock()

    with (
        patch.object(llm_mod, "tracer", tracer),
        patch.object(llm_mod, "retry_counter", mock_retries),
        patch.object(llm_mod, "token_usage", MagicMock()),
        patch.object(llm_mod, "operation_duration", MagicMock()),
        patch.object(llm_mod, "cost_counter", MagicMock()),
    ):
        result = await client.generate_structured(
            _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    mock_retries.add.assert_called_once()
    retry_attrs = mock_retries.add.call_args.args[1]
    assert "error.type" in retry_attrs
    assert "retry.attempt" in retry_attrs


# ---------------------------------------------------------------------------
# generate_structured — returns parsed result
# ---------------------------------------------------------------------------


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_returns_parsed_pydantic_model() -> None:
    client, tracer, _span = _setup_generate_mocks(content='{"answer": "42"}')

    with patch.object(llm_mod, "tracer", tracer):
        result = await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    assert result.answer == "42"


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_passes_system_prompt_as_first_message() -> None:
    client, tracer, _span = _setup_generate_mocks()

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client,
            _make_prompt_template(),
            FakeResult,
            "test",
            system_prompt="Be helpful",
            endpoint="/review",
        )

    messages = client.llm.achat.call_args.args[0]
    assert messages[0].role == "system"
    assert "Be helpful" in messages[0].content
    assert messages[1].role == "user"


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_includes_json_schema_in_system_message() -> None:
    client, tracer, _span = _setup_generate_mocks()

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    messages = client.llm.achat.call_args.args[0]
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "JSON" in messages[0].content
    assert messages[1].role == "user"


# ---------------------------------------------------------------------------
# generate_structured — parse retry on ValidationError
# ---------------------------------------------------------------------------


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_retries_on_validation_error() -> None:
    client = _make_client()
    bad_resp = _make_chat_response(content='{"wrong_field": "oops"}')
    good_resp = _make_chat_response(content='{"answer": "fixed"}')

    client.llm.achat = AsyncMock(side_effect=[bad_resp, good_resp])

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span

    with patch.object(llm_mod, "tracer", tracer):
        result = await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    assert result.answer == "fixed"
    assert client.llm.achat.call_count == 2
    correction_msgs = client.llm.achat.call_args.args[0]
    assert any(m.role == "user" and "schema" in str(m.content).lower() for m in correction_msgs)


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_raises_after_max_parse_retries() -> None:
    client = _make_client()
    bad_resp = _make_chat_response(content='{"wrong": "data"}')

    client.llm.achat = AsyncMock(return_value=bad_resp)

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span

    from pydantic import ValidationError

    with (
        patch.object(llm_mod, "tracer", tracer),
        pytest.raises(ValidationError),
    ):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert client.llm.achat.call_count == 3  # initial + 2 retries


# ---------------------------------------------------------------------------
# _set_initial_span_attrs — direct unit tests
# ---------------------------------------------------------------------------


def test_set_initial_span_attrs_skips_server_address_when_empty() -> None:
    span = MagicMock()
    llm = _make_llm(temperature=0.5)

    _set_initial_span_attrs(span, llm, "gpt-4.1-nano", "", "blog", "hello", "/review")

    server_addr_calls = [
        c for c in span.set_attribute.call_args_list if c.args[0] == "server.address"
    ]
    assert len(server_addr_calls) == 0
    span.set_attribute.assert_any_call("gen_ai.request.temperature", 0.5)
    span.set_attribute.assert_any_call("content.type", "blog")
    span.set_attribute.assert_any_call("content.length", 5)


def test_set_initial_span_attrs_sets_all_attributes() -> None:
    span = MagicMock()
    llm = _make_llm(temperature=0.3)

    _set_initial_span_attrs(
        span, llm, "gpt-4.1-nano", "api.openai.com", "technical", "test content", "/score"
    )

    span.set_attribute.assert_any_call("gen_ai.operation.name", "chat")
    span.set_attribute.assert_any_call("gen_ai.request.model", "gpt-4.1-nano")
    span.set_attribute.assert_any_call("server.address", "api.openai.com")
    span.set_attribute.assert_any_call("server.port", 443)
    span.set_attribute.assert_any_call("gen_ai.output.type", "json")
    span.set_attribute.assert_any_call("gen_ai.request.temperature", 0.3)
    span.set_attribute.assert_any_call("content.type", "technical")
    span.set_attribute.assert_any_call("content.length", 12)
    span.set_attribute.assert_any_call("endpoint", "/score")


# ---------------------------------------------------------------------------
# create_llm — error case
# ---------------------------------------------------------------------------


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_sets_response_id_and_finish_reason_on_span() -> None:
    client, tracer, span = _setup_generate_mocks(
        response_id="chatcmpl-abc123", finish_reason="stop"
    )

    with patch.object(llm_mod, "tracer", tracer):
        await LLMClient.generate_structured.__wrapped__(
            client, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    span.set_attribute.assert_any_call("gen_ai.response.id", "chatcmpl-abc123")
    span.set_attribute.assert_any_call("gen_ai.response.finish_reasons", ["stop"])


# ---------------------------------------------------------------------------
# create_llm — error case
# ---------------------------------------------------------------------------


def test_create_llm_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm(provider="unknown_provider")
