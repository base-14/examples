"""LLM client tests driven by the shared test vectors.

Each test loads a vector from `_shared/test-vectors`, drives the client with the
real provider SDK answering from a mock transport, and asserts the spans and
metrics that reach the in-memory exporters. The spans come from the OpenTelemetry
GenAI instrumentations, so two things differ from the vectors, which were written
for one hand-written span per call: every retry attempt is its own span, and a
failed attempt's `error.type` is the SDK's exception class, such as
`InternalServerError`, not `Exception`.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import Histogram, Sum
from opentelemetry.trace import SpanKind, StatusCode

from sales_intelligence.llm import LLMClient
from tests.conftest import METRIC_READER
from tests.sdk_transports import (
    anthropic_message,
    anthropic_responses,
    openai_completion,
    openai_responses,
)


VECTORS_DIR = Path(__file__).parents[3] / "_shared" / "test-vectors"

COST_ATTRIBUTE = "base14.gen_ai.cost_usd"


def load_vector(name: str) -> dict[str, Any]:
    with (VECTORS_DIR / name).open() as f:
        data: dict[str, Any] = json.load(f)
    return data


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
        settings.anthropic_api_key = "test-key"
        settings.google_api_key = "test-key"
        settings.openai_api_key = "test-key"
        settings.ollama_base_url = "http://localhost:11434"
        get_settings.return_value = settings
        return LLMClient()


def find_span(spans: Any, name: str) -> Any:
    matches = [s for s in spans if s.name == name]
    assert matches, f"span {name!r} not found in {[s.name for s in spans]}"
    return matches[0]


# Where the instrumentation's span differs from a vector written for the hand-written
# span: Anthropic's `end_turn` is reported as the convention's `stop`, and the
# instrumentations leave out `server.port` when it is the default 443.
INSTRUMENTATION_VALUES: dict[str, Any] = {"gen_ai.response.finish_reasons": ["stop"]}
DEFAULT_PORT = 443


def assert_attributes(span: Any, expected: dict[str, Any]) -> None:
    for key, vector_value in expected.items():
        if key == "server.port" and vector_value == DEFAULT_PORT:
            assert key not in span.attributes
            continue
        value = INSTRUMENTATION_VALUES.get(key, vector_value)
        if key == COST_ATTRIBUTE:
            assert span.attributes[key] == pytest.approx(value, rel=0.01)
        elif isinstance(value, list):
            assert list(span.attributes[key]) == value
        else:
            assert span.attributes[key] == value, key


@pytest.fixture(autouse=True)
def api_keys():
    """Providers are built on first use, after `client_for` has returned."""
    with patch("sales_intelligence.llm._get_api_key", return_value="test-key"):
        yield


@pytest.fixture
def content_capture_off():
    """Content capture defaults to off, as the contract requires."""


@pytest.fixture
def content_capture_on(capture_content):
    """See `capture_content` in conftest."""


def model_spans(spans: Any, name: str) -> list[Any]:
    return [s for s in spans if s.name == name]


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

        with anthropic_responses([anthropic_message(vector["mock_response"])]):
            result = await client_for(setup).generate(
                prompt=request["prompt"], system=request["system"]
            )

        assert result == vector["mock_response"]["content"]

        span = find_span(span_exporter.get_finished_spans(), expected["name"])
        assert span.kind is SpanKind.CLIENT
        # The vector's "OK" means "not failed". Instrumentation leaves a
        # successful span UNSET rather than setting OK explicitly.
        assert span.status.status_code is not StatusCode.ERROR

        assert_attributes(span, expected["attributes"])

        assert "gen_ai.input.messages" not in span.attributes, "content capture is off"

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

    async def test_content_on_span_when_capture_is_on(
        self, vector, span_exporter, content_capture_on
    ):
        request = vector["input"]
        setup = {
            "provider": request["provider"],
            "model": request["model"],
            "fallback_provider": "openai",
            "fallback_model": "gpt-4.1-mini",
        }

        with anthropic_responses([anthropic_message(vector["mock_response"])]):
            await client_for(setup).generate(prompt=request["prompt"], system=request["system"])

        span = find_span(span_exporter.get_finished_spans(), vector["expected_span"]["name"])
        assert request["prompt"] in span.attributes["gen_ai.input.messages"]
        assert request["system"] in span.attributes["gen_ai.system_instructions"]
        assert vector["mock_response"]["content"] in span.attributes["gen_ai.output.messages"]


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
        fallbacks_before = metric_total("base14.gen_ai.fallback.count", {})
        errors_before = metric_total("base14.gen_ai.error.count", {})

        assert "raise Exception" in behavior["attempt_1"]
        retry_attrs = {**retry_metric["attrs"], "error.type": "RateLimitError"}
        retries_before = metric_total("base14.gen_ai.retry.count", retry_attrs)
        with anthropic_responses([429, anthropic_message(behavior["attempt_2"])]):
            result = await client_for(setup).generate(prompt="Hello", system="You are helpful.")

        assert result == behavior["attempt_2"]["content"]

        failed, succeeded = model_spans(span_exporter.get_finished_spans(), expected["name"])
        assert failed.status.status_code is StatusCode.ERROR
        assert succeeded.status.status_code is not StatusCode.ERROR
        assert_attributes(succeeded, expected["attributes"])

        assert (
            metric_total("base14.gen_ai.retry.count", retry_attrs) - retries_before
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
        error_attrs = {
            **metrics_by_name["base14.gen_ai.error.count"]["attrs"],
            "error.type": "InternalServerError",
        }
        errors_before = metric_total("base14.gen_ai.error.count", error_attrs)
        primary_tokens_before = metric_total(
            "gen_ai.client.token.usage", {"gen_ai.request.model": setup["primary_model"]}
        )

        tracer = trace.get_tracer(__name__)
        with (
            anthropic_responses([503, 503, 503]),
            openai_responses([openai_completion(vector["mock_behavior"]["fallback"])]),
            tracer.start_as_current_span("pipeline.run"),
        ):
            result = await client_for(client_setup).generate(
                prompt="Hello", system="You are helpful."
            )

        assert result == vector["mock_behavior"]["fallback"]["content"]

        spans = span_exporter.get_finished_spans()
        primary_spans = model_spans(spans, primary["name"])
        assert len(primary_spans) == 3, "one span per attempt"
        for primary_span in primary_spans:
            assert primary_span.status.status_code is StatusCode.ERROR
            assert primary_span.attributes["gen_ai.provider.name"] == "anthropic"
            assert primary_span.attributes["error.type"].endswith("InternalServerError")

        fallback_span = find_span(spans, fallback["name"])
        assert fallback_span.status.status_code is not StatusCode.ERROR
        assert_attributes(fallback_span, fallback["attributes"])

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
            metric_total("base14.gen_ai.error.count", error_attrs) - errors_before
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
