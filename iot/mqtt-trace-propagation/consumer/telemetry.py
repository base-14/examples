"""OpenTelemetry SDK setup for the consumer.

Distinct service.name from the producer so the two appear as separate
services in Scout sharing one trace. requests is auto-instrumented so the
downstream HTTP call to the echo service becomes a child span automatically.
"""

from __future__ import annotations

import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "mqtt-trace-consumer")


def setup_telemetry() -> tuple[trace.Tracer, metrics.Meter]:
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "device.kind": "gateway",
            "fleet.id": os.getenv("FLEET_ID", "fleet-demo"),
            "fleet.tenant": os.getenv("FLEET_TENANT", "acme"),
            "site.id": os.getenv("SITE_ID", "site-hq"),
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)

    RequestsInstrumentor().instrument()

    return trace.get_tracer(SERVICE_NAME), metrics.get_meter(SERVICE_NAME)
