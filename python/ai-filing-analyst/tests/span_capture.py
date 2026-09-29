from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from filing_analyst.telemetry import (
    AgentRunAttributesProcessor,
    CostAndErrorAttributingSpanExporter,
)


_memory: InMemorySpanExporter | None = None


def captured_spans() -> InMemorySpanExporter:
    """The process-wide tracer provider, set once, exporting through the example's exporter.
    Strands reads the global provider, so tests share it and clear it first."""
    global _memory
    if _memory is None:
        _memory = InMemorySpanExporter()
        provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
        provider.add_span_processor(AgentRunAttributesProcessor())
        provider.add_span_processor(
            SimpleSpanProcessor(CostAndErrorAttributingSpanExporter(_memory))
        )
        trace.set_tracer_provider(provider)
    _memory.clear()
    return _memory


def named(spans: tuple[ReadableSpan, ...], name: str) -> list[ReadableSpan]:
    return [span for span in spans if span.name == name]


def only(spans: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    (span,) = named(spans, name)
    return span
