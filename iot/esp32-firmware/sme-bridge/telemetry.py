"""OTel emission for the SME-v1 bridge.

A constrained device sends a compact JSON envelope; this turns it into
ordinary OpenTelemetry. Each device gets its own Resource (built from the
envelope's `device` block) so device.* / fleet.* land as resource
attributes, not datapoint attributes. Counters arrive as running totals,
so they become observable monotonic Sums reading a per-series cache and
stay rate-able. Events become log records; a present traceparent wraps
the handling in a span that continues the device's trace.
"""

from __future__ import annotations

import logging
import os

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "sme-bridge")

_SEVERITY = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_propagator = TraceContextTextMapPropagator()


def _attrs_key(attrs: dict) -> tuple:
    return tuple(sorted(attrs.items()))


class DeviceTelemetry:
    """Per-device OTel providers, resource built from the device block."""

    def __init__(self, resource_attrs: dict) -> None:
        resource = Resource.create({"service.name": SERVICE_NAME, **resource_attrs})

        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
        self._logger_provider = LoggerProvider(resource=resource)
        self._logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter())
        )
        self._tracer_provider = TracerProvider(resource=resource)
        self._tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

        self._meter = self._meter_provider.get_meter(SERVICE_NAME)
        self._tracer = self._tracer_provider.get_tracer(SERVICE_NAME)

        self._log = logging.getLogger("sme." + str(resource_attrs.get("device.id")))
        self._log.setLevel(logging.DEBUG)
        self._log.propagate = False
        if not self._log.handlers:
            self._log.addHandler(LoggingHandler(logger_provider=self._logger_provider))

        self._gauges: dict[str, object] = {}
        self._counters: dict[str, object] = {}
        self._counter_series: dict[str, dict[tuple, tuple]] = {}

    def _ensure_counter(self, name: str, unit: str) -> None:
        if name in self._counters:
            return
        series = self._counter_series.setdefault(name, {})

        def callback(_options: CallbackOptions, _series=series):
            return [Observation(value, attrs) for value, attrs in _series.values()]

        self._counters[name] = self._meter.create_observable_counter(
            name, unit=unit, callbacks=[callback]
        )

    def record_metric(self, name, kind, value, unit, attrs) -> None:
        if kind == "counter":
            self._ensure_counter(name, unit)
            self._counter_series[name][_attrs_key(attrs)] = (value, dict(attrs))
            return
        gauge = self._gauges.get(name)
        if gauge is None:
            gauge = self._meter.create_gauge(name, unit=unit)
            self._gauges[name] = gauge
        gauge.set(float(value), attrs)

    def emit_event(self, name, severity, attrs) -> None:
        self._log.log(_SEVERITY.get(severity, logging.INFO), name, extra=attrs)

    def trace_publish(self, traceparent, attrs) -> None:
        parent = _propagator.extract({"traceparent": traceparent})
        span = self._tracer.start_span("mcu.publish", context=parent, attributes=attrs)
        # The publish already happened on-device; this span records the
        # bridge handling it, linked into the device's trace, then ends.
        span.end()

    def shutdown(self) -> None:
        self._meter_provider.shutdown()
        self._logger_provider.shutdown()
        self._tracer_provider.shutdown()


class BridgeTelemetry:
    """Owns per-device telemetry plus the bridge's own housekeeping metrics."""

    def __init__(self) -> None:
        resource = Resource.create({"service.name": SERVICE_NAME})
        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
        meter = self._meter_provider.get_meter(SERVICE_NAME)
        self._messages = meter.create_counter("sme_bridge.messages_total")
        self._parse_errors = meter.create_counter("sme_bridge.parse_errors_total")
        self._version_rejected = meter.create_counter(
            "sme_bridge.version_rejected_total"
        )
        self._devices: dict[str, DeviceTelemetry] = {}

    def device(self, device_id: str, resource_attrs: dict) -> DeviceTelemetry:
        dev = self._devices.get(device_id)
        if dev is None:
            dev = DeviceTelemetry(resource_attrs)
            self._devices[device_id] = dev
        return dev

    def count_message(self, result: str) -> None:
        self._messages.add(1, {"result": result})

    def count_parse_error(self) -> None:
        self._parse_errors.add(1)
        self.count_message("parse_error")

    def count_version_rejected(self, version) -> None:
        self._version_rejected.add(1, {"sme.version": str(version)})
        self.count_message("version_rejected")

    def shutdown(self) -> None:
        for dev in self._devices.values():
            dev.shutdown()
        self._meter_provider.shutdown()
