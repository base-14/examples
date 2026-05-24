"""OTel SDK setup for the bridge: traces, metrics, and logs over OTLP/HTTP.

The resource carries site and fleet identity; per-metric asset.* attributes
are attached by the mapper. Logs go through the standard logging module via an
OTel LoggingHandler, so `log.warning(msg, extra={"asset.id": ...})` becomes an
OTLP log record carrying those attributes.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "opcua-bridge")


def _resource() -> Resource:
    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "site.id": os.getenv("SITE_ID", "site-hq"),
            "site.name": os.getenv("SITE_NAME", "HQ Plant"),
            "fleet.id": os.getenv("FLEET_ID", "factory-floor"),
        }
    )


def setup_telemetry() -> tuple[trace.Tracer, metrics.Meter, logging.Logger]:
    resource = _resource()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)

    bridge_log = logging.getLogger("bridge")
    bridge_log.setLevel(logging.INFO)
    bridge_log.addHandler(LoggingHandler(logger_provider=logger_provider))

    return (
        trace.get_tracer(SERVICE_NAME),
        metrics.get_meter(SERVICE_NAME),
        bridge_log,
    )
