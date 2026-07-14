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
        metadata={"ls_model_name": "claude-sonnet-4-6", "ls_provider": "anthropic"},
    )
    msg = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        response_metadata={"stop_reason": "end_turn"},
    )
    result = LLMResult(generations=[[ChatGeneration(message=msg)]])
    h.on_llm_end(result, run_id=rid)

    span = exporter.get_finished_spans()[0]
    assert span.name == "chat claude-sonnet-4-6"
    assert span.attributes["gen_ai.operation.name"] == "chat"
    assert span.attributes["gen_ai.provider.name"] == "anthropic"
    assert span.attributes["gen_ai.usage.input_tokens"] == 100
    assert span.attributes["gen_ai.usage.output_tokens"] == 20


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
