"""OTel emission for the Sparkplug decoder.

Sparkplug metric sets are runtime-defined by BIRTH, so OTel instruments are
created on first sight rather than from static config. Floats and booleans
become gauges; integers whose name looks monotonic (Throughput / *Counter /
*Total) become observable counters reading a per-series cache, so they stay
rate-able. Edge-node and device lifecycle (BIRTH / DEATH) are state
transitions, so they are emitted as OTel log records, not spans.
"""

from __future__ import annotations

import logging
import os
import re

from opentelemetry import metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "sparkplug-decoder")

_MONOTONIC_SUFFIXES = ("Counter", "Total", "Throughput", "Count")
# Optional unit hints for well-known metric names; unknown metrics ship
# unitless, since Sparkplug does not carry units in the basic metric.
_UNITS = {"Temperature": "Cel", "VibrationRMS": "mm/s", "Throughput": "{item}"}

def _metric_name(sparkplug_name: str) -> str:
    # camelCase -> snake_case, keeping trailing acronyms intact
    # (VibrationRMS -> vibration_rms, not vibration_r_m_s).
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", sparkplug_name)
    return "sparkplug." + snake.lower()


def _attrs_key(attrs: dict) -> tuple:
    return tuple(sorted(attrs.items()))


class DecoderTelemetry:
    def __init__(self) -> None:
        resource = Resource.create(
            {
                "service.name": SERVICE_NAME,
                "site.id": os.getenv("SITE_ID", "FactoryA"),
                "fleet.id": os.getenv("FLEET_ID", "factory-floor"),
            }
        )

        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
        metrics.set_meter_provider(self._meter_provider)
        self._meter = metrics.get_meter(SERVICE_NAME)

        self._logger_provider = LoggerProvider(resource=resource)
        self._logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter())
        )
        set_logger_provider(self._logger_provider)
        self._log = logging.getLogger("sparkplug")
        self._log.setLevel(logging.INFO)
        self._log.addHandler(LoggingHandler(logger_provider=self._logger_provider))

        self._gauges: dict[str, object] = {}
        self._counter_series: dict[str, dict[tuple, tuple]] = {}
        self._observable_counters: dict[str, object] = {}

        self._messages = self._meter.create_counter("sparkplug.decoder.messages_total")
        self._unresolved = self._meter.create_counter(
            "sparkplug.decoder.alias_unresolved_total"
        )
        self._seq_gaps = self._meter.create_counter("sparkplug.decoder.seq_gap_total")

    @staticmethod
    def _is_monotonic(name: str, datatype_is_int: bool) -> bool:
        return datatype_is_int and name.endswith(_MONOTONIC_SUFFIXES)

    def _ensure_counter(self, inst_name: str) -> None:
        if inst_name in self._observable_counters:
            return
        series = self._counter_series.setdefault(inst_name, {})

        def callback(_options: CallbackOptions, _series=series):
            return [Observation(value, attrs) for value, attrs in _series.values()]

        self._observable_counters[inst_name] = self._meter.create_observable_counter(
            inst_name, callbacks=[callback]
        )

    def record(
        self, sparkplug_name: str, value, datatype_is_int: bool, attrs: dict
    ) -> None:
        inst_name = _metric_name(sparkplug_name)
        if self._is_monotonic(sparkplug_name, datatype_is_int):
            self._ensure_counter(inst_name)
            self._counter_series[inst_name][_attrs_key(attrs)] = (int(value), dict(attrs))
            return
        gauge = self._gauges.get(inst_name)
        if gauge is None:
            unit = _UNITS.get(sparkplug_name, "")
            gauge = self._meter.create_gauge(inst_name, unit=unit)
            self._gauges[inst_name] = gauge
        gauge.set(float(value), attrs)

    def lifecycle(self, message: str, *, dead: bool, attrs: dict) -> None:
        if dead:
            self._log.warning(message, extra=attrs)
        else:
            self._log.info(message, extra=attrs)

    def count_message(self, message_type: str) -> None:
        self._messages.add(1, {"sparkplug.message_type": message_type})

    def count_unresolved(self, attrs: dict) -> None:
        self._unresolved.add(1, attrs)

    def count_seq_gap(self, attrs: dict) -> None:
        self._seq_gaps.add(1, attrs)

    def shutdown(self) -> None:
        self._meter_provider.shutdown()
        self._logger_provider.shutdown()
