"""Unified observability setup for AI Sales Intelligence.

This module configures OpenTelemetry for traces, metrics, and logs,
exporting to Base14 Scout via OTLP.

IMPORTANT: Import this module BEFORE creating the FastAPI app.

Instrumentation Strategy:
- AUTO-INSTRUMENTATION: FastAPI, SQLAlchemy, httpx, logging
  (These are handled by OTel instrumentors - zero custom code needed)
- CUSTOM INSTRUMENTATION: GenAI metrics and spans in llm.py
  (Auto-instrumentation doesn't understand LLM semantics)
"""

import logging
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from sales_intelligence.config import get_settings


logger = logging.getLogger(__name__)


def setup_telemetry(
    engine: Any = None,
) -> tuple[trace.Tracer, metrics.Meter]:
    """Initialize unified observability.

    This function sets up:
    1. Trace provider with OTLP exporter (for spans)
    2. Meter provider with OTLP exporter (for metrics)
    3. Auto-instrumentation for FastAPI, SQLAlchemy, httpx, logging

    Auto-instrumentation provides:
    - HTTP spans: All FastAPI requests automatically traced
    - DB spans: All SQLAlchemy queries automatically traced
    - External HTTP spans: All httpx calls (including LLM APIs) traced
    - Log correlation: trace_id and span_id added to log records

    Custom instrumentation (in llm.py) adds:
    - GenAI semantic attributes: model, tokens, cost, provider
    - GenAI metrics: token usage, operation duration, cost tracking
    - Business context: agent name, campaign ID for attribution

    Args:
        engine: SQLAlchemy engine for DB instrumentation (optional)

    Returns:
        Tuple of (tracer, meter) for custom instrumentation
    """
    settings = get_settings()

    if not settings.otel_enabled:
        logger.info("OpenTelemetry disabled")
        return trace.get_tracer(settings.otel_service_name), metrics.get_meter(
            settings.otel_service_name
        )

    # Resource identifies this service in all telemetry
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "2.0.0",
            "deployment.environment": settings.scout_environment,
        }
    )

    # === TRACES ===
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
        )
    )
    trace.set_tracer_provider(trace_provider)

    # === METRICS ===
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/metrics"),
        export_interval_millis=10000,
    )
    metric_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metric_provider)

    # === AUTO-INSTRUMENTATION ===
    # These instrumentors add spans automatically without any code changes

    # httpx: Traces all outbound HTTP calls (including LLM API calls)
    # Benefit: See HTTP-level details (status code, latency) for debugging
    HTTPXClientInstrumentor().instrument()

    # logging: Adds trace_id and span_id to all log records
    # Benefit: Correlate logs with traces in Scout dashboards
    LoggingInstrumentor().instrument(set_logging_format=True)

    # SQLAlchemy: Traces all database queries
    # Benefit: See query SQL, parameters, and duration in trace waterfall
    if engine:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    logger.info(
        "OpenTelemetry initialized",
        extra={
            "service": settings.otel_service_name,
            "endpoint": settings.otel_exporter_otlp_endpoint,
        },
    )

    return trace.get_tracer(settings.otel_service_name), metrics.get_meter(
        settings.otel_service_name
    )


def instrument_fastapi(app: Any) -> None:
    """Instrument FastAPI app after creation.

    AUTO-INSTRUMENTATION for HTTP layer:
    - Creates spans for every HTTP request
    - Records method, path, status code, duration
    - Propagates trace context to child spans

    This must be called AFTER the FastAPI app is created.

    Args:
        app: FastAPI application instance
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health", exclude_spans=["receive", "send"])
