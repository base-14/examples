from __future__ import annotations

import logging
import os

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.metrics import Meter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

logger = logging.getLogger(__name__)

_telemetry_initialized = False
_otel_log_handler: LoggingHandler | None = None


def setup_telemetry() -> None:
    global _telemetry_initialized, _otel_log_handler
    if _telemetry_initialized:
        return

    if os.getenv("OTEL_SDK_DISABLED", "").lower() in ("true", "1", "yes"):
        logger.info("OpenTelemetry SDK disabled")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "django-postgres-celery-app")
    service_version = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    resource_attrs: dict[str, str] = {
        "service.name": service_name,
        "service.version": service_version,
    }

    extra_attrs = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    if extra_attrs:
        for attr in extra_attrs.split(","):
            if "=" in attr:
                key, value = attr.split("=", 1)
                resource_attrs[key.strip()] = value.strip()

    resource = Resource.create(resource_attrs)

    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics"),
        export_interval_millis=10000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    log_exporter = OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs")
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    _logs.set_logger_provider(logger_provider)

    _otel_log_handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)

    DjangoInstrumentor().instrument(excluded_urls="health")
    PsycopgInstrumentor().instrument()
    RedisInstrumentor().instrument()
    CeleryInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)

    _telemetry_initialized = True
    logger.info(f"OpenTelemetry initialized for {service_name} v{service_version}")


def get_tracer(name: str = __name__) -> Tracer:
    return trace.get_tracer(name)


def get_meter(name: str = __name__) -> Meter:
    return metrics.get_meter(name)


def get_otel_log_handler() -> LoggingHandler | None:
    return _otel_log_handler
