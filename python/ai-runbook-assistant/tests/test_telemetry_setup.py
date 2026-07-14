from unittest.mock import patch

from runbook_assistant.telemetry.setup import build_resource, setup_telemetry


def test_resource_has_dual_key_environment(monkeypatch):
    monkeypatch.setenv("SCOUT_ENVIRONMENT", "staging")
    res = build_resource()
    attrs = res.attributes
    assert attrs["service.name"] == "ai-runbook-assistant"
    assert attrs["deployment.environment.name"] == "staging"
    assert attrs["environment"] == "staging"


_PATCHES = (
    "TracerProvider",
    "MeterProvider",
    "LoggerProvider",
    "BatchSpanProcessor",
    "BatchLogRecordProcessor",
    "PeriodicExportingMetricReader",
    "OTLPSpanExporter",
    "OTLPMetricExporter",
    "OTLPLogExporter",
    "LoggingHandler",
    "LoggingInstrumentor",
    "HTTPXClientInstrumentor",
    "logging",
    "trace",
    "metrics",
    "_logs",
)


def _enter():
    mocks = {}
    for name in _PATCHES:
        mocks[name] = patch(f"runbook_assistant.telemetry.setup.{name}").start()
    return mocks


def test_logs_exported_via_otlp_for_trace_correlation():
    mocks = _enter()
    try:
        setup_telemetry()

        mocks["LoggerProvider"].assert_called_once()
        mocks["OTLPLogExporter"].assert_called_once_with(endpoint="http://localhost:4318/v1/logs")
        mocks["_logs"].set_logger_provider.assert_called_once()
        mocks["LoggingHandler"].assert_called_once()
        assert (
            mocks["LoggingHandler"].call_args.kwargs["logger_provider"]
            is mocks["LoggerProvider"].return_value
        )
        mocks["logging"].getLogger.return_value.addHandler.assert_called_once_with(
            mocks["LoggingHandler"].return_value
        )
    finally:
        patch.stopall()
