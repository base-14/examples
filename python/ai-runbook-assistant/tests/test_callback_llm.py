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


def test_chat_span_has_genai_attrs_and_tokens():
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer, agent_name="runbook_assistant")
    rid = uuid4()
    h.on_chat_model_start(
        {},
        [[]],
        run_id=rid,
        parent_run_id=None,
        metadata={
            "ls_model_name": "claude-sonnet-4-6",
            "ls_provider": "anthropic",
            "ls_temperature": 0.0,
            "ls_max_tokens": 4096,
        },
    )
    msg = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        response_metadata={"stop_reason": "end_turn", "id": "msg_abc"},
    )
    result = LLMResult(generations=[[ChatGeneration(message=msg)]])
    h.on_llm_end(result, run_id=rid)

    span = exporter.get_finished_spans()[0]
    assert span.name == "chat claude-sonnet-4-6"
    assert span.attributes["gen_ai.operation.name"] == "chat"
    assert span.attributes["gen_ai.provider.name"] == "anthropic"
    assert span.attributes["gen_ai.request.temperature"] == 0.0
    assert span.attributes["gen_ai.request.max_tokens"] == 4096
    assert span.attributes["gen_ai.response.id"] == "msg_abc"
    assert span.attributes["server.address"] == "api.anthropic.com"
    assert span.attributes["server.port"] == 443
    assert span.attributes["gen_ai.usage.input_tokens"] == 100
    assert span.attributes["gen_ai.usage.output_tokens"] == 20
    assert span.attributes["base14.gen_ai.cost_usd"] > 0


def test_gemini_reports_the_semconv_provider_name():
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer)
    rid = uuid4()
    h.on_chat_model_start(
        {},
        [[]],
        run_id=rid,
        parent_run_id=None,
        metadata={"ls_model_name": "gemini-3.6-flash", "ls_provider": "google_genai"},
    )
    h.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]]), run_id=rid
    )

    span = exporter.get_finished_spans()[0]
    assert span.attributes["gen_ai.provider.name"] == "gcp.gemini"
    assert span.attributes["server.address"] == "generativelanguage.googleapis.com"


def test_ollama_server_address_comes_from_the_base_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
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
    h.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]]), run_id=rid
    )

    span = exporter.get_finished_spans()[0]
    assert span.attributes["server.address"] == "host.docker.internal"
    assert span.attributes["server.port"] == 11434
    assert span.attributes["base14.gen_ai.cost_usd"] == 0.0


def test_ollama_result_shape_from_spike():
    """Phase 0 (Task 0) captured the real ChatOllama LLMResult shape; drive that
    exact shape through on_llm_end to prove the handler reads Ollama's
    done_reason + usage_metadata, not just synthetic cloud-provider shapes.
    Shape verified live in SPIKE-FINDINGS.md (Ollama 0.30.10, qwen3.5:9B)."""
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
    msg = AIMessage(
        content="Hello there friend",
        usage_metadata={
            "input_tokens": 16,
            "output_tokens": 1002,
            "total_tokens": 1018,
        },
        response_metadata={
            "model": "qwen3.5:9B",
            "done_reason": "stop",
            "model_name": "qwen3.5:9B",
            "model_provider": "ollama",
            "prompt_eval_count": 16,
            "eval_count": 1002,
        },
    )
    result = LLMResult(generations=[[ChatGeneration(message=msg)]])
    h.on_llm_end(result, run_id=rid)

    span = exporter.get_finished_spans()[0]
    assert span.name == "chat qwen3.5:9B"
    assert span.attributes["gen_ai.provider.name"] == "ollama"
    assert span.attributes["gen_ai.usage.input_tokens"] == 16
    assert span.attributes["gen_ai.usage.output_tokens"] == 1002
    assert list(span.attributes["gen_ai.response.finish_reasons"]) == ["stop"]
    assert span.attributes["gen_ai.response.model"] == "qwen3.5:9B"


def test_llm_error_marks_the_span_and_counts_the_error():
    tracer, exporter = _tracer()
    from opentelemetry.trace import StatusCode

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
    h.on_llm_error(TimeoutError("upstream gone"), run_id=rid)

    span = exporter.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "TimeoutError"
    assert any(e.name == "exception" for e in span.events)
