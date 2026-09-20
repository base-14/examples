"""LLM client tests driven by the shared test vectors.

Each test loads a vector from `_shared/test-vectors`, drives the client with a
fake provider SDK that behaves as the vector describes, and asserts the spans
and metrics that reach the in-memory exporters.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import Histogram, Sum
from opentelemetry.trace import SpanKind, StatusCode

from sales_intelligence.llm import LLMClient
from tests.conftest import METRIC_READER


VECTORS_DIR = Path(__file__).parents[3] / "_shared" / "test-vectors"

COST_ATTRIBUTE = "base14.gen_ai.cost_usd"


def load_vector(name: str) -> dict[str, Any]:
    with (VECTORS_DIR / name).open() as f:
        data: dict[str, Any] = json.load(f)
    return data


def anthropic_response(mock: dict[str, Any]) -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=mock["content"])]
    response.usage = MagicMock(
        input_tokens=mock["input_tokens"], output_tokens=mock["output_tokens"]
    )
    response.model = mock["model"]
    response.id = mock["response_id"]
    response.stop_reason = mock["finish_reason"]
    return response


def openai_response(mock: dict[str, Any]) -> MagicMock:
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(content=mock["content"]),
            finish_reason=mock["finish_reason"],
        )
    ]
    response.usage = MagicMock(
        prompt_tokens=mock["input_tokens"], completion_tokens=mock["output_tokens"]
    )
    response.model = mock["model"]
    response.id = mock["response_id"]
    return response


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


def client_for(setup: dict[str, Any]) -> LLMClient:
    """Build a client whose primary and fallback match the vector's setup."""
    with patch("sales_intelligence.llm.get_settings") as get_settings:
        settings = MagicMock()
        settings.llm_provider = setup["provider"]
        settings.llm_model_capable = setup["model"]
        settings.llm_model_fast = setup["model"]
        settings.fallback_provider = setup["fallback_provider"]
        settings.fallback_model = setup["fallback_model"]
        settings.default_temperature = setup.get("temperature", 0.7)
        settings.default_max_tokens = setup.get("max_tokens", 1024)
        settings.anthropic_api_key = ""
        settings.google_api_key = ""
        settings.openai_api_key = ""
        settings.ollama_base_url = "http://localhost:11434"
        get_settings.return_value = settings
        return LLMClient()


def find_span(spans: Any, name: str) -> Any:
    matches = [s for s in spans if s.name == name]
    assert matches, f"span {name!r} not found in {[s.name for s in spans]}"
    return matches[0]


@pytest.fixture
def content_capture_off():
    """Content capture defaults to off, as the contract requires."""
    with patch("sales_intelligence.llm.get_settings") as get_settings:
        get_settings.return_value = MagicMock(
            otel_instrumentation_genai_capture_message_content=False
        )
        yield


@pytest.fixture
def content_capture_on():
    with patch("sales_intelligence.llm.get_settings") as get_settings:
        get_settings.return_value = MagicMock(
            otel_instrumentation_genai_capture_message_content=True
        )
        yield


class TestChatCompletionVector:
    """_shared/test-vectors/chat-completion.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-completion.json")

    async def test_span_and_metrics(self, vector, span_exporter, content_capture_off):
        expected = vector["expected_span"]
        request = vector["input"]
        setup = {
            "provider": request["provider"],
            "model": request["model"],
            "fallback_provider": "openai",
            "fallback_model": "gpt-4.1-mini",
            "temperature": request["temperature"],
            "max_tokens": request["max_tokens"],
        }
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

        with patch("anthropic.AsyncAnthropic") as anthropic_cls:
            anthropic_cls.return_value.messages.create = AsyncMock(
                return_value=anthropic_response(vector["mock_response"])
            )
            result = await client_for(setup).generate(
                prompt=request["prompt"], system=request["system"]
            )

        assert result == vector["mock_response"]["content"]

        span = find_span(span_exporter.get_finished_spans(), expected["name"])
        assert span.kind is SpanKind.CLIENT
        # The vector's "OK" means "not failed". Instrumentation leaves a
        # successful span UNSET rather than setting OK explicitly.
        assert span.status.status_code is not StatusCode.ERROR

        for key, value in expected["attributes"].items():
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
    ):
        request = vector["input"]
        setup = {
            "provider": request["provider"],
            "model": request["model"],
            "fallback_provider": "openai",
            "fallback_model": "gpt-4.1-mini",
        }

        with patch("anthropic.AsyncAnthropic") as anthropic_cls:
            anthropic_cls.return_value.messages.create = AsyncMock(
                return_value=anthropic_response(vector["mock_response"])
            )
            await client_for(setup).generate(prompt=request["prompt"], system=request["system"])

        span = find_span(span_exporter.get_finished_spans(), vector["expected_span"]["name"])
        expected_event = vector["expected_span"]["events"][0]["name"]
        assert [e.name for e in span.events] == [expected_event]

        event = span.events[0]
        assert event.attributes["gen_ai.input.messages"] == request["prompt"]
        assert event.attributes["gen_ai.system_instructions"] == request["system"]
        assert event.attributes["gen_ai.output.messages"] == vector["mock_response"]["content"]


class TestChatWithRetryVector:
    """_shared/test-vectors/chat-with-retry.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-with-retry.json")

    async def test_retry_is_transparent(self, vector, span_exporter, content_capture_off):
        setup = vector["setup"]
        behavior = vector["mock_behavior"]
        expected = vector["expected_span"]
        retry_metric = next(
            m for m in vector["expected_metrics"] if m["name"] == "base14.gen_ai.retry.count"
        )
        retries_before = metric_total("base14.gen_ai.retry.count", retry_metric["attrs"])
        fallbacks_before = metric_total("base14.gen_ai.fallback.count", {})
        errors_before = metric_total("base14.gen_ai.error.count", {})

        assert "raise Exception" in behavior["attempt_1"]
        with patch("anthropic.AsyncAnthropic") as anthropic_cls:
            anthropic_cls.return_value.messages.create = AsyncMock(
                side_effect=[
                    Exception("Rate limit"),
                    anthropic_response(behavior["attempt_2"]),
                ]
            )
            result = await client_for(setup).generate(prompt="Hello", system="You are helpful.")

        assert result == behavior["attempt_2"]["content"]

        span = find_span(span_exporter.get_finished_spans(), expected["name"])
        assert span.status.status_code is not StatusCode.ERROR
        for key, value in expected["attributes"].items():
            assert span.attributes[key] == value

        assert (
            metric_total("base14.gen_ai.retry.count", retry_metric["attrs"]) - retries_before
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
    ):
        setup = vector["setup"]
        client_setup = {
            "provider": setup["primary_provider"],
            "model": setup["primary_model"],
            "fallback_provider": setup["fallback_provider"],
            "fallback_model": setup["fallback_model"],
        }
        primary, fallback = vector["expected_spans"]
        metrics_by_name = {m["name"]: m for m in vector["expected_metrics"]}

        retries_before = metric_total("base14.gen_ai.retry.count", {})
        fallbacks_before = metric_total(
            "base14.gen_ai.fallback.count", metrics_by_name["base14.gen_ai.fallback.count"]["attrs"]
        )
        errors_before = metric_total(
            "base14.gen_ai.error.count", metrics_by_name["base14.gen_ai.error.count"]["attrs"]
        )
        primary_tokens_before = metric_total(
            "gen_ai.client.token.usage", {"gen_ai.request.model": setup["primary_model"]}
        )

        tracer = trace.get_tracer(__name__)
        with (
            patch("anthropic.AsyncAnthropic") as anthropic_cls,
            patch("openai.AsyncOpenAI") as openai_cls,
        ):
            anthropic_cls.return_value.messages.create = AsyncMock(
                side_effect=Exception("Service unavailable")
            )
            openai_cls.return_value.chat.completions.create = AsyncMock(
                return_value=openai_response(vector["mock_behavior"]["fallback"])
            )
            with tracer.start_as_current_span("pipeline.run"):
                result = await client_for(client_setup).generate(
                    prompt="Hello", system="You are helpful."
                )

        assert result == vector["mock_behavior"]["fallback"]["content"]

        spans = span_exporter.get_finished_spans()
        primary_span = find_span(spans, primary["name"])
        assert primary_span.status.status_code is StatusCode.ERROR
        for key, value in primary["attributes"].items():
            assert primary_span.attributes[key] == value

        fallback_span = find_span(spans, fallback["name"])
        assert fallback_span.status.status_code is not StatusCode.ERROR
        for key, value in fallback["attributes"].items():
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
