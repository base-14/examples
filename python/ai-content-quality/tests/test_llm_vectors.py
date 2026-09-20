"""LLM client tests driven by the shared test vectors.

Each test loads a vector from `_shared/test-vectors`, drives the LLM client
with a fake LlamaIndex `LLM` that behaves as the vector describes, and
asserts the spans and metrics that reach the in-memory exporters.

content-quality wraps LlamaIndex's `LLM.achat()` rather than calling a
provider SDK directly, and returns structured JSON validated against a
Pydantic schema rather than a raw string. The vectors describe raw
provider responses, so `mock_response.content` is wrapped as
`{"answer": "<content>"}` JSON to satisfy the structured-output parser,
and requests go through a mocked `LLM` object instead of a patched
provider SDK client. `gen_ai.request.max_tokens` is not part of
content-quality's span attributes (LlamaIndex does not surface a
request max_tokens knob here), so it is excluded from the attribute
comparisons below.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import Histogram, Sum
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import BaseModel

from content_quality.services.llm import LLMClient
from tests.conftest import METRIC_READER


VECTORS_DIR = Path(__file__).parents[3] / "_shared" / "test-vectors"

COST_ATTRIBUTE = "base14.gen_ai.cost_usd"
SKIPPED_ATTRIBUTES = {"gen_ai.request.max_tokens"}


class AnswerResult(BaseModel):
    answer: str


def load_vector(name: str) -> dict[str, Any]:
    with (VECTORS_DIR / name).open() as f:
        data: dict[str, Any] = json.load(f)
    return data


def make_llm(model_name: str, temperature: float = 0.7) -> MagicMock:
    llm = MagicMock()
    llm.metadata.model_name = model_name
    llm.temperature = temperature
    return llm


def chat_response(mock: dict[str, Any]) -> MagicMock:
    """Build a fake LlamaIndex chat response from a vector's mock_response block."""
    response = MagicMock()
    response.message.content = json.dumps({"answer": mock["content"]})
    response.additional_kwargs = {
        "prompt_tokens": mock["input_tokens"],
        "completion_tokens": mock["output_tokens"],
        "model": mock["model"],
        "id": mock["response_id"],
        "finish_reason": mock["finish_reason"],
    }
    response.raw = None
    return response


def make_prompt_template(prompt: str) -> MagicMock:
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


def metric_count(name: str, attrs: dict[str, Any]) -> int:
    """Number of histogram observations over points matching attrs."""
    count = 0
    data = METRIC_READER.get_metrics_data()
    if data is None:
        return count
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name != name or not isinstance(metric.data, Histogram):
                    continue
                for point in metric.data.data_points:
                    if all(point.attributes.get(k) == v for k, v in attrs.items()):
                        count += point.count
    return count


def find_span(spans: Any, name: str) -> Any:
    matches = [s for s in spans if s.name == name]
    assert matches, f"span {name!r} not found in {[s.name for s in spans]}"
    return matches[0]


@pytest.fixture
def content_capture_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", raising=False)


@pytest.fixture
def content_capture_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")


class TestChatCompletionVector:
    """_shared/test-vectors/chat-completion.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-completion.json")

    async def test_span_and_metrics(self, vector, span_exporter, content_capture_off) -> None:
        request = vector["input"]
        expected = vector["expected_span"]
        client = LLMClient(
            provider=request["provider"],
            model=request["model"],
            llm=make_llm(request["model"], request["temperature"]),
        )

        token_attrs = {"gen_ai.request.model": request["model"]}
        input_attrs = {**token_attrs, "gen_ai.token.type": "input"}
        output_attrs = {**token_attrs, "gen_ai.token.type": "output"}
        input_before = metric_total("gen_ai.client.token.usage", input_attrs)
        output_before = metric_total("gen_ai.client.token.usage", output_attrs)
        cost_before = metric_total("base14.gen_ai.cost", token_attrs)
        retries_before = metric_total("base14.gen_ai.retry.count", {})
        fallbacks_before = metric_total("base14.gen_ai.fallback.count", {})
        errors_before = metric_total("base14.gen_ai.error.count", {})
        durations_before = metric_count("gen_ai.client.operation.duration", token_attrs)

        client.llm.achat = AsyncMock(return_value=chat_response(vector["mock_response"]))
        result = await client.generate_structured(
            make_prompt_template(request["prompt"]),
            AnswerResult,
            request["prompt"],
            endpoint="/review",
            system_prompt=request["system"],
        )

        assert result.answer == vector["mock_response"]["content"]

        span = find_span(span_exporter.get_finished_spans(), expected["name"])
        assert span.kind is SpanKind.CLIENT
        assert span.status.status_code is not StatusCode.ERROR

        for key, value in expected["attributes"].items():
            if key in SKIPPED_ATTRIBUTES:
                continue
            if key == COST_ATTRIBUTE:
                assert span.attributes[key] == pytest.approx(value, rel=0.01)
            elif isinstance(value, list):
                assert list(span.attributes[key]) == value
            else:
                assert span.attributes[key] == value

        assert [e.name for e in span.events] == [], (
            "content capture is off, so no inference event is expected"
        )

        assert metric_total("gen_ai.client.token.usage", input_attrs) - input_before == (
            pytest.approx(vector["mock_response"]["input_tokens"])
        )
        assert metric_total("gen_ai.client.token.usage", output_attrs) - output_before == (
            pytest.approx(vector["mock_response"]["output_tokens"])
        )
        assert metric_count("gen_ai.client.operation.duration", token_attrs) == (
            durations_before + 1
        )
        assert metric_total("base14.gen_ai.cost", token_attrs) - cost_before == pytest.approx(
            expected["attributes"][COST_ATTRIBUTE], rel=0.01
        )

        assert metric_total("base14.gen_ai.retry.count", {}) == retries_before
        assert metric_total("base14.gen_ai.fallback.count", {}) == fallbacks_before
        assert metric_total("base14.gen_ai.error.count", {}) == errors_before

    async def test_inference_event_when_capture_is_on(
        self, vector, span_exporter, content_capture_on
    ) -> None:
        request = vector["input"]
        client = LLMClient(
            provider=request["provider"],
            model=request["model"],
            llm=make_llm(request["model"], request["temperature"]),
        )
        client.llm.achat = AsyncMock(return_value=chat_response(vector["mock_response"]))

        await client.generate_structured(
            make_prompt_template(request["prompt"]),
            AnswerResult,
            request["prompt"],
            endpoint="/review",
            system_prompt=request["system"],
        )

        span = find_span(span_exporter.get_finished_spans(), vector["expected_span"]["name"])
        expected_event = vector["expected_span"]["events"][0]["name"]
        assert [e.name for e in span.events] == [expected_event]

        event = span.events[0]
        assert event.attributes["gen_ai.input.messages"] == request["prompt"]
        assert event.attributes["gen_ai.system_instructions"] == request["system"]
        assert (
            json.loads(event.attributes["gen_ai.output.messages"])["answer"]
            == vector["mock_response"]["content"]
        )


class TestChatWithRetryVector:
    """_shared/test-vectors/chat-with-retry.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-with-retry.json")

    async def test_retry_is_transparent(self, vector, span_exporter, content_capture_off) -> None:
        setup = vector["setup"]
        behavior = vector["mock_behavior"]
        expected = vector["expected_span"]
        retry_metric = next(
            m for m in vector["expected_metrics"] if m["name"] == "base14.gen_ai.retry.count"
        )
        retries_before = metric_total(
            "base14.gen_ai.retry.count",
            {"gen_ai.provider.name": retry_metric["attrs"]["gen_ai.provider.name"]},
        )
        fallbacks_before = metric_total("base14.gen_ai.fallback.count", {})
        errors_before = metric_total("base14.gen_ai.error.count", {})

        assert "raise Exception" in behavior["attempt_1"]
        client = LLMClient(
            provider=setup["provider"],
            model=setup["model"],
            llm=make_llm(setup["model"]),
        )
        client.llm.achat = AsyncMock(
            side_effect=[
                Exception("Rate limit"),
                chat_response(behavior["attempt_2"]),
            ]
        )

        result = await client.generate_structured(
            make_prompt_template("Hello"), AnswerResult, "Hello", endpoint="/review"
        )

        assert result.answer == behavior["attempt_2"]["content"]

        span = find_span(span_exporter.get_finished_spans(), expected["name"])
        assert span.status.status_code is not StatusCode.ERROR
        for key, value in expected["attributes"].items():
            if key in SKIPPED_ATTRIBUTES:
                continue
            assert span.attributes[key] == value

        assert (
            metric_total(
                "base14.gen_ai.retry.count",
                {"gen_ai.provider.name": retry_metric["attrs"]["gen_ai.provider.name"]},
            )
            - retries_before
            == retry_metric["value"]
        )
        assert metric_total("base14.gen_ai.fallback.count", {}) == fallbacks_before
        assert metric_total("base14.gen_ai.error.count", {}) == errors_before


class TestChatWithFallbackVector:
    """_shared/test-vectors/chat-with-fallback.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-with-fallback.json")

    async def test_primary_fails_and_fallback_succeeds(
        self, vector, span_exporter, content_capture_off
    ) -> None:
        setup = vector["setup"]
        primary, fallback = vector["expected_spans"]
        metrics_by_name = {m["name"]: m for m in vector["expected_metrics"]}

        retries_before = metric_total("base14.gen_ai.retry.count", {})
        fallbacks_before = metric_total(
            "base14.gen_ai.fallback.count",
            metrics_by_name["base14.gen_ai.fallback.count"]["attrs"],
        )
        errors_before = metric_total(
            "base14.gen_ai.error.count", metrics_by_name["base14.gen_ai.error.count"]["attrs"]
        )
        primary_tokens_before = metric_total(
            "gen_ai.client.token.usage", {"gen_ai.request.model": setup["primary_model"]}
        )

        primary_llm = make_llm(setup["primary_model"])
        primary_llm.achat = AsyncMock(side_effect=Exception("Service unavailable"))
        fallback_llm = make_llm(setup["fallback_model"])
        fallback_llm.achat = AsyncMock(
            return_value=chat_response(vector["mock_behavior"]["fallback"])
        )

        client = LLMClient(
            provider=setup["primary_provider"],
            model=setup["primary_model"],
            llm=primary_llm,
            fallback_provider=setup["fallback_provider"],
            fallback_model=setup["fallback_model"],
            fallback_llm=fallback_llm,
        )

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("pipeline.run"):
            result = await client.generate_structured(
                make_prompt_template("Hello"), AnswerResult, "Hello", endpoint="/review"
            )

        assert result.answer == vector["mock_behavior"]["fallback"]["content"]

        spans = span_exporter.get_finished_spans()
        primary_span = find_span(spans, primary["name"])
        assert primary_span.status.status_code is StatusCode.ERROR
        for key, value in primary["attributes"].items():
            if key in SKIPPED_ATTRIBUTES:
                continue
            assert primary_span.attributes[key] == value

        fallback_span = find_span(spans, fallback["name"])
        assert fallback_span.status.status_code is not StatusCode.ERROR
        for key, value in fallback["attributes"].items():
            if key in SKIPPED_ATTRIBUTES:
                continue
            assert fallback_span.attributes[key] == value

        parent_span = find_span(spans, "pipeline.run")
        assert parent_span.status.status_code is not StatusCode.ERROR
        assert parent_span.attributes["gen_ai.fallback.triggered"] is True
        fallback_event = next(e for e in parent_span.events if e.name == "provider_fallback")
        assert (
            fallback_event.attributes["base14.gen_ai.fallback.provider"]
            == setup["fallback_provider"]
        )

        assert (
            metric_total("base14.gen_ai.retry.count", {}) - retries_before
            == metrics_by_name["base14.gen_ai.retry.count"]["value"]
        )
        assert (
            metric_total(
                "base14.gen_ai.fallback.count",
                metrics_by_name["base14.gen_ai.fallback.count"]["attrs"],
            )
            - fallbacks_before
            == metrics_by_name["base14.gen_ai.fallback.count"]["value"]
        )
        assert (
            metric_total(
                "base14.gen_ai.error.count",
                metrics_by_name["base14.gen_ai.error.count"]["attrs"],
            )
            - errors_before
            == metrics_by_name["base14.gen_ai.error.count"]["value"]
        )

        fallback_tokens = {"gen_ai.request.model": setup["fallback_model"]}
        assert metric_total(
            "gen_ai.client.token.usage", {**fallback_tokens, "gen_ai.token.type": "input"}
        ) == pytest.approx(vector["mock_behavior"]["fallback"]["input_tokens"])
        assert metric_total("base14.gen_ai.cost", fallback_tokens) > 0
        assert (
            metric_total(
                "gen_ai.client.token.usage", {"gen_ai.request.model": setup["primary_model"]}
            )
            == primary_tokens_before
        )
