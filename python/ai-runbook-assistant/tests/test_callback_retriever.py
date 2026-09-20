from uuid import uuid4

from langchain_core.documents import Document
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


def test_retrieval_span_has_chunk_count_and_store_endpoint():
    tracer, exporter = _tracer()
    from runbook_assistant.telemetry.callback import OTelCallbackHandler

    h = OTelCallbackHandler(
        tracer=tracer,
        data_source_id="runbooks",
        data_source_address="postgres",
        data_source_port=5432,
    )
    rid = uuid4()
    h.on_retriever_start({}, "disk full", run_id=rid)
    h.on_retriever_end([Document(page_content="a"), Document(page_content="b")], run_id=rid)
    span = exporter.get_finished_spans()[0]
    assert span.name == "retrieval runbooks"
    assert span.attributes["gen_ai.operation.name"] == "retrieval"
    assert span.attributes["gen_ai.data_source.id"] == "runbooks"
    assert span.attributes["server.address"] == "postgres"
    assert span.attributes["server.port"] == 5432
    assert span.attributes["app.retrieval.chunk_count"] == 2
