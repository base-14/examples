from collections.abc import Callable

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Link, Span, Status, StatusCode

from kyc_onboarding.attributes import PROMPT_VERSION_ATTRIBUTE
from kyc_onboarding.telemetry import (
    COST_ATTRIBUTE,
    COST_SIMULATED_ATTRIBUTE,
    ERROR_TYPE_ATTRIBUTE,
    CostAndErrorAttributingSpanExporter,
    calculate_cost,
)


def test_calculate_cost_known_model_is_not_simulated() -> None:
    cost, simulated = calculate_cost("gpt-4.1-nano", 1000, 500)

    assert cost == 0.0003
    assert simulated is False


def test_calculate_cost_unknown_local_model_is_simulated() -> None:
    cost, simulated = calculate_cost("qwen3.5:9B", 1000, 500)

    assert cost == 0.0
    assert simulated is True


def _succeed(span: Span) -> None:
    return None


def _export_one_span(
    exporter: InMemorySpanExporter,
    name: str,
    attributes: dict[str, object],
    during: Callable[[Span], None] = _succeed,
) -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(CostAndErrorAttributingSpanExporter(exporter)))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span(
        name, attributes=attributes, record_exception=False, set_status_on_exception=False
    ) as span:
        during(span)
    provider.shutdown()


def _exported(
    name: str, attributes: dict[str, object], during: Callable[[Span], None]
) -> ReadableSpan:
    exporter = InMemorySpanExporter()
    _export_one_span(exporter, name, attributes, during)
    (span,) = exporter.get_finished_spans()
    return span


def _fails_with(*errors: Exception) -> Callable[[Span], None]:
    def fail(span: Span) -> None:
        for error in errors:
            span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, "failed"))

    return fail


def test_exporter_stamps_cost_on_chat_span_for_known_model() -> None:
    exporter = InMemorySpanExporter()
    _export_one_span(
        exporter,
        "chat gpt-4.1-nano",
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "gpt-4.1-nano",
            "gen_ai.usage.input_tokens": 1000,
            "gen_ai.usage.output_tokens": 500,
        },
    )

    (span,) = exporter.get_finished_spans()

    assert span.attributes is not None
    assert span.attributes[COST_ATTRIBUTE] == 0.0003
    assert span.attributes[COST_SIMULATED_ATTRIBUTE] is False


def test_exporter_stamps_simulated_cost_on_chat_span_for_local_model() -> None:
    exporter = InMemorySpanExporter()
    _export_one_span(
        exporter,
        "chat qwen3.5:9B",
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "qwen3.5:9B",
            "gen_ai.usage.input_tokens": 1000,
            "gen_ai.usage.output_tokens": 500,
        },
    )

    (span,) = exporter.get_finished_spans()

    assert span.attributes is not None
    assert span.attributes[COST_ATTRIBUTE] == 0.0
    assert span.attributes[COST_SIMULATED_ATTRIBUTE] is True


def test_exporter_leaves_non_chat_spans_untouched() -> None:
    exporter = InMemorySpanExporter()
    _export_one_span(
        exporter,
        "invoke_agent assessor",
        {"gen_ai.operation.name": "invoke_agent"},
    )

    (span,) = exporter.get_finished_spans()

    assert span.attributes is not None
    assert COST_ATTRIBUTE not in span.attributes
    assert COST_SIMULATED_ATTRIBUTE not in span.attributes


def test_exporter_copies_the_prompt_version_out_of_the_run_metadata() -> None:
    span = _exported(
        "invoke_agent kyc-assessment",
        {"gen_ai.operation.name": "invoke_agent", "metadata": '{"prompt_version": "v2"}'},
        _succeed,
    )

    assert span.attributes is not None
    assert span.attributes[PROMPT_VERSION_ATTRIBUTE] == "v2"


def test_exporter_leaves_a_run_without_a_prompt_version_untouched() -> None:
    for metadata in ('{"other": 1}', "not json", '["v2"]'):
        span = _exported(
            "invoke_agent kyc-assessment",
            {"gen_ai.operation.name": "invoke_agent", "metadata": metadata},
            _succeed,
        )

        assert span.attributes is not None
        assert PROMPT_VERSION_ATTRIBUTE not in span.attributes, metadata


def test_exporter_copies_the_prompt_version_only_from_run_spans() -> None:
    span = _exported(
        "execute_tool screen_sanctions",
        {"gen_ai.operation.name": "execute_tool", "metadata": '{"prompt_version": "v2"}'},
        _succeed,
    )

    assert span.attributes is not None
    assert PROMPT_VERSION_ATTRIBUTE not in span.attributes


def test_exporter_sets_error_type_from_the_first_exception_on_failed_genai_spans() -> None:
    for operation in ("chat", "invoke_agent"):
        span = _exported(
            f"{operation} probe",
            {"gen_ai.operation.name": operation},
            _fails_with(ConnectionError("down"), ValueError("later")),
        )

        assert span.attributes is not None
        assert span.attributes[ERROR_TYPE_ATTRIBUTE] == "ConnectionError", operation


def test_exporter_sets_no_error_type_without_error_status_or_exception() -> None:
    def recorded_but_ok(span: Span) -> None:
        span.record_exception(ConnectionError("retried"))

    def failed_without_exception(span: Span) -> None:
        span.set_status(Status(StatusCode.ERROR, "failed"))

    for during in (recorded_but_ok, failed_without_exception):
        span = _exported("chat probe", {"gen_ai.operation.name": "chat"}, during)

        assert span.attributes is not None
        assert ERROR_TYPE_ATTRIBUTE not in span.attributes


def test_exporter_sets_no_error_type_on_other_failed_spans() -> None:
    span = _exported(
        "execute_tool screen_sanctions",
        {"gen_ai.operation.name": "execute_tool"},
        _fails_with(ConnectionError("down")),
    )

    assert span.attributes is not None
    assert ERROR_TYPE_ATTRIBUTE not in span.attributes


def test_exporter_keeps_an_error_type_the_span_already_has() -> None:
    span = _exported(
        "chat probe",
        {"gen_ai.operation.name": "chat", "error.type": "timeout"},
        _fails_with(ConnectionError("down")),
    )

    assert span.attributes is not None
    assert span.attributes[ERROR_TYPE_ATTRIBUTE] == "timeout"


def test_exporter_keeps_the_drop_counts_of_a_rebuilt_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create({"service.name": "test"}),
        span_limits=SpanLimits(max_span_attributes=5, max_events=1, max_links=1),
    )
    provider.add_span_processor(SimpleSpanProcessor(CostAndErrorAttributingSpanExporter(exporter)))
    linked = provider.get_tracer("test").start_span("linked").get_span_context()
    with provider.get_tracer("test").start_as_current_span(
        "chat gpt-4.1-nano",
        attributes={
            "evicted.first": 1,
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "gpt-4.1-nano",
            "gen_ai.usage.input_tokens": 1000,
            "gen_ai.usage.output_tokens": 500,
            "kept": 2,
        },
        links=[Link(linked), Link(linked)],
    ) as span:
        span.add_event("first")
        span.add_event("second")
    provider.shutdown()

    (exported,) = exporter.get_finished_spans()

    assert exported.attributes is not None
    assert exported.attributes[COST_ATTRIBUTE] == 0.0003
    assert (exported.dropped_attributes, exported.dropped_events, exported.dropped_links) == (
        1,
        1,
        1,
    )
