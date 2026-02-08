import os
from unittest.mock import MagicMock, patch

from content_quality.telemetry import instrument_fastapi, setup_telemetry


# Common patches for all enabled-SDK tests
_ENABLED_PATCHES = (
    "content_quality.telemetry.TracerProvider",
    "content_quality.telemetry.MeterProvider",
    "content_quality.telemetry.LoggerProvider",
    "content_quality.telemetry.BatchSpanProcessor",
    "content_quality.telemetry.BatchLogRecordProcessor",
    "content_quality.telemetry.PeriodicExportingMetricReader",
    "content_quality.telemetry.OTLPSpanExporter",
    "content_quality.telemetry.OTLPMetricExporter",
    "content_quality.telemetry.OTLPLogExporter",
    "content_quality.telemetry.LoggingHandler",
    "content_quality.telemetry.LoggingInstrumentor",
    "content_quality.telemetry.trace",
    "content_quality.telemetry.metrics",
    "content_quality.telemetry._logs",
    "content_quality.telemetry.atexit",
)


def _enter_patches() -> dict[str, MagicMock]:
    """Start all common patches and return a name->mock mapping."""
    mocks: dict[str, MagicMock] = {}
    for target in _ENABLED_PATCHES:
        p = patch(target)
        short = target.rsplit(".", 1)[-1]
        mocks[short] = p.start()
    mocks["trace"].get_tracer.return_value = MagicMock()
    mocks["metrics"].get_meter.return_value = MagicMock()
    return mocks


def _stop_patches() -> None:
    patch.stopall()


def _clear_otel_disabled() -> None:
    os.environ.pop("OTEL_SDK_DISABLED", None)


def test_disabled_returns_noop_providers() -> None:
    with patch.dict(os.environ, {"OTEL_SDK_DISABLED": "true"}):
        tracer, meter = setup_telemetry("test-service", "http://localhost:4318")

    assert tracer is not None
    assert meter is not None
    span = tracer.start_span("test")
    span.end()


def test_enabled_creates_real_providers() -> None:
    with patch.dict(os.environ, {}, clear=False):
        _clear_otel_disabled()
        mocks = _enter_patches()
        try:
            setup_telemetry("test-service", "http://localhost:4318")

            mocks["TracerProvider"].assert_called_once()
            mocks["MeterProvider"].assert_called_once()
            mocks["LoggerProvider"].assert_called_once()
            mocks["trace"].set_tracer_provider.assert_called_once()
            mocks["metrics"].set_meter_provider.assert_called_once()
            mocks["_logs"].set_logger_provider.assert_called_once()
        finally:
            _stop_patches()


def test_enabled_instruments_logging() -> None:
    with patch.dict(os.environ, {}, clear=False):
        _clear_otel_disabled()
        mocks = _enter_patches()
        try:
            setup_telemetry("test-service", "http://localhost:4318")

            mocks["LoggingInstrumentor"].return_value.instrument.assert_called_once_with(
                set_logging_format=True
            )
        finally:
            _stop_patches()


def test_enabled_registers_atexit_shutdown() -> None:
    with patch.dict(os.environ, {}, clear=False):
        _clear_otel_disabled()
        mocks = _enter_patches()
        try:
            setup_telemetry("test-service", "http://localhost:4318")

            calls = mocks["atexit"].register.call_args_list
            assert len(calls) == 3
            assert calls[0].args[0] == mocks["TracerProvider"].return_value.shutdown
            assert calls[1].args[0] == mocks["MeterProvider"].return_value.shutdown
            assert calls[2].args[0] == mocks["LoggerProvider"].return_value.shutdown
        finally:
            _stop_patches()


def test_instrument_fastapi_calls_instrumentor() -> None:
    with patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor") as mock_fai:
        mock_app = MagicMock()
        instrument_fastapi(mock_app)
        mock_fai.instrument_app.assert_called_once_with(
            mock_app, excluded_urls="health", exclude_spans=["receive", "send"]
        )


def test_resource_includes_service_metadata() -> None:
    with patch.dict(os.environ, {"SCOUT_ENVIRONMENT": "staging"}, clear=False):
        _clear_otel_disabled()
        _enter_patches()
        try:
            with patch("content_quality.telemetry.Resource") as mock_resource:
                setup_telemetry("my-service", "http://localhost:4318")

                mock_resource.create.assert_called_once_with(
                    {
                        "service.name": "my-service",
                        "service.version": "1.0.0",
                        "deployment.environment": "staging",
                    }
                )
        finally:
            _stop_patches()
