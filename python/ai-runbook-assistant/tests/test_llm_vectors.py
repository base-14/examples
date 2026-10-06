"""Agent model calls driven by the shared test vectors.

Each test loads a vector from `_shared/test-vectors`, runs the agent with
`ResilienceMiddleware` and a scripted model that behaves as the vector describes,
and asserts the spans and metrics that reach the in-memory exporters. The spans
come from the OpenTelemetry LangChain instrumentation, so every attempt is its own
`chat {model}` span: a retried attempt and a primary that gave way to the fallback
each leave a failed span, where the vectors, written for one span per logical
call, expect one.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from langchain.agents import create_agent
from opentelemetry.sdk.metrics.export import Histogram, Sum
from opentelemetry.trace import StatusCode

from runbook_assistant import llm
from runbook_assistant.agent import AGENT_NAME, run_diagnosis
from runbook_assistant.llm import ResilienceMiddleware
from tests.conftest import METRIC_READER
from tests.scripted_model import ScriptedChatModel, answer


VECTORS_DIR = Path(__file__).parents[3] / "_shared" / "test-vectors"

COST_ATTRIBUTE = "base14.gen_ai.cost_usd"


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_MIN_WAIT_S", 0)
    monkeypatch.setattr(llm, "RETRY_MAX_WAIT_S", 0)


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


def chat_spans(spans: Any, model: str) -> list[Any]:
    return [s for s in spans if s.name == f"chat {model}"]


def run_agent(
    primary: ScriptedChatModel,
    fallback: ScriptedChatModel | None = None,
    question: str = "Hello",
) -> str:
    middleware = ResilienceMiddleware(
        primary_provider=primary.provider,
        primary_model=primary.model,
        fallback=fallback,
        fallback_provider=fallback.provider if fallback else None,
        fallback_model=fallback.model if fallback else None,
    )
    agent = create_agent(model=primary, middleware=[middleware], name=AGENT_NAME)
    return run_diagnosis(agent, question, conversation_id="conv-1")


class TestChatCompletionVector:
    """_shared/test-vectors/chat-completion.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-completion.json")

    def test_span_and_metrics(self, vector, span_exporter):
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

        primary = ScriptedChatModel(
            provider="anthropic",
            model=request["model"],
            script=[answer(mock["content"], mock["input_tokens"], mock["output_tokens"])],
        )
        result = run_agent(primary, question=request["prompt"])

        assert result == mock["content"]
        (span,) = chat_spans(span_exporter.get_finished_spans(), request["model"])
        assert span.status.status_code is not StatusCode.ERROR
        expected = vector["expected_span"]["attributes"]
        for key in (
            "gen_ai.operation.name",
            "gen_ai.provider.name",
            "gen_ai.request.model",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
        ):
            assert span.attributes[key] == expected[key], key
        assert span.attributes[COST_ATTRIBUTE] == pytest.approx(expected[COST_ATTRIBUTE], rel=0.01)
        assert span.attributes["gen_ai.conversation.id"] == "conv-1"
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

    def test_content_is_captured_and_scrubbed(self, vector, span_exporter, capture_content):
        request = vector["input"]
        mock = vector["mock_response"]
        primary = ScriptedChatModel(
            provider="anthropic",
            model=request["model"],
            script=[answer("Mail ops@example.com", mock["input_tokens"], mock["output_tokens"])],
        )
        run_agent(primary, question="Node 10.0.0.7 is down")

        (span,) = chat_spans(span_exporter.get_finished_spans(), request["model"])
        assert "[ip]" in span.attributes["gen_ai.input.messages"]
        assert "10.0.0.7" not in span.attributes["gen_ai.input.messages"]
        assert "[email]" in span.attributes["gen_ai.output.messages"]
        assert "ops@example.com" not in span.attributes["gen_ai.output.messages"]


class TestChatWithRetryVector:
    """_shared/test-vectors/chat-with-retry.json"""

    @pytest.fixture
    def vector(self) -> dict[str, Any]:
        return load_vector("chat-with-retry.json")

    def test_retry_leaves_a_failed_attempt(self, vector, span_exporter):
        setup = vector["setup"]
        second = vector["mock_behavior"]["attempt_2"]
        retry_metric = next(
            m for m in vector["expected_metrics"] if m["name"] == "base14.gen_ai.retry.count"
        )
        retries_before = metric_total("base14.gen_ai.retry.count", retry_metric["attrs"])
        fallbacks_before = metric_total("base14.gen_ai.fallback.count", {})
        errors_before = metric_total("base14.gen_ai.error.count", {})

        assert "raise Exception" in vector["mock_behavior"]["attempt_1"]
        primary = ScriptedChatModel(
            provider=setup["provider"],
            model=setup["model"],
            script=[
                Exception("Rate limit"),
                answer(second["content"], second["input_tokens"], second["output_tokens"]),
            ],
        )
        assert run_agent(primary) == second["content"]

        failed, succeeded = chat_spans(span_exporter.get_finished_spans(), setup["model"])
        assert failed.status.status_code is StatusCode.ERROR
        assert succeeded.status.status_code is not StatusCode.ERROR
        assert succeeded.attributes["gen_ai.usage.input_tokens"] == second["input_tokens"]
        assert succeeded.attributes["gen_ai.usage.output_tokens"] == second["output_tokens"]

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

    def test_primary_fails_and_fallback_answers(self, vector, span_exporter):
        setup = vector["setup"]
        served = vector["mock_behavior"]["fallback"]
        by_name = {m["name"]: m for m in vector["expected_metrics"]}
        retries_before = metric_total("base14.gen_ai.retry.count", {})
        fallbacks_before = metric_total(
            "base14.gen_ai.fallback.count", by_name["base14.gen_ai.fallback.count"]["attrs"]
        )
        errors_before = metric_total(
            "base14.gen_ai.error.count", by_name["base14.gen_ai.error.count"]["attrs"]
        )

        primary = ScriptedChatModel(
            provider=setup["primary_provider"],
            model=setup["primary_model"],
            script=[Exception("Service unavailable")] * 3,
        )
        fallback = ScriptedChatModel(
            provider=setup["fallback_provider"],
            model=setup["fallback_model"],
            script=[answer(served["content"], served["input_tokens"], served["output_tokens"])],
        )
        assert run_agent(primary, fallback) == served["content"]

        spans = span_exporter.get_finished_spans()
        primary_spans = chat_spans(spans, setup["primary_model"])
        assert len(primary_spans) == 3, "one span per attempt"
        assert all(s.status.status_code is StatusCode.ERROR for s in primary_spans)
        (fallback_span,) = chat_spans(spans, setup["fallback_model"])
        assert fallback_span.status.status_code is not StatusCode.ERROR
        assert fallback_span.attributes["gen_ai.provider.name"] == setup["fallback_provider"]
        assert fallback_span.attributes["gen_ai.usage.input_tokens"] == served["input_tokens"]

        agent_span = next(s for s in spans if s.name == f"invoke_agent {AGENT_NAME}")
        assert agent_span.status.status_code is not StatusCode.ERROR
        assert agent_span.attributes["gen_ai.fallback.triggered"] is True
        event = next(e for e in agent_span.events if e.name == "provider_fallback")
        assert event.attributes["base14.gen_ai.fallback.provider"] == setup["fallback_provider"]

        assert (
            metric_total("base14.gen_ai.retry.count", {}) - retries_before
            == by_name["base14.gen_ai.retry.count"]["value"]
        )
        assert (
            metric_total(
                "base14.gen_ai.fallback.count", by_name["base14.gen_ai.fallback.count"]["attrs"]
            )
            - fallbacks_before
            == by_name["base14.gen_ai.fallback.count"]["value"]
        )
        assert (
            metric_total("base14.gen_ai.error.count", by_name["base14.gen_ai.error.count"]["attrs"])
            - errors_before
            == by_name["base14.gen_ai.error.count"]["value"]
        )
        assert (
            metric_total("base14.gen_ai.cost", {"gen_ai.request.model": setup["fallback_model"]})
            > 0
        )
