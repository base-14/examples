import json
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


def _tracer():
    p = TracerProvider()
    e = InMemorySpanExporter()
    p.add_span_processor(SimpleSpanProcessor(e))
    return p.get_tracer("test"), e


def _capture_on(monkeypatch):
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    from runbook_assistant.config import get_settings

    get_settings.cache_clear()


def test_no_content_capture_by_default(monkeypatch):
    monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", raising=False)
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer)
    rid = uuid4()
    h.on_tool_start({"name": "search_runbooks"}, "alice@example.com paged", run_id=rid)
    h.on_tool_end("ok", run_id=rid)
    span = exporter.get_finished_spans()[0]
    assert "gen_ai.tool.call.arguments" not in span.attributes


def test_one_details_event_carries_input_system_and_output(monkeypatch):
    _capture_on(monkeypatch)
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import DETAILS_EVENT, OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer)
    rid = uuid4()
    h.on_chat_model_start(
        {},
        [[SystemMessage(content="You are an SRE."), HumanMessage(content="node-7 disk full")]],
        run_id=rid,
        parent_run_id=None,
        metadata={"ls_model_name": "qwen3.5:9B", "ls_provider": "ollama"},
    )
    msg = AIMessage(content="raise the memory limit")
    h.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id=rid)

    span = exporter.get_finished_spans()[0]
    assert [e.name for e in span.events] == [DETAILS_EVENT]

    attributes = span.events[0].attributes
    assert json.loads(attributes["gen_ai.input.messages"]) == [
        {"role": "user", "content": "node-7 disk full"}
    ]
    assert attributes["gen_ai.system_instructions"] == "You are an SRE."
    assert json.loads(attributes["gen_ai.output.messages"]) == [
        {"role": "assistant", "content": "raise the memory limit"}
    ]


def test_captured_content_is_scrubbed(monkeypatch):
    _capture_on(monkeypatch)
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer)
    rid = uuid4()
    h.on_chat_model_start(
        {},
        [[HumanMessage(content="alice@example.com reported 10.0.0.4 is down")]],
        run_id=rid,
        parent_run_id=None,
        metadata={"ls_model_name": "qwen3.5:9B", "ls_provider": "ollama"},
    )
    h.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]]), run_id=rid
    )

    captured = exporter.get_finished_spans()[0].events[0].attributes["gen_ai.input.messages"]
    assert "alice@example.com" not in captured
    assert "10.0.0.4" not in captured
    assert "[email]" in captured
    assert "[ip]" in captured
