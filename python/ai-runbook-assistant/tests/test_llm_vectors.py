"""Chat model tests driven by the shared test vectors.

Each test loads a vector from `_shared/test-vectors`, drives
`ResilientChatModel` with a stand-in provider that behaves as the vector
describes, and asserts on the spans and metrics that reach the in-memory
exporters.

One provider attempt means one chat span: retries inside a provider are
invisible, and a switch to the fallback provider closes the primary's span as
failed and opens a second span for the provider that answered, with the switch
recorded as a `provider_fallback` event on the parent.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.runnables.config import set_config_context
from opentelemetry.sdk.metrics.export import Histogram, Sum
from opentelemetry.trace import SpanKind, StatusCode

from runbook_assistant.llm import ResilientChatModel
from runbook_assistant.telemetry.callback import DETAILS_EVENT, OTelCallbackHandler
from tests.conftest import METRIC_READER


VECTORS_DIR = Path(__file__).parents[3] / "_shared" / "test-vectors"

COST_ATTRIBUTE = "base14.gen_ai.cost_usd"


def load_vector(name: str) -> dict[str, Any]:
    with (VECTORS_DIR / name).open() as f:
        data: dict[str, Any] = json.load(f)
    return data


class VectorChatModel(BaseChatModel):
    """Stand-in provider that replays a vector's failures and responses."""

    pending: list[Any]

    @property
    def _llm_type(self) -> str:
        return "vector"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        item = self.pending.pop(0) if len(self.pending) > 1 else self.pending[0]
        if isinstance(item, Exception):
            raise item
        message = AIMessage(
            content=item["content"],
            usage_metadata={
                "input_tokens": item["input_tokens"],
                "output_tokens": item["output_tokens"],
                "total_tokens": item["input_tokens"] + item["output_tokens"],
            },
            response_metadata={
                "model_name": item["model"],
                "id": item["response_id"],
                "finish_reason": item["finish_reason"],
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, BaseMessage]:
        """Bind as a real provider does, by returning a RunnableBinding."""
        return self.bind(tools=list(tools), **kwargs)


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


def run_chat(model: ResilientChatModel, system: str, prompt: str) -> AIMessage:
    """Invoke the model inside a chain, so the chat run has a parent run."""
    chain = model | RunnablePassthrough()
    handler = OTelCallbackHandler(agent_name="runbook_assistant")
    message: AIMessage = chain.invoke(
        [SystemMessage(content=system), HumanMessage(content=prompt)],
        config={"callbacks": [handler]},
    )
    return message


class TestChatCompletionVector:
    """_shared/test-vectors/chat-completion.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-completion.json")

    def test_span_and_metrics(self, vector, span_exporter):
        request = vector["input"]
        expected = vector["expected_span"]
        model = ResilientChatModel(
            primary=VectorChatModel(pending=[vector["mock_response"]]),
            primary_provider=request["provider"],
            primary_model=request["model"],
            temperature=request["temperature"],
            max_tokens=request["max_tokens"],
        )

        token_attrs = {"gen_ai.request.model": request["model"]}
        input_attrs = {**token_attrs, "gen_ai.token.type": "input"}
        output_attrs = {**token_attrs, "gen_ai.token.type": "output"}
        input_before = metric_total("gen_ai.client.token.usage", input_attrs)
        output_before = metric_total("gen_ai.client.token.usage", output_attrs)
        cost_before = metric_total("base14.gen_ai.cost", token_attrs)
        durations_before = metric_count("gen_ai.client.operation.duration", token_attrs)
        retries_before = metric_total("base14.gen_ai.retry.count", {})
        fallbacks_before = metric_total("base14.gen_ai.fallback.count", {})
        errors_before = metric_total("base14.gen_ai.error.count", {})

        message = run_chat(model, request["system"], request["prompt"])
        assert message.content == vector["mock_response"]["content"]

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

    def test_one_inference_event_when_capture_is_on(self, vector, span_exporter, monkeypatch):
        from runbook_assistant.config import get_settings

        monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
        get_settings.cache_clear()

        request = vector["input"]
        model = ResilientChatModel(
            primary=VectorChatModel(pending=[vector["mock_response"]]),
            primary_provider=request["provider"],
            primary_model=request["model"],
            temperature=request["temperature"],
            max_tokens=request["max_tokens"],
        )
        run_chat(model, request["system"], request["prompt"])

        span = find_span(span_exporter.get_finished_spans(), vector["expected_span"]["name"])
        assert [e.name for e in span.events] == [vector["expected_span"]["events"][0]["name"]]
        assert span.events[0].name == DETAILS_EVENT

        attributes = span.events[0].attributes
        assert json.loads(attributes["gen_ai.input.messages"]) == [
            {"role": "user", "content": request["prompt"]}
        ]
        assert attributes["gen_ai.system_instructions"] == request["system"]
        assert json.loads(attributes["gen_ai.output.messages"]) == [
            {"role": "assistant", "content": vector["mock_response"]["content"]}
        ]


class TestBoundToolsSpanShape:
    """One chat span per call, including when the agent has bound tools."""

    def test_bound_tools_do_not_double_the_span(self, span_exporter):
        vector = load_vector("chat-completion.json")
        request = vector["input"]
        model = ResilientChatModel(
            primary=VectorChatModel(pending=[vector["mock_response"]]),
            primary_provider=request["provider"],
            primary_model=request["model"],
        ).bind_tools([{"name": "ping", "description": "ping", "parameters": {}}])

        # An agent invokes the model with the handler in the ambient config,
        # which is how a bound inner model can end up opening its own span.
        handler = OTelCallbackHandler(agent_name="runbook_assistant")
        config: dict[str, Any] = {"callbacks": [handler]}
        with set_config_context(config) as context:
            context.run(model.invoke, [HumanMessage(content=request["prompt"])], config=config)

        chat_spans = [s for s in span_exporter.get_finished_spans() if s.name.startswith("chat ")]
        assert [s.name for s in chat_spans] == [vector["expected_span"]["name"]]


class TestChatWithRetryVector:
    """_shared/test-vectors/chat-with-retry.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-with-retry.json")

    def test_retry_is_transparent(self, vector, span_exporter):
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
        model = ResilientChatModel(
            primary=VectorChatModel(
                pending=[Exception("Rate limit"), behavior["attempt_2"]],
            ),
            primary_provider=setup["provider"],
            primary_model=setup["model"],
        )
        message = run_chat(model, "You are helpful.", "Hello")
        assert message.content == behavior["attempt_2"]["content"]

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

    def test_primary_fails_and_fallback_succeeds(self, vector, span_exporter):
        setup = vector["setup"]
        served = vector["mock_behavior"]["fallback"]
        primary_expected, fallback_span = vector["expected_spans"]
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

        model = ResilientChatModel(
            primary=VectorChatModel(pending=[Exception("Service unavailable")]),
            primary_provider=setup["primary_provider"],
            primary_model=setup["primary_model"],
            fallback=VectorChatModel(pending=[served]),
            fallback_provider=setup["fallback_provider"],
            fallback_model=setup["fallback_model"],
        )
        message = run_chat(model, "You are helpful.", "Hello")
        assert message.content == served["content"]

        spans = span_exporter.get_finished_spans()
        primary_span = find_span(spans, primary_expected["name"])
        assert primary_span.status.status_code is StatusCode.ERROR
        for key, value in primary_expected["attributes"].items():
            assert primary_span.attributes[key] == value
        assert any(e.name == "exception" for e in primary_span.events)
        assert "gen_ai.usage.input_tokens" not in primary_span.attributes

        chat_span = find_span(spans, fallback_span["name"])
        assert chat_span.status.status_code is not StatusCode.ERROR
        for key, value in fallback_span["attributes"].items():
            assert chat_span.attributes[key] == value
        assert chat_span.parent.span_id == primary_span.parent.span_id, (
            "both provider attempts sit beside each other under the same parent"
        )
        assert primary_span.end_time <= chat_span.start_time

        parent = find_span(spans, "invoke_agent runbook_assistant")
        assert parent.status.status_code is not StatusCode.ERROR
        assert parent.attributes["gen_ai.fallback.triggered"] is True
        event = next(e for e in parent.events if e.name == "provider_fallback")
        assert event.attributes["gen_ai.provider.name"] == setup["primary_provider"]
        assert event.attributes["base14.gen_ai.fallback.provider"] == setup["fallback_provider"]
        assert event.attributes["error.type"] == "Exception"

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
        ) == pytest.approx(served["input_tokens"])
        assert metric_total("base14.gen_ai.cost", fallback_tokens) > 0
        assert (
            metric_total(
                "gen_ai.client.token.usage", {"gen_ai.request.model": setup["primary_model"]}
            )
            == primary_tokens_before
        )
