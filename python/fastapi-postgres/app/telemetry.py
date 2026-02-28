import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_telemetry(otel_host_port: str):
    service_name = os.getenv("OTEL_SERVICE_NAME", "fastapi-postgres-app")
    resource = Resource.create({"service.name": service_name})

    trace.set_tracer_provider(TracerProvider(resource=resource))
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"http://{otel_host_port}/v1/traces"))
    )

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"http://{otel_host_port}/v1/metrics"),
        export_interval_millis=1000,
    )
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[metric_reader, PeriodicExportingMetricReader(ConsoleMetricExporter())],
        )
    )
