"""OpenTelemetry instrumentation setup for Flask application.

Configures traces, metrics, and logs with OTLP exporters.
"""

import logging
import os

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, get_aggregated_resources
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_otel_log_handler: LoggingHandler | None = None
_initialized: bool = False


def setup_telemetry() -> None:
    """Initialize OpenTelemetry with traces, metrics, and logs.

    This function should be called once at application startup,
    BEFORE creating the Flask app.
    """
    global _otel_log_handler, _initialized

    if _initialized:
        return

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    service_name = os.getenv("OTEL_SERVICE_NAME", "flask-postgres-app")
    service_version = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")

    # Create resource - get_aggregated_resources automatically picks up OTEL_RESOURCE_ATTRIBUTES
    resource = get_aggregated_resources(
        detectors=[],
        initial_resource=Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
            }
        ),
    )

    # ==========================================================================
    # 1. Traces
    # ==========================================================================
    trace_exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    # ==========================================================================
    # 2. Metrics
    # ==========================================================================
    metric_exporter = OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # ==========================================================================
    # 3. Logs
    # ==========================================================================
    log_exporter = OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs")
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    _logs.set_logger_provider(logger_provider)

    # Create handler for attaching to Python loggers
    _otel_log_handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)

    # ==========================================================================
    # 4. Auto-instrumentation (non-Flask)
    # ==========================================================================
    # SQLAlchemy instrumentation
    SQLAlchemyInstrumentor().instrument()

    # Redis instrumentation
    RedisInstrumentor().instrument()

    # Celery instrumentation
    CeleryInstrumentor().instrument()

    # Logging instrumentation (adds trace_id, span_id to log records)
    LoggingInstrumentor().instrument(set_logging_format=True)

    _initialized = True


def get_otel_log_handler() -> LoggingHandler | None:
    """Get the OTel logging handler for attaching to loggers.

    Returns:
        The OTel LoggingHandler if initialized, None otherwise.
    """
    return _otel_log_handler


def instrument_flask_app(app) -> None:
    """Instrument a Flask app for tracing.

    This must be called after app creation, especially when using
    Gunicorn which forks workers after the global instrumentation
    is set up.

    Args:
        app: Flask application instance.
    """
    FlaskInstrumentor().instrument_app(app, excluded_urls="/api/health,/health")


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for creating custom spans.

    Args:
        name: Name of the tracer (typically __name__).

    Returns:
        OpenTelemetry Tracer instance.
    """
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Get a meter for creating custom metrics.

    Args:
        name: Name of the meter (typically __name__).

    Returns:
        OpenTelemetry Meter instance.
    """
    return metrics.get_meter(name)
