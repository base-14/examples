"""Service name, resource and OTLP endpoints the providers are built with, read from the
standard `OTEL_*` variables."""

from unittest.mock import patch

import pytest
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider

from kyc_onboarding import telemetry
from kyc_onboarding.telemetry import (
    SERVICE_INSTANCE_ID,
    configure_logging,
    configure_metrics,
    configure_tracing,
    service_name,
    temporal_metrics_url,
)


FALLBACK = "fallback-service"


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "OTEL_SERVICE_NAME",
        "OTEL_RESOURCE_ATTRIBUTES",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ):
        monkeypatch.delenv(var, raising=False)


class TestServiceName:
    def test_otel_service_name_wins_over_the_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")

        assert service_name(FALLBACK) == "from-env"

    def test_the_fallback_applies_when_the_variable_is_unset(self) -> None:
        assert service_name(FALLBACK) == FALLBACK

    def test_a_service_name_in_otel_resource_attributes_wins_over_the_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=from-attributes")

        assert service_name(FALLBACK) == "from-attributes"


def _traced_provider() -> TracerProvider:
    with patch.object(telemetry.trace, "set_tracer_provider") as set_provider:
        configure_tracing(FALLBACK)
    provider: TracerProvider = set_provider.call_args.args[0]._tracer_provider
    return provider


def _metered_provider() -> MeterProvider:
    with patch.object(telemetry.otel_metrics, "set_meter_provider") as set_provider:
        configure_metrics(FALLBACK)
    provider: MeterProvider = set_provider.call_args.args[0]._meter_provider
    return provider


def _logged_provider() -> LoggerProvider:
    with patch.object(telemetry, "install_logging") as install:
        configure_logging(FALLBACK)
    provider: LoggerProvider = install.call_args.args[0]
    return provider


class TestProviders:
    def test_every_provider_carries_the_service_name_and_instance_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")
        tracer_provider = _traced_provider()
        meter_provider = _metered_provider()
        logger_provider = _logged_provider()
        try:
            for resource in (
                tracer_provider.resource,
                meter_provider._sdk_config.resource,
                logger_provider.resource,
            ):
                assert resource.attributes["service.name"] == "from-env"
                assert resource.attributes["service.instance.id"] == SERVICE_INSTANCE_ID
        finally:
            tracer_provider.shutdown()
            meter_provider.shutdown()
            logger_provider.shutdown()

    def test_the_exporters_read_otel_exporter_otlp_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.test:4318")
        tracer_provider = _traced_provider()
        meter_provider = _metered_provider()
        logger_provider = _logged_provider()
        try:
            (span_processor,) = tracer_provider._active_span_processor._span_processors
            span_exporter = span_processor._batch_processor._exporter
            (reader,) = meter_provider._metric_readers
            (log_processor,) = logger_provider._multi_log_record_processor._log_record_processors
            log_exporter = log_processor._batch_processor._exporter

            assert span_exporter._wrapped._endpoint == "http://collector.test:4318/v1/traces"
            assert reader._exporter._endpoint == "http://collector.test:4318/v1/metrics"
            assert log_exporter._endpoint == "http://collector.test:4318/v1/logs"
        finally:
            tracer_provider.shutdown()
            meter_provider.shutdown()
            logger_provider.shutdown()


class TestTemporalMetricsUrl:
    def test_appends_the_metrics_path_to_the_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.test:4318")

        assert temporal_metrics_url() == "http://collector.test:4318/v1/metrics"

    def test_a_trailing_slash_is_not_doubled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.test:4318/")

        assert temporal_metrics_url() == "http://collector.test:4318/v1/metrics"

    def test_defaults_to_the_sdk_default_endpoint(self) -> None:
        assert temporal_metrics_url() == "http://localhost:4318/v1/metrics"
