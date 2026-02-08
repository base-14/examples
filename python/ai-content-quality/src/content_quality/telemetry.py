import atexit
import logging
import os
from importlib.metadata import version
from typing import Any

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


logger = logging.getLogger(__name__)


def setup_telemetry(
    service_name: str,
    otlp_endpoint: str,
) -> tuple[trace.Tracer, metrics.Meter]:
    """Initialize unified observability.

    Sets up:
    1. Trace provider with OTLP exporter (for spans)
    2. Meter provider with OTLP exporter (for metrics)
    3. Log provider with OTLP exporter (for logs with trace correlation)
    4. Auto-instrumentation for logging (trace_id/span_id correlation)

    GenAI telemetry (spans, metrics, events) is handled by custom instrumentation
    in llm.py following OTel GenAI semantic conventions. We intentionally do NOT use
    OpenInference/LlamaIndex auto-instrumentation to avoid non-standard attributes
    (llm.*, input.*, output.*) that pollute the telemetry with framework-specific
    data outside the OTel GenAI semconv.

    Args:
        service_name: Service identifier for all telemetry
        otlp_endpoint: OTLP collector endpoint (e.g., "http://otel-collector:4318")

    Returns:
        Tuple of (tracer, meter) for custom instrumentation
    """
    if os.environ.get("OTEL_SDK_DISABLED") == "true":
        logger.info("OpenTelemetry disabled")
        return trace.get_tracer(service_name), metrics.get_meter(service_name)

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": version("ai-content-quality"),
            "deployment.environment": os.getenv("SCOUT_ENVIRONMENT", "development"),
        }
    )

    # Traces
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(trace_provider)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics"),
        export_interval_millis=10000,
    )
    metric_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metric_provider)

    # Logs
    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs"))
    )
    _logs.set_logger_provider(log_provider)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=log_provider))

    # Graceful shutdown: flush buffered telemetry on exit
    atexit.register(trace_provider.shutdown)
    atexit.register(metric_provider.shutdown)
    atexit.register(log_provider.shutdown)

    # Auto-instrumentation: logging (adds trace_id/span_id to log records)
    LoggingInstrumentor().instrument(set_logging_format=True)

    logger.info(
        "OpenTelemetry initialized",
        extra={"service": service_name, "endpoint": otlp_endpoint},
    )

    return trace.get_tracer(service_name), metrics.get_meter(service_name)


def instrument_fastapi(app: Any) -> None:
    """Instrument FastAPI app after creation.

    Creates spans for every HTTP request with method, path, status code, duration.
    Must be called AFTER the FastAPI app is created.
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health",
        exclude_spans=["receive", "send"],
    )
