# app/telemetry.py
import logging
from celery.signals import worker_process_init
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from .config import OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT

@worker_process_init.connect(weak=False)
def init_celery_tracing(*args, **kwargs):
    init_tracing()
    CeleryInstrumentor().instrument()

def init_tracing():
    trace.set_tracer_provider(TracerProvider())
    tracer_provider = trace.get_tracer_provider()

    # Configure OTLP exporter with compression
    otlp_exporter = OTLPSpanExporter(
        endpoint=OTEL_EXPORTER_OTLP_ENDPOINT
    )
    otel_trace_exporter = OTLPSpanExporter(
        endpoint=OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
    )
    span_processor = BatchSpanProcessor(otel_trace_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Optionally, add a console exporter for debugging
    console_exporter = ConsoleSpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))


def setup_telemetry(app, engine):
    """Configure OpenTelemetry with all instrumentations."""
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        service="postgresql",
    )
    
    # Instrument Celery
    init_celery_tracing()
    
    # Instrument Redis
    RedisInstrumentor().instrument()


def cleanup_telemetry(trace_provider):
    """Cleanup telemetry resources."""
    if trace_provider:
        trace_provider.shutdown()