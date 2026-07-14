"""OpenTelemetry bootstrap: providers, exporters, base auto-instrumentation.

Import and call setup_telemetry() BEFORE creating the FastAPI app. The
instrumentation MODE (auto vs callback) is dispatched here based on settings.
"""

import logging
from typing import Any

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from runbook_assistant.config import get_settings


logger = logging.getLogger(__name__)
_APP_VERSION = "1.0.0"


def build_resource() -> Resource:
    """Resource with the dual-key environment convention."""
    s = get_settings()
    return Resource.create(
        {
            "service.name": s.otel_service_name,
            "service.version": _APP_VERSION,
            # Dual-key: Scout UI filters on lowercase `environment`.
            "deployment.environment.name": s.scout_environment,
            "environment": s.scout_environment,
        }
    )


def setup_telemetry(engine: Any = None) -> tuple[trace.Tracer, metrics.Meter]:
    s = get_settings()
    if not s.otel_enabled:
        logger.info("OpenTelemetry disabled")
        return (
            trace.get_tracer(s.otel_service_name),
            metrics.get_meter(s.otel_service_name),
        )

    resource = build_resource()

    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{s.otel_exporter_otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(trace_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{s.otel_exporter_otlp_endpoint}/v1/metrics"),
        export_interval_millis=10000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    # OTLP logs carry the active trace_id/span_id for trace<>log correlation.
    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=f"{s.otel_exporter_otlp_endpoint}/v1/logs")
        )
    )
    _logs.set_logger_provider(log_provider)
    level = logging.getLevelNamesMapping().get(s.log_level, logging.INFO)
    logging.getLogger().setLevel(level)
    logging.getLogger().addHandler(LoggingHandler(level=level, logger_provider=log_provider))

    HTTPXClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    if s.instrumentation_mode == "auto":
        from runbook_assistant.telemetry.auto import enable_auto_instrumentation

        enable_auto_instrumentation()
        logger.info("LangChain instrumentation: auto (OpenLLMetry)")
    else:
        logger.info("LangChain instrumentation: %s", s.instrumentation_mode)

    return (
        trace.get_tracer(s.otel_service_name),
        metrics.get_meter(s.otel_service_name),
    )


def instrument_fastapi(app: Any) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")
