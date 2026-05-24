"""The extract side of the bridge: a producer-shaped user-property list must
restore the original trace, and a context-less message must be detected so the
consumer can fall back to a root span."""

from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import set_span_in_context

from propagation import has_trace_context, user_properties_to_context

trace.set_tracer_provider(TracerProvider())
_tracer = trace.get_tracer("test")


def _producer_user_properties() -> list[tuple[str, str]]:
    span = _tracer.start_span("publish sensors/x/reading")
    carrier: dict[str, str] = {}
    inject(carrier, context=set_span_in_context(span))
    span.end()
    return list(carrier.items()), span.get_span_context().trace_id


def test_extract_restores_producer_trace_id():
    user_props, producer_trace_id = _producer_user_properties()

    ctx = user_properties_to_context(user_props)
    restored = trace.get_current_span(ctx).get_span_context()

    assert restored.trace_id == producer_trace_id
    assert restored.is_remote


def test_has_trace_context_detects_presence_and_absence():
    user_props, _ = _producer_user_properties()

    assert has_trace_context(user_props) is True
    assert has_trace_context(None) is False
    assert has_trace_context([("foo", "bar")]) is False
