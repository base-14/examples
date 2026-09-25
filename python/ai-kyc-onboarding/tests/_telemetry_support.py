from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.sdk._logs import LoggerProvider, ReadableLogRecord
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from temporalio.contrib.opentelemetry import (
    ReplaySafeMeterProvider,
    ReplaySafeTracerProvider,
    create_tracer_provider,
)


_metric_reader: InMemoryMetricReader | None = None
_logger_provider: LoggerProvider | None = None


def global_tracer_provider() -> ReplaySafeTracerProvider:
    """The process-wide tracer provider, which can be set only once per process."""
    current = trace.get_tracer_provider()
    if isinstance(current, ReplaySafeTracerProvider):
        return current
    provider = create_tracer_provider(resource=Resource.create({"service.name": "test"}))
    trace.set_tracer_provider(provider)
    return provider


def global_metric_reader() -> InMemoryMetricReader:
    """An in-memory reader behind the process-wide meter provider, which can be set only once."""
    global _metric_reader
    if _metric_reader is None:
        _metric_reader = InMemoryMetricReader()
        provider = MeterProvider(
            resource=Resource.create({"service.name": "test"}), metric_readers=[_metric_reader]
        )
        metrics.set_meter_provider(ReplaySafeMeterProvider(provider))
    return _metric_reader


def global_logger_provider() -> LoggerProvider:
    """The process-wide logger provider, installed once through `install_logging`.

    Application imports stay inside functions here because the sandbox re-imports this module.
    """
    global _logger_provider
    if _logger_provider is None:
        from kyc_onboarding.telemetry import install_logging

        _logger_provider = LoggerProvider(resource=Resource.create({"service.name": "test"}))
        install_logging(_logger_provider)
    return _logger_provider


@contextmanager
def captured_spans() -> Iterator[InMemorySpanExporter]:
    from pydantic_ai import Agent

    exporter = InMemorySpanExporter()
    global_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    Agent.instrument_all(True)
    try:
        yield exporter
    finally:
        Agent.instrument_all(False)
        exporter.shutdown()


@contextmanager
def captured_logs() -> Iterator[InMemoryLogRecordExporter]:
    exporter = InMemoryLogRecordExporter()
    global_logger_provider().add_log_record_processor(SimpleLogRecordProcessor(exporter))
    try:
        yield exporter
    finally:
        exporter.shutdown()


def named(spans: list[ReadableSpan], name: str) -> list[ReadableSpan]:
    return [span for span in spans if span.name == name]


def only(spans: list[ReadableSpan], name: str) -> ReadableSpan:
    (span,) = named(spans, name)
    return span


def span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.span_id


def trace_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.trace_id


def log_body(record: ReadableLogRecord) -> str:
    return str(record.log_record.body)


def log_attribute(record: ReadableLogRecord, key: str) -> object:
    return (record.log_record.attributes or {}).get(key)


def collected_points() -> dict[str, list[Any]]:
    """Every recorded data point by metric name, from one collection.

    Values are cumulative, but each collection returns exemplars only once.
    """
    data = global_metric_reader().get_metrics_data()
    points: dict[str, list[Any]] = {}
    for resource_metrics in data.resource_metrics if data is not None else ():
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                points.setdefault(metric.name, []).extend(metric.data.data_points)
    return points


def point_with(points: list[Any], attributes: Mapping[str, object]) -> Any | None:
    """The data point whose attributes are exactly `attributes`."""
    matching = [point for point in points if dict(point.attributes or {}) == attributes]
    return matching[0] if matching else None


def metric_point(name: str, attributes: Mapping[str, object]) -> Any | None:
    return point_with(collected_points().get(name, []), attributes)


def counter_value(name: str, attributes: Mapping[str, object]) -> int:
    point = metric_point(name, attributes)
    return int(point.value) if point is not None else 0


def histogram_count(name: str, attributes: Mapping[str, object]) -> int:
    point = metric_point(name, attributes)
    return int(point.count) if point is not None else 0
