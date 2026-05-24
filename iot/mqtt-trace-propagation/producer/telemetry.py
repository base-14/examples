"""OpenTelemetry SDK setup for the producer (a simulated sensor device).

The resource carries the full Scout IoT attribute schema (device.* / fleet.* /
site.*) so every span and metric is attributable to a device and fleet. These
are env-driven with demo defaults; Phase 2 (edge filtering) reads
fleet.priority and device.battery.level.
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
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "mqtt-trace-producer")


def _resource() -> Resource:
    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "device.id": os.getenv("DEVICE_ID", "sensor-001"),
            "device.kind": "sensor",
            "device.model.identifier": "sim-sensor-v1",
            "device.firmware.version": os.getenv("DEVICE_FIRMWARE_VERSION", "1.4.2"),
            "device.firmware.channel": os.getenv("DEVICE_FIRMWARE_CHANNEL", "stable"),
            "device.power.source": "battery",
            "device.battery.level": int(os.getenv("DEVICE_BATTERY_LEVEL", "100")),
            "fleet.id": os.getenv("FLEET_ID", "fleet-demo"),
            "fleet.tenant": os.getenv("FLEET_TENANT", "acme"),
            "fleet.priority": os.getenv("FLEET_PRIORITY", "normal"),
            "site.id": os.getenv("SITE_ID", "site-hq"),
        }
    )


def setup_telemetry() -> tuple[trace.Tracer, metrics.Meter]:
    resource = _resource()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)

    return trace.get_tracer(SERVICE_NAME), metrics.get_meter(SERVICE_NAME)
