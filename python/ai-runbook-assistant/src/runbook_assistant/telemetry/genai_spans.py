"""Enrichment of the spans the OpenTelemetry LangChain instrumentation creates.

The instrumentation puts the conversation ID from the run's metadata on agent and
chat spans only, and names a retrieval span's provider after the vector store class,
with no data source. `RunAttributesProcessor` adds the conversation ID to the other
spans and the data source to retrieval spans when they start.
`GenAISpanExporter` adds the cost of each model call and scrubs PII from captured
content when the span is exported, because both need values that exist only once
the span has finished.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from opentelemetry import context as otel_context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.util import BoundedList

from runbook_assistant.cost import calculate_cost
from runbook_assistant.pii import scrub


LANGCHAIN_SCOPE = "opentelemetry.instrumentation.genai.langchain"
COST_ATTRIBUTE = "base14.gen_ai.cost_usd"
CONTENT_ATTRIBUTES = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "gen_ai.retrieval.query.text",
)

type AttributeValue = str | bool | int | float


@dataclass(frozen=True)
class DataSource:
    """The vector store the agent retrieves from."""

    id: str
    address: str | None = None
    port: int | None = None


@dataclass(frozen=True)
class RunAttributes:
    """What the application knows about one agent run that the instrumentation does not."""

    conversation_id: str


_run: ContextVar[RunAttributes | None] = ContextVar("agent_run", default=None)


@contextmanager
def run_attributes(run: RunAttributes) -> Iterator[None]:
    """Spans started inside carry the run's conversation ID."""
    token = _run.set(run)
    try:
        yield
    finally:
        _run.reset(token)


def _operation(span: ReadableSpan) -> str:
    """The operation, from the attribute or, before the instrumentation sets it, the span name."""
    operation = (span.attributes or {}).get("gen_ai.operation.name")
    return str(operation) if operation else span.name.split(" ", 1)[0]


def _is_langchain_span(span: ReadableSpan) -> bool:
    scope = span.instrumentation_scope
    return scope is not None and scope.name == LANGCHAIN_SCOPE


class RunAttributesProcessor(SpanProcessor):
    """Adds the conversation and the data source to the instrumentation's spans."""

    def __init__(self, data_source: DataSource) -> None:
        self._data_source = data_source

    def on_start(self, span: Span, parent_context: otel_context.Context | None = None) -> None:
        if not _is_langchain_span(span):
            return
        attributes = span.attributes or {}
        added: dict[str, AttributeValue] = {}
        run = _run.get()
        if run is not None:
            added["gen_ai.conversation.id"] = run.conversation_id
        if _operation(span) == "retrieval":
            added["gen_ai.data_source.id"] = self._data_source.id
            if self._data_source.address is not None:
                added["server.address"] = self._data_source.address
            if self._data_source.port is not None:
                added["server.port"] = self._data_source.port
        span.set_attributes({k: v for k, v in added.items() if k not in attributes})


def _as_token_count(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _derived_attributes(span: ReadableSpan) -> dict[str, AttributeValue]:
    attributes = span.attributes or {}
    derived: dict[str, AttributeValue] = {}
    model = attributes.get("gen_ai.response.model") or attributes.get("gen_ai.request.model")
    if attributes.get("gen_ai.operation.name") == "chat" and model is not None:
        derived[COST_ATTRIBUTE] = calculate_cost(
            str(model),
            _as_token_count(attributes.get("gen_ai.usage.input_tokens")),
            _as_token_count(attributes.get("gen_ai.usage.output_tokens")),
        )
    for key in CONTENT_ATTRIBUTES:
        value = attributes.get(key)
        if isinstance(value, str):
            derived[key] = scrub(value, limit=len(value))
    return derived


def _with_attributes(span: ReadableSpan, derived: dict[str, AttributeValue]) -> ReadableSpan:
    """A finished span's attributes are frozen, so the span is rebuilt with the additions."""
    events = BoundedList.from_seq(None, span.events)
    events.dropped = span.dropped_events
    links = BoundedList.from_seq(None, span.links)
    links.dropped = span.dropped_links
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes={**(span.attributes or {}), **derived},
        events=events,
        links=links,
        kind=span.kind,
        instrumentation_scope=span.instrumentation_scope,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
    )


class GenAISpanExporter(SpanExporter):
    """Adds the cost to model call spans and scrubs PII from captured content."""

    def __init__(self, wrapped: SpanExporter) -> None:
        self._wrapped = wrapped

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        exported = []
        for span in spans:
            derived = _derived_attributes(span) if _is_langchain_span(span) else {}
            exported.append(_with_attributes(span, derived) if derived else span)
        return self._wrapped.export(exported)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)
