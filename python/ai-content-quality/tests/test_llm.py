from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

import content_quality.services.llm as llm_mod
from content_quality.services.llm import (
    _calculate_cost,
    _on_retry,
    _record_span_events,
    _record_token_metrics,
    generate_structured,
)


class FakeResult(BaseModel):
    answer: str


def _make_llm(model_name: str = "gpt-4.1-nano") -> MagicMock:
    llm = MagicMock()
    llm.metadata.model_name = model_name
    return llm


def _make_chat_response(
    content: str = '{"answer": "yes"}',
    input_tokens: int | None = 100,
    output_tokens: int | None = 50,
) -> MagicMock:
    resp = MagicMock()
    resp.message.content = content
    kwargs: dict[str, int] = {}
    if input_tokens is not None:
        kwargs["prompt_tokens"] = input_tokens
    if output_tokens is not None:
        kwargs["completion_tokens"] = output_tokens
    resp.additional_kwargs = kwargs
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


def test_calculate_cost_unknown_model_uses_fallback() -> None:
    cost = _calculate_cost("unknown-model-xyz", 1000, 500)
    expected = (1000 * 0.10 + 500 * 0.40) / 1_000_000
    assert cost == pytest.approx(expected)


def test_calculate_cost_zero_tokens() -> None:
    assert _calculate_cost("gpt-4.1-nano", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# _record_span_events
# ---------------------------------------------------------------------------


def test_span_events_all_three_messages() -> None:
    span = MagicMock()
    _record_span_events(span, "sys prompt", "user prompt", "assistant reply")
    assert span.add_event.call_count == 3
    names = [c.args[0] for c in span.add_event.call_args_list]
    assert names == ["gen_ai.system.message", "gen_ai.user.message", "gen_ai.assistant.message"]


def test_span_events_skips_empty_system_prompt() -> None:
    span = MagicMock()
    _record_span_events(span, "", "user prompt", "assistant reply")
    assert span.add_event.call_count == 2
    names = [c.args[0] for c in span.add_event.call_args_list]
    assert "gen_ai.system.message" not in names


def test_span_events_truncates_to_500_chars() -> None:
    span = MagicMock()
    long_text = "x" * 1000
    _record_span_events(span, long_text, long_text, long_text)
    for call in span.add_event.call_args_list:
        assert len(call.args[1]["content"]) <= 500


def test_span_events_scrubs_pii() -> None:
    span = MagicMock()
    _record_span_events(span, "", "Email john@example.com", "Call 555-123-4567")
    user_content = span.add_event.call_args_list[0].args[1]["content"]
    assert "[EMAIL]" in user_content
    assert "john@example.com" not in user_content
    assistant_content = span.add_event.call_args_list[1].args[1]["content"]
    assert "[PHONE]" in assistant_content


# ---------------------------------------------------------------------------
# _record_token_metrics
# ---------------------------------------------------------------------------


def test_token_metrics_records_when_tokens_available() -> None:
    span = MagicMock()
    mock_histogram = MagicMock()
    mock_cost = MagicMock()
    chat_resp = _make_chat_response(input_tokens=150, output_tokens=80)
    common_attrs = {"gen_ai.request.model": "gpt-4.1-nano", "gen_ai.provider.name": "openai"}

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
    common_attrs = {"gen_ai.request.model": "gpt-4.1-nano", "gen_ai.provider.name": "openai"}

    with patch.object(llm_mod, "token_usage", mock_histogram):
        _record_token_metrics(chat_resp, common_attrs, "gpt-4.1-nano", "blog", "/review", span)

    mock_histogram.record.assert_not_called()
    span.set_attribute.assert_not_called()


def test_token_metrics_uses_alternate_key_names() -> None:
    span = MagicMock()
    resp = MagicMock()
    resp.additional_kwargs = {"input_tokens": 200, "output_tokens": 100}
    common_attrs = {"gen_ai.request.model": "gemini-2.0-flash", "gen_ai.provider.name": "google"}

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
    common_attrs = {"gen_ai.request.model": "gpt-4.1-nano", "gen_ai.provider.name": "openai"}

    with (
        patch.object(llm_mod, "token_usage", MagicMock()),
        patch.object(llm_mod, "cost_counter", MagicMock()),
    ):
        _record_token_metrics(chat_resp, common_attrs, "gpt-4.1-nano", "general", "/review", span)

    expected_cost = _calculate_cost("gpt-4.1-nano", 1000, 500)
    span.set_attribute.assert_any_call("gen_ai.usage.cost_usd", expected_cost)


# ---------------------------------------------------------------------------
# _on_retry
# ---------------------------------------------------------------------------


def test_on_retry_increments_counter() -> None:
    mock_counter = MagicMock()
    llm = _make_llm("gpt-4.1-mini")
    retry_state = MagicMock()
    retry_state.args = (llm,)

    with (
        patch.object(llm_mod, "retry_counter", mock_counter),
        patch.object(llm_mod, "_provider", "openai"),
    ):
        _on_retry(retry_state)

    mock_counter.add.assert_called_once_with(
        1, {"gen_ai.request.model": "gpt-4.1-mini", "gen_ai.provider.name": "openai"}
    )


def test_on_retry_handles_missing_args() -> None:
    mock_counter = MagicMock()
    retry_state = MagicMock()
    retry_state.args = ()

    with (
        patch.object(llm_mod, "retry_counter", mock_counter),
        patch.object(llm_mod, "_provider", "openai"),
    ):
        _on_retry(retry_state)

    attrs = mock_counter.add.call_args.args[1]
    assert attrs["gen_ai.request.model"] == "unknown"


# ---------------------------------------------------------------------------
# generate_structured — span creation & attributes
# ---------------------------------------------------------------------------


def _setup_generate_mocks(
    content: str = '{"answer": "yes"}',
    input_tokens: int | None = 100,
    output_tokens: int | None = 50,
    model_name: str = "gpt-4.1-nano",
) -> tuple[MagicMock, MagicMock, MagicMock]:
    llm = _make_llm(model_name)
    chat_resp = _make_chat_response(content, input_tokens, output_tokens)
    sllm = MagicMock()
    sllm.achat = AsyncMock(return_value=chat_resp)
    llm.as_structured_llm.return_value = sllm

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)

    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span

    return llm, tracer, span


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_creates_span_with_correct_name() -> None:
    llm, tracer, _span = _setup_generate_mocks()

    with patch.object(llm_mod.trace, "get_tracer", return_value=tracer):
        await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    tracer.start_as_current_span.assert_called_once_with("content_analysis review")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_sets_content_attributes_on_span() -> None:
    llm, tracer, span = _setup_generate_mocks()

    with patch.object(llm_mod.trace, "get_tracer", return_value=tracer):
        await generate_structured.__wrapped__(
            llm,
            _make_prompt_template(),
            FakeResult,
            "hello world",
            content_type="marketing",
            endpoint="/review",
        )

    span.set_attribute.assert_any_call("content.type", "marketing")
    span.set_attribute.assert_any_call("content.length", 11)
    span.set_attribute.assert_any_call("endpoint", "/review")
    span.set_attribute.assert_any_call("gen_ai.operation.name", "content_analysis")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_sets_model_attributes_on_span() -> None:
    llm, tracer, span = _setup_generate_mocks(model_name="gemini-2.0-flash")

    with (
        patch.object(llm_mod.trace, "get_tracer", return_value=tracer),
        patch.object(llm_mod, "_provider", "google"),
    ):
        await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/score"
        )

    span.set_attribute.assert_any_call("gen_ai.request.model", "gemini-2.0-flash")
    span.set_attribute.assert_any_call("gen_ai.provider.name", "google")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
async def test_generate_records_operation_duration() -> None:
    llm, tracer, span = _setup_generate_mocks()
    mock_duration = MagicMock()

    with (
        patch.object(llm_mod.trace, "get_tracer", return_value=tracer),
        patch.object(llm_mod, "operation_duration", mock_duration),
    ):
        await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    mock_duration.record.assert_called_once()
    duration_val = mock_duration.record.call_args.args[0]
    assert duration_val > 0
    span.set_attribute.assert_any_call("gen_ai.client.operation.duration", duration_val)


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_records_token_histograms() -> None:
    llm, tracer, _span = _setup_generate_mocks(input_tokens=200, output_tokens=100)
    mock_tokens = MagicMock()

    with (
        patch.object(llm_mod.trace, "get_tracer", return_value=tracer),
        patch.object(llm_mod, "token_usage", mock_tokens),
    ):
        await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
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
    llm, tracer, _span = _setup_generate_mocks(input_tokens=1000, output_tokens=500)
    mock_cost = MagicMock()

    with (
        patch.object(llm_mod.trace, "get_tracer", return_value=tracer),
        patch.object(llm_mod, "cost_counter", mock_cost),
    ):
        await generate_structured.__wrapped__(
            llm,
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
async def test_generate_adds_span_events_with_pii_scrubbed() -> None:
    llm, tracer, span = _setup_generate_mocks()

    with patch.object(llm_mod.trace, "get_tracer", return_value=tracer):
        await generate_structured.__wrapped__(
            llm,
            _make_prompt_template(),
            FakeResult,
            "test",
            system_prompt="Contact john@test.com",
            endpoint="/review",
        )

    event_calls = span.add_event.call_args_list
    event_names = [c.args[0] for c in event_calls]
    assert "gen_ai.system.message" in event_names
    assert "gen_ai.user.message" in event_names
    assert "gen_ai.assistant.message" in event_names

    system_event = next(c for c in event_calls if c.args[0] == "gen_ai.system.message")
    assert "[EMAIL]" in system_event.args[1]["content"]
    assert "john@test.com" not in system_event.args[1]["content"]


# ---------------------------------------------------------------------------
# generate_structured — error path
# ---------------------------------------------------------------------------


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_error_records_exception_on_span() -> None:
    llm = _make_llm()
    sllm = MagicMock()
    sllm.achat = AsyncMock(side_effect=RuntimeError("LLM crashed"))
    llm.as_structured_llm.return_value = sllm

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span

    with (
        patch.object(llm_mod.trace, "get_tracer", return_value=tracer),
        pytest.raises(RuntimeError, match="LLM crashed"),
    ):
        await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    span.record_exception.assert_called_once()
    span.set_attribute.assert_any_call("error.type", "RuntimeError")


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_error_increments_error_counter() -> None:
    llm = _make_llm("gpt-4.1-mini")
    sllm = MagicMock()
    sllm.achat = AsyncMock(side_effect=ValueError("bad response"))
    llm.as_structured_llm.return_value = sllm

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span
    mock_errors = MagicMock()

    with (
        patch.object(llm_mod.trace, "get_tracer", return_value=tracer),
        patch.object(llm_mod, "error_counter", mock_errors),
        pytest.raises(ValueError, match="bad response"),
    ):
        await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    mock_errors.add.assert_called_once_with(
        1, {"gen_ai.request.model": "gpt-4.1-mini", "error.type": "ValueError"}
    )


# ---------------------------------------------------------------------------
# generate_structured — retry triggers retry_counter via @retry decorator
# ---------------------------------------------------------------------------


async def test_generate_retry_increments_retry_counter() -> None:
    llm = _make_llm()
    chat_resp = _make_chat_response()

    sllm = MagicMock()
    call_count = 0

    async def flaky_achat(*args: object, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection refused")
        return chat_resp

    sllm.achat = flaky_achat
    llm.as_structured_llm.return_value = sllm

    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer = MagicMock()
    tracer.start_as_current_span.return_value = span
    mock_retries = MagicMock()

    with (
        patch.object(llm_mod.trace, "get_tracer", return_value=tracer),
        patch.object(llm_mod, "retry_counter", mock_retries),
        patch.object(llm_mod, "token_usage", MagicMock()),
        patch.object(llm_mod, "operation_duration", MagicMock()),
        patch.object(llm_mod, "cost_counter", MagicMock()),
    ):
        result = await generate_structured(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    mock_retries.add.assert_called_once()


# ---------------------------------------------------------------------------
# generate_structured — returns parsed result
# ---------------------------------------------------------------------------


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_returns_parsed_pydantic_model() -> None:
    llm, tracer, _span = _setup_generate_mocks(content='{"answer": "42"}')

    with patch.object(llm_mod.trace, "get_tracer", return_value=tracer):
        result = await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    assert isinstance(result, FakeResult)
    assert result.answer == "42"


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_passes_system_prompt_as_first_message() -> None:
    llm, tracer, _span = _setup_generate_mocks()
    sllm = llm.as_structured_llm.return_value

    with patch.object(llm_mod.trace, "get_tracer", return_value=tracer):
        await generate_structured.__wrapped__(
            llm,
            _make_prompt_template(),
            FakeResult,
            "test",
            system_prompt="Be helpful",
            endpoint="/review",
        )

    messages = sllm.achat.call_args.args[0]
    assert messages[0].role == "system"
    assert messages[0].content == "Be helpful"
    assert messages[1].role == "user"


@patch.object(llm_mod, "cost_counter", MagicMock())
@patch.object(llm_mod, "token_usage", MagicMock())
@patch.object(llm_mod, "operation_duration", MagicMock())
async def test_generate_omits_system_message_when_empty() -> None:
    llm, tracer, _span = _setup_generate_mocks()
    sllm = llm.as_structured_llm.return_value

    with patch.object(llm_mod.trace, "get_tracer", return_value=tracer):
        await generate_structured.__wrapped__(
            llm, _make_prompt_template(), FakeResult, "test", endpoint="/review"
        )

    messages = sllm.achat.call_args.args[0]
    assert len(messages) == 1
    assert messages[0].role == "user"
