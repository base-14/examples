from uuid import uuid4

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode


def _tracer():
    p = TracerProvider()
    e = InMemorySpanExporter()
    p.add_span_processor(SimpleSpanProcessor(e))
    return p.get_tracer("test"), e


def test_tool_span_named_and_typed():
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer)
    rid = uuid4()
    h.on_tool_start({"name": "search_runbooks"}, "disk full", run_id=rid)
    h.on_tool_end("3 runbooks", run_id=rid)
    span = exporter.get_finished_spans()[0]
    assert span.name == "execute_tool search_runbooks"
    assert span.attributes["gen_ai.tool.name"] == "search_runbooks"
    assert span.attributes["gen_ai.operation.name"] == "execute_tool"


def test_tool_error_marks_span_error_and_parent_event():
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(tracer=tracer, agent_name="a")
    parent, child = uuid4(), uuid4()
    h.on_chain_start({"name": "g"}, {}, run_id=parent, parent_run_id=None)
    h.on_tool_start({"name": "query_metrics"}, "x", run_id=child, parent_run_id=parent)
    h.on_tool_error(ValueError("boom"), run_id=child, parent_run_id=parent)
    h.on_chain_end({}, run_id=parent, parent_run_id=None)

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["execute_tool query_metrics"].status.status_code == StatusCode.ERROR
    parent_span = spans["invoke_agent a"]
    assert parent_span.status.status_code != StatusCode.ERROR
    assert any(e.name == "tool_execution_failed" for e in parent_span.events)
