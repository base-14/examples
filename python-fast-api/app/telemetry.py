from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

def setup_telemetry(otel_host_port: str):
    resource = Resource.create({"service.name": "custom-fastapi-service"})

    trace.set_tracer_provider(TracerProvider(resource=resource))
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"http://{otel_host_port}/v1/traces"))
    )

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"http://{otel_host_port}/v1/metrics"),
        export_interval_millis=1000
    )
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[metric_reader, PeriodicExportingMetricReader(ConsoleMetricExporter())]
        )
    )
