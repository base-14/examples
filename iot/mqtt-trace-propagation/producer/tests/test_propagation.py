"""The inject side of the bridge: a span's context must survive serialization
into MQTT user properties and come back as the same trace."""

from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import set_span_in_context

from propagation import context_to_user_properties

trace.set_tracer_provider(TracerProvider())
_tracer = trace.get_tracer("test")


def test_user_properties_carry_traceparent():
    span = _tracer.start_span("publish sensors/x/reading")
    ctx = set_span_in_context(span)

    props = dict(context_to_user_properties(ctx))

    assert "traceparent" in props
    trace_id = trace.format_trace_id(span.get_span_context().trace_id)
    assert trace_id in props["traceparent"]
    span.end()


def test_round_trip_preserves_trace_id():
    span = _tracer.start_span("publish sensors/x/reading")
    ctx = set_span_in_context(span)

    carrier = dict(context_to_user_properties(ctx))
    extracted = extract(carrier)
    restored = trace.get_current_span(extracted).get_span_context()

    assert restored.trace_id == span.get_span_context().trace_id
    assert restored.is_remote
    span.end()
