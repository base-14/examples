"""LLM client tests driven by the shared test vectors.

Each test loads a vector from `_shared/test-vectors` and runs the client over
LlamaIndex's real Anthropic and OpenAI integrations, whose SDK clients answer from
a mock transport. The spans come from the OpenTelemetry GenAI instrumentations for
those SDKs, so three things differ from the vectors, which were written for one
hand-written span per logical call: every retry attempt is its own span, a failed
attempt's `error.type` is the SDK's exception class, and Anthropic's `end_turn` is
reported as the convention's `stop`. The vectors' `content` is wrapped as
`{"answer": "<content>"}` JSON for the structured-output parser.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest
from opentelemetry.sdk.metrics.export import Histogram, Sum
from opentelemetry.trace import StatusCode
from pydantic import BaseModel

from content_quality.services.llm import LLMClient, create_llm
from tests.conftest import METRIC_READER


VECTORS_DIR = Path(__file__).parents[3] / "_shared" / "test-vectors"

COST_ATTRIBUTE = "base14.gen_ai.cost_usd"

Response = dict[str, Any] | int


class AnswerResult(BaseModel):
    answer: str


def load_vector(name: str) -> dict[str, Any]:
    with (VECTORS_DIR / name).open() as f:
        data: dict[str, Any] = json.load(f)
    return data


def _next(responses: list[Response]) -> httpx.Response:
    response = responses.pop(0)
    if isinstance(response, int):
        return httpx.Response(response, json={"error": {"type": "api_error", "message": "down"}})
    return httpx.Response(200, json=response)


def anthropic_message(mock: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": mock["response_id"],
        "type": "message",
        "role": "assistant",
        "model": mock["model"],
        "content": [{"type": "text", "text": json.dumps({"answer": mock["content"]})}],
        "stop_reason": mock["finish_reason"],
        "stop_sequence": None,
        "usage": {"input_tokens": mock["input_tokens"], "output_tokens": mock["output_tokens"]},
    }


def openai_completion(mock: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": mock["response_id"],
        "object": "chat.completion",
        "created": 1,
        "model": mock["model"],
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"answer": mock["content"]}),
                },
                "finish_reason": mock["finish_reason"],
            }
        ],
        "usage": {
            "prompt_tokens": mock["input_tokens"],
            "completion_tokens": mock["output_tokens"],
            "total_tokens": mock["input_tokens"] + mock["output_tokens"],
        },
    }


def anthropic_llm(model: str, responses: list[Response]) -> Any:
    llm = create_llm(provider="anthropic", model=model, api_key="test-key")
    transport = httpx.MockTransport(lambda _request: _next(responses))
    llm._aclient = anthropic.AsyncAnthropic(
        api_key="test-key", max_retries=0, http_client=httpx.AsyncClient(transport=transport)
    )
    return llm


def openai_llm(model: str, responses: list[Response]) -> Any:
    llm = create_llm(provider="openai", model=model, api_key="test-key")
    transport = httpx.MockTransport(lambda _request: _next(responses))
    llm._async_http_client = httpx.AsyncClient(transport=transport)
    return llm


def prompt_template(prompt: str) -> MagicMock:
    pt = MagicMock()
    pt.format.return_value = prompt
    return pt


def metric_total(name: str, attrs: dict[str, Any]) -> float:
    """Cumulative value of a counter or histogram, over points matching attrs."""
    total = 0.0
    data = METRIC_READER.get_metrics_data()
    if data is None:
        return total
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    if any(point.attributes.get(k) != v for k, v in attrs.items()):
                        continue
                    if isinstance(metric.data, Sum):
                        total += point.value
                    elif isinstance(metric.data, Histogram):
                        total += point.sum
    return total


def chat_spans(spans: Any, model: str) -> list[Any]:
    return [s for s in spans if s.name == f"chat {model}"]


class TestChatCompletionVector:
    """_shared/test-vectors/chat-completion.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-completion.json")

    async def test_span_and_metrics(self, vector, span_exporter) -> None:
        request = vector["input"]
        mock = vector["mock_response"]
        model_attrs = {"gen_ai.request.model": request["model"]}
        input_before = metric_total(
            "gen_ai.client.token.usage", {**model_attrs, "gen_ai.token.type": "input"}
        )
        cost_before = metric_total("base14.gen_ai.cost", model_attrs)
        counters_before = [
            metric_total(f"base14.gen_ai.{name}.count", {})
            for name in ("retry", "fallback", "error")
        ]

        llm = anthropic_llm(request["model"], [anthropic_message(mock)])
        client = LLMClient(provider="anthropic", model=request["model"], llm=llm)
        result = await client.generate_structured(
            prompt_template(request["prompt"]), AnswerResult, "content", endpoint="/review"
        )

        assert isinstance(result, AnswerResult)
        assert result.answer == mock["content"]
        (span,) = chat_spans(span_exporter.get_finished_spans(), request["model"])
        assert span.status.status_code is not StatusCode.ERROR
        expected = vector["expected_span"]["attributes"]
        for key in (
            "gen_ai.operation.name",
            "gen_ai.provider.name",
            "gen_ai.request.model",
            "gen_ai.response.model",
            "gen_ai.response.id",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
            "server.address",
        ):
            assert span.attributes[key] == expected[key], key
        assert list(span.attributes["gen_ai.response.finish_reasons"]) == ["stop"]
        assert span.attributes[COST_ATTRIBUTE] == pytest.approx(expected[COST_ATTRIBUTE], rel=0.01)
        assert "gen_ai.input.messages" not in span.attributes, "content capture is off"

        assert metric_total(
            "gen_ai.client.token.usage", {**model_attrs, "gen_ai.token.type": "input"}
        ) - input_before == pytest.approx(mock["input_tokens"])
        assert metric_total("base14.gen_ai.cost", model_attrs) - cost_before == pytest.approx(
            expected[COST_ATTRIBUTE], rel=0.01
        )
        assert [
            metric_total(f"base14.gen_ai.{name}.count", {})
            for name in ("retry", "fallback", "error")
        ] == counters_before


class TestChatWithRetryVector:
    """_shared/test-vectors/chat-with-retry.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-with-retry.json")

    async def test_retry_leaves_a_failed_attempt(self, vector, span_exporter) -> None:
        setup = vector["setup"]
        second = vector["mock_behavior"]["attempt_2"]
        retry_attrs = {"gen_ai.provider.name": "anthropic", "error.type": "RateLimitError"}
        retries_before = metric_total("base14.gen_ai.retry.count", retry_attrs)
        errors_before = metric_total("base14.gen_ai.error.count", {})

        assert "raise Exception" in vector["mock_behavior"]["attempt_1"]
        llm = anthropic_llm(setup["model"], [429, anthropic_message(second)])
        client = LLMClient(provider="anthropic", model=setup["model"], llm=llm)
        result = await client.generate_structured(
            prompt_template("Hello"), AnswerResult, "content", endpoint="/review"
        )

        assert isinstance(result, AnswerResult)
        failed, succeeded = chat_spans(span_exporter.get_finished_spans(), setup["model"])
        assert failed.status.status_code is StatusCode.ERROR
        assert succeeded.status.status_code is not StatusCode.ERROR
        assert succeeded.attributes["gen_ai.usage.output_tokens"] == second["output_tokens"]
        assert metric_total("base14.gen_ai.retry.count", retry_attrs) - retries_before == 1
        assert metric_total("base14.gen_ai.error.count", {}) == errors_before


class TestChatWithFallbackVector:
    """_shared/test-vectors/chat-with-fallback.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-with-fallback.json")

    async def test_primary_fails_and_fallback_answers(self, vector, span_exporter) -> None:
        setup = vector["setup"]
        served = vector["mock_behavior"]["fallback"]
        by_name = {m["name"]: m for m in vector["expected_metrics"]}
        fallback_attrs = by_name["base14.gen_ai.fallback.count"]["attrs"]
        retries_before = metric_total("base14.gen_ai.retry.count", {})
        fallbacks_before = metric_total("base14.gen_ai.fallback.count", fallback_attrs)
        errors_before = metric_total(
            "base14.gen_ai.error.count", {"gen_ai.provider.name": "anthropic"}
        )

        client = LLMClient(
            provider="anthropic",
            model=setup["primary_model"],
            llm=anthropic_llm(setup["primary_model"], [503, 503, 503]),
            fallback_provider="openai",
            fallback_model=setup["fallback_model"],
            fallback_llm=openai_llm(setup["fallback_model"], [openai_completion(served)]),
        )
        result = await client.generate_structured(
            prompt_template("Hello"), AnswerResult, "content", endpoint="/review"
        )

        assert isinstance(result, AnswerResult)
        assert result.answer == served["content"]
        spans = span_exporter.get_finished_spans()
        primary_spans = chat_spans(spans, setup["primary_model"])
        assert len(primary_spans) == 3, "one span per attempt"
        assert all(s.status.status_code is StatusCode.ERROR for s in primary_spans)
        (fallback_span,) = chat_spans(spans, setup["fallback_model"])
        assert fallback_span.status.status_code is not StatusCode.ERROR
        assert fallback_span.attributes["gen_ai.provider.name"] == "openai"
        assert fallback_span.attributes["gen_ai.usage.input_tokens"] == served["input_tokens"]

        assert (
            metric_total("base14.gen_ai.retry.count", {}) - retries_before
            == by_name["base14.gen_ai.retry.count"]["value"]
        )
        assert metric_total("base14.gen_ai.fallback.count", fallback_attrs) - fallbacks_before == 1
        assert (
            metric_total("base14.gen_ai.error.count", {"gen_ai.provider.name": "anthropic"})
            - errors_before
            == 1
        )
        assert (
            metric_total("base14.gen_ai.cost", {"gen_ai.request.model": setup["fallback_model"]})
            > 0
        )
