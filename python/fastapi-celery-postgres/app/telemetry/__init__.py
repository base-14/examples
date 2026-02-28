import logging
import os

from celery.signals import worker_process_init
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes

from ..config import (
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_SERVICE_NAME,
)

logger = logging.getLogger(__name__)


@worker_process_init.connect(weak=False)
def init_celery_tracing(*args, **kwargs):
    """Initialize tracing and metrics for Celery worker processes."""
    logger.info("Initializing OpenTelemetry for Celery worker")
    init_telemetry()
    CeleryInstrumentor().instrument()


def init_telemetry():
    """Initialize OpenTelemetry tracing and metrics with OTLP exporters."""
    service_name = os.getenv("OTEL_SERVICE_NAME", OTEL_SERVICE_NAME)

    resource = Resource(
        attributes={
            ResourceAttributes.SERVICE_NAME: service_name,
            ResourceAttributes.SERVICE_VERSION: "1.0.0",
        }
    )

    # Setup trace provider
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()

    # OTLP trace exporter for Base14 Scout
    otel_trace_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_TRACES_ENDPOINT)
    span_processor = BatchSpanProcessor(otel_trace_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Enable logging instrumentation for trace correlation
    LoggingInstrumentor().instrument(set_logging_format=True)

    logger.info(f"OpenTelemetry tracing initialized for service: {service_name}")

    # Setup metrics provider
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=OTEL_EXPORTER_OTLP_METRICS_ENDPOINT)
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger.info(f"OpenTelemetry metrics initialized for service: {service_name}")


def setup_telemetry(app, engine):
    """
    Configure OpenTelemetry auto-instrumentation for all components.

    This function sets up zero-code instrumentation for:
    - FastAPI (HTTP requests, routing, middleware, metrics)
    - SQLAlchemy (database queries, transactions)
    - Celery (task execution, worker operations, metrics)
    - Redis (cache operations, result backend)

    All traces and metrics are automatically sent to Base14 Scout via OTLP exporters.
    """
    logger.info("Setting up OpenTelemetry auto-instrumentation")

    # Initialize tracing and metrics
    init_telemetry()

    # Auto-instrument FastAPI (includes HTTP metrics)
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="health", exclude_spans=["receive", "send"]
    )
    logger.info("FastAPI auto-instrumentation enabled (traces + metrics)")

    # Auto-instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        service="postgresql",
        enable_commenter=True,
        commenter_options={"db_driver": True, "db_framework": True},
    )
    logger.info("SQLAlchemy auto-instrumentation enabled")

    # Auto-instrument Celery on producer side (injects trace context into task headers)
    CeleryInstrumentor().instrument()
    logger.info("Celery auto-instrumentation enabled (producer side)")

    # Auto-instrument Redis
    RedisInstrumentor().instrument()
    logger.info("Redis auto-instrumentation enabled")

    logger.info("OpenTelemetry auto-instrumentation setup complete")


def cleanup_telemetry():
    """Cleanup telemetry resources on shutdown."""
    tracer_provider = trace.get_tracer_provider()
    if hasattr(tracer_provider, "shutdown"):
        logger.info("Shutting down OpenTelemetry tracer provider")
        tracer_provider.shutdown()

    meter_provider = metrics.get_meter_provider()
    if hasattr(meter_provider, "shutdown"):
        logger.info("Shutting down OpenTelemetry meter provider")
        meter_provider.shutdown()
