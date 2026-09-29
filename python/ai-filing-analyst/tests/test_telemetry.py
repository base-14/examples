import logging
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from filing_analyst import telemetry
from filing_analyst.telemetry import (
    CONSOLE_HANDLER_NAME,
    COST_ATTRIBUTE,
    COST_SIMULATED_ATTRIBUTE,
    REDACT_ALL_TOKEN,
    CostAndErrorAttributingSpanExporter,
    QuestionIdFilter,
    apply_content_capture_setting,
    build_logger_provider,
    build_resource,
    build_tracer_provider,
    correlate_console_logs,
    install_logging,
    question_logging,
)


OTEL_VARS = (
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_SDK_DISABLED",
    "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT",
    "OTEL_SEMCONV_STABILITY_OPT_IN",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    "OTEL_PYTHON_LOG_CORRELATION",
)


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in OTEL_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def exported() -> Iterator[tuple[TracerProvider, InMemorySpanExporter]]:
    memory = InMemorySpanExporter()
    provider = build_tracer_provider(
        CostAndErrorAttributingSpanExporter(memory), build_resource(), SimpleSpanProcessor
    )
    yield provider, memory
    provider.shutdown()


def _only_span(memory: InMemorySpanExporter) -> ReadableSpan:
    (span,) = memory.get_finished_spans()
    return span


def _chat_span(provider: TracerProvider, model: str) -> None:
    with provider.get_tracer("test").start_as_current_span("chat") as span:
        span.set_attributes(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": model,
                "gen_ai.usage.input_tokens": 1_000_000,
                "gen_ai.usage.output_tokens": 1_000_000,
            }
        )


class TestCost:
    def test_a_local_model_costs_nothing_and_is_marked_simulated(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        _chat_span(provider, "qwen3.5:9B")
        attributes = _only_span(memory).attributes or {}
        assert attributes[COST_ATTRIBUTE] == 0.0
        assert attributes[COST_SIMULATED_ATTRIBUTE] is True

    def test_a_priced_model_gets_its_cost_from_the_pricing_file(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        _chat_span(provider, "gpt-5.6-sol")
        attributes = _only_span(memory).attributes or {}
        assert attributes[COST_ATTRIBUTE] == 35.0
        assert attributes[COST_SIMULATED_ATTRIBUTE] is False

    def test_a_span_that_is_not_chat_gets_no_cost(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span("execute_tool query_facts"):
            pass
        assert COST_ATTRIBUTE not in (_only_span(memory).attributes or {})


class TestErrorType:
    def test_a_failed_span_gets_the_recorded_exception_type(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span(
            "invoke_agent analyst", record_exception=False, set_status_on_exception=False
        ) as span:
            span.set_status(Status(StatusCode.ERROR, "boom"))
            span.record_exception(TimeoutError("boom"))
        assert (_only_span(memory).attributes or {})["error.type"] == "TimeoutError"

    def test_the_strands_event_loop_wrapper_gives_way_to_its_cause(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        exceptions = pytest.importorskip("strands.types.exceptions")
        EventLoopException = exceptions.EventLoopException
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span(
            "invoke_agent analyst", record_exception=False, set_status_on_exception=False
        ) as span:
            try:
                try:
                    raise LookupError("budget")
                except LookupError as cause:
                    raise EventLoopException(cause, {}) from cause
            except EventLoopException as wrapper:
                span.set_status(Status(StatusCode.ERROR, "budget"))
                span.record_exception(wrapper)
        assert (_only_span(memory).attributes or {})["error.type"] == "LookupError"

    def test_an_existing_error_type_is_kept(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span("chat") as span:
            span.set_attribute("error.type", "rate_limited")
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(RuntimeError("boom"))
        assert (_only_span(memory).attributes or {})["error.type"] == "rate_limited"

    @pytest.mark.parametrize(
        ("status_attribute", "code"),
        [("http.status_code", 403), ("http.response.status_code", 504)],
    )
    def test_a_failed_http_span_without_an_exception_gets_its_status_code(
        self,
        exported: tuple[TracerProvider, InMemorySpanExporter],
        status_attribute: str,
        code: int,
    ) -> None:
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span("GET") as span:
            span.set_attribute(status_attribute, code)
            span.set_status(Status(StatusCode.ERROR))
        assert (_only_span(memory).attributes or {})["error.type"] == str(code)

    def test_any_other_failed_span_gets_the_semconv_fallback(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span("execute_tool FilingAnswer") as span:
            span.set_status(Status(StatusCode.ERROR))
        assert (_only_span(memory).attributes or {})["error.type"] == "_OTHER"

    def test_a_recorded_exception_replaces_an_instrumentation_fallback(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span("invoke_agent analyst") as span:
            span.record_exception(ConnectionError("refused"))
            span.set_attribute("error.type", "_OTHER")
            span.set_status(Status(StatusCode.ERROR))
        assert (_only_span(memory).attributes or {})["error.type"] == "ConnectionError"

    def test_a_successful_span_gets_no_error_type(
        self, exported: tuple[TracerProvider, InMemorySpanExporter]
    ) -> None:
        provider, memory = exported
        with provider.get_tracer("test").start_as_current_span("chat"):
            pass
        assert "error.type" not in (_only_span(memory).attributes or {})


class TestContentCapture:
    def test_capture_false_appends_the_redaction_token(self) -> None:
        environ = {
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
            "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
        }
        apply_content_capture_setting(environ)
        assert environ["OTEL_SEMCONV_STABILITY_OPT_IN"] == (
            f"gen_ai_latest_experimental,{REDACT_ALL_TOKEN}"
        )

    def test_capture_false_with_no_opt_in_sets_only_the_token(self) -> None:
        environ = {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "False"}
        apply_content_capture_setting(environ)
        assert environ["OTEL_SEMCONV_STABILITY_OPT_IN"] == REDACT_ALL_TOKEN

    @pytest.mark.parametrize("capture", ["true", None])
    def test_capture_true_or_unset_leaves_the_opt_in_alone(self, capture: str | None) -> None:
        environ = {"OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental"}
        if capture is not None:
            environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = capture
        apply_content_capture_setting(environ)
        assert environ["OTEL_SEMCONV_STABILITY_OPT_IN"] == "gen_ai_latest_experimental"

    def test_a_reader_chosen_unredacted_list_is_kept(self) -> None:
        opt_in = "gen_ai_latest_experimental,gen_ai_unredacted_attributes=gen_ai.input.messages"
        environ = {
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
            "OTEL_SEMCONV_STABILITY_OPT_IN": opt_in,
        }
        apply_content_capture_setting(environ)
        assert environ["OTEL_SEMCONV_STABILITY_OPT_IN"] == opt_in

    def test_strands_redacts_message_content_after_the_mapping(
        self,
        monkeypatch: pytest.MonkeyPatch,
        exported: tuple[TracerProvider, InMemorySpanExporter],
    ) -> None:
        tracing = pytest.importorskip("strands.telemetry.tracer")
        provider, memory = exported
        monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
        apply_content_capture_setting()
        with patch("strands.telemetry.tracer.trace_api.get_tracer_provider", return_value=provider):
            tracer = tracing.Tracer()
        span = tracer.start_model_invoke_span(
            messages=[{"role": "user", "content": [{"text": "workiva revenue orion-9"}]}],
            model_id="qwen3.5:9B",
        )
        span.end()
        assert "orion-9" not in str(dict(_only_span(memory).attributes or {}))


class TestResource:
    def test_service_name_and_resource_attributes_reach_an_exported_span(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_SERVICE_NAME", "filing-from-env")
        monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.version=9.9.9,deployment.env=test")
        memory = InMemorySpanExporter()
        provider = build_tracer_provider(memory, build_resource(), SimpleSpanProcessor)
        with provider.get_tracer("test").start_as_current_span("probe"):
            pass
        resource = _only_span(memory).resource.attributes
        assert resource["service.name"] == "filing-from-env"
        assert resource["service.version"] == "9.9.9"
        assert resource["deployment.env"] == "test"
        assert resource["service.instance.id"]

    def test_the_fallback_service_name_applies_when_none_is_set(self) -> None:
        assert build_resource().attributes["service.name"] == "ai-filing-analyst"

    def test_the_attribute_length_limit_comes_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT", "8")
        memory = InMemorySpanExporter()
        provider = build_tracer_provider(memory, build_resource(), SimpleSpanProcessor)
        with provider.get_tracer("test").start_as_current_span("probe") as span:
            span.set_attribute("gen_ai.tool.call.result", "0123456789abcdef")
        assert (_only_span(memory).attributes or {})["gen_ai.tool.call.result"] == "01234567"


class TestSdkDisabled:
    def test_no_spans_are_recorded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        memory = InMemorySpanExporter()
        provider = build_tracer_provider(memory, build_resource(), SimpleSpanProcessor)
        with provider.get_tracer("test").start_as_current_span("probe"):
            pass
        assert memory.get_finished_spans() == ()

    def test_the_app_still_serves_health(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        monkeypatch.setenv("SEC_USER_AGENT", "Example Co ops@example.com")
        monkeypatch.setattr("filing_analyst.health.count_facts", lambda _dsn: 3)
        from filing_analyst.main import create_app

        with (
            patch.object(telemetry.trace, "set_tracer_provider") as set_tracer,
            patch.object(telemetry.metrics, "set_meter_provider"),
            patch.object(telemetry, "set_logger_provider"),
            patch.object(telemetry, "instrument_libraries"),
            TestClient(create_app()) as client,
        ):
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["facts"] == 3
        set_tracer.assert_called_once()


def test_records_emitted_straight_to_the_provider_carry_the_question_id() -> None:
    exporter = InMemoryLogRecordExporter()
    provider = build_logger_provider(exporter, build_resource())
    logger = provider.get_logger("framework")
    with question_logging("q-log-1"):
        logger.emit(body="inference event")
    logger.emit(body="outside a question")
    provider.force_flush()
    inside, outside = (log.log_record for log in exporter.get_finished_logs())
    assert (inside.attributes or {})["base14.filing.question_id"] == "q-log-1"
    assert "base14.filing.question_id" not in (outside.attributes or {})


def test_attribute_truncation_warnings_are_not_exported() -> None:
    root = logging.getLogger()
    handlers = list(root.handlers)
    with patch("filing_analyst.telemetry.set_logger_provider"):
        install_logging(LoggerProvider())
    try:
        assert not logging.getLogger("opentelemetry.attributes").isEnabledFor(logging.WARNING)
    finally:
        for handler in set(root.handlers) - set(handlers):
            root.removeHandler(handler)


@pytest.fixture
def console_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers = list(root.handlers)
    LoggingInstrumentor().uninstrument()
    yield
    LoggingInstrumentor().uninstrument()
    for handler in set(root.handlers) - set(handlers):
        root.removeHandler(handler)


def _record_under_span(provider: TracerProvider) -> tuple[logging.LogRecord, str]:
    with provider.get_tracer("test").start_as_current_span("work") as span:
        record = logging.getLogger("filing_analyst").makeRecord(
            "filing_analyst", logging.INFO, __file__, 1, "x", None, None
        )
        return record, format(span.get_span_context().trace_id, "032x")


@pytest.mark.usefixtures("console_logging")
def test_log_correlation_puts_the_trace_id_on_console_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_PYTHON_LOG_CORRELATION", "true")
    correlate_console_logs()
    record, trace_id = _record_under_span(TracerProvider())
    assert getattr(record, "otelTraceID", None) == trace_id
    (console,) = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "name", None) == CONSOLE_HANDLER_NAME
    ]
    assert f"trace_id={trace_id}" in console.format(record)
    exported = QuestionIdFilter().filter(record)
    assert isinstance(exported, logging.LogRecord)
    assert not hasattr(exported, "otelTraceID")
    assert getattr(record, "otelTraceID", None) == trace_id


@pytest.mark.usefixtures("console_logging")
def test_log_correlation_off_leaves_console_records_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_PYTHON_LOG_CORRELATION", "false")
    correlate_console_logs()
    record, _ = _record_under_span(TracerProvider())
    assert not hasattr(record, "otelTraceID")
    assert all(
        getattr(handler, "name", None) != CONSOLE_HANDLER_NAME
        for handler in logging.getLogger().handlers
    )
