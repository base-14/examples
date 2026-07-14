from uuid import uuid4

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


def _tracer_with_exporter():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def test_intermediate_chain_suppressed_children_nest_under_root():
    tracer, exporter = _tracer_with_exporter()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer, agent_name="runbook_assistant")
    root, mid, tool = uuid4(), uuid4(), uuid4()

    h.on_chain_start({"name": "LangGraph"}, {}, run_id=root, parent_run_id=None)
    h.on_chain_start({"name": "tools"}, {}, run_id=mid, parent_run_id=root)
    h.on_tool_start({"name": "search_runbooks"}, "disk full", run_id=tool, parent_run_id=mid)
    h.on_tool_end("ok", run_id=tool)
    h.on_chain_end({}, run_id=mid, parent_run_id=root)
    h.on_chain_end({}, run_id=root, parent_run_id=None)

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert set(spans) == {
        "invoke_agent runbook_assistant",
        "execute_tool search_runbooks",
    }
    root_span = spans["invoke_agent runbook_assistant"]
    tool_span = spans["execute_tool search_runbooks"]
    assert tool_span.parent.span_id == root_span.context.span_id


def test_conversation_id_set_on_root():
    tracer, exporter = _tracer_with_exporter()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer, agent_name="a", conversation_id="conv-1")
    root = uuid4()
    h.on_chain_start({"name": "g"}, {}, run_id=root, parent_run_id=None)
    h.on_chain_end({}, run_id=root, parent_run_id=None)

    span = exporter.get_finished_spans()[0]
    assert span.attributes["gen_ai.conversation.id"] == "conv-1"
