"""Enrichment of the model call spans the OpenTelemetry GenAI instrumentations create.

The OpenAI, Anthropic and Google Gen AI instrumentations open one `chat {model}` span
per SDK call. They do not know which agent made the call or which campaign it served,
and the OpenAI instrumentation names the provider `openai` for any OpenAI-compatible
endpoint, Ollama's included. `LLMCallAttributesProcessor` adds the agent, the campaign
and the real provider when the span starts. `GenAISpanExporter` adds the cost and
scrubs PII from captured content when the span is exported, because both need values
that exist only once the call has finished.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from opentelemetry import context as otel_context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.util import BoundedList

from sales_intelligence.pii import scrub_pii
from sales_intelligence.pricing import calculate_cost


GENAI_INSTRUMENTATION_SCOPES = (
    "opentelemetry.instrumentation.genai.",
    "opentelemetry.instrumentation.google_genai",
)
MODEL_CALL_OPERATIONS = frozenset({"chat", "generate_content", "text_completion"})
CONTENT_ATTRIBUTES = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
)
COST_ATTRIBUTE = "base14.gen_ai.cost_usd"

type AttributeValue = str | bool | int | float


@dataclass(frozen=True)
class LLMCallAttributes:
    """What the application knows about one model call that the instrumentation does not."""

    provider: str
    agent_name: str | None = None
    campaign_id: str | None = None


_llm_call: ContextVar[LLMCallAttributes | None] = ContextVar("llm_call", default=None)


@contextmanager
def llm_call_attributes(call: LLMCallAttributes) -> Iterator[None]:
    """Model call spans started inside carry the call's agent, campaign and provider."""
    token = _llm_call.set(call)
    try:
        yield
    finally:
        _llm_call.reset(token)


def _is_genai_instrumentation_span(span: ReadableSpan) -> bool:
    scope = span.instrumentation_scope.name if span.instrumentation_scope else ""
    return scope.startswith(GENAI_INSTRUMENTATION_SCOPES)


class LLMCallAttributesProcessor(SpanProcessor):
    """Adds the agent, the campaign and the provider to model call spans as they start."""

    def on_start(self, span: Span, parent_context: otel_context.Context | None = None) -> None:
        call = _llm_call.get()
        if call is None or not _is_genai_instrumentation_span(span):
            return
        attributes: dict[str, AttributeValue] = {"gen_ai.provider.name": call.provider}
        if call.agent_name:
            attributes["gen_ai.agent.name"] = call.agent_name
        if call.campaign_id:
            attributes["base14.campaign_id"] = call.campaign_id
        span.set_attributes(attributes)


def _as_token_count(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _derived_attributes(span: ReadableSpan) -> dict[str, AttributeValue]:
    attributes = span.attributes or {}
    if attributes.get("gen_ai.operation.name") not in MODEL_CALL_OPERATIONS:
        return {}
    derived: dict[str, AttributeValue] = {}
    model = attributes.get("gen_ai.response.model") or attributes.get("gen_ai.request.model")
    if model is not None:
        derived[COST_ATTRIBUTE] = calculate_cost(
            str(model),
            _as_token_count(attributes.get("gen_ai.usage.input_tokens")),
            _as_token_count(attributes.get("gen_ai.usage.output_tokens")),
        )
    for key in CONTENT_ATTRIBUTES:
        value = attributes.get(key)
        if isinstance(value, str):
            derived[key] = scrub_pii(value)
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
    """Adds the cost to model call spans and scrubs PII from their captured content."""

    def __init__(self, wrapped: SpanExporter) -> None:
        self._wrapped = wrapped

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        exported = []
        for span in spans:
            derived = _derived_attributes(span) if _is_genai_instrumentation_span(span) else {}
            exported.append(_with_attributes(span, derived) if derived else span)
        return self._wrapped.export(exported)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)
