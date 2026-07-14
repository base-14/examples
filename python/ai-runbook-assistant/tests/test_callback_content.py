import json
from uuid import uuid4

from langchain_core.messages import AIMessage
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


def test_completion_content_captured_when_enabled(monkeypatch):
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    from runbook_assistant.config import get_settings

    get_settings.cache_clear()
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer)
    rid = uuid4()
    h.on_chat_model_start(
        {},
        [[]],
        run_id=rid,
        parent_run_id=None,
        metadata={"ls_model_name": "qwen3.5:9B", "ls_provider": "ollama"},
    )
    msg = AIMessage(content="raise the memory limit")
    h.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id=rid)

    span = exporter.get_finished_spans()[0]
    events = [e for e in span.events if "gen_ai.output.messages" in e.attributes]
    assert events, "expected a gen_ai.output.messages event"
    out = json.loads(events[0].attributes["gen_ai.output.messages"])
    assert out[0]["role"] == "assistant"
    assert out[0]["content"] == "raise the memory limit"
