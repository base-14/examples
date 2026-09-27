from typing import Any

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


_reader: InMemoryMetricReader | None = None


def captured_metrics() -> InMemoryMetricReader:
    """The process-wide meter provider, set once. The example's instruments are created on the
    global proxy meter at import, so they reach this provider however early they were made."""
    global _reader
    if _reader is None:
        _reader = InMemoryMetricReader()
        metrics.set_meter_provider(MeterProvider(metric_readers=[_reader]))
    return _reader


def total(reader: InMemoryMetricReader, name: str, **attributes: Any) -> float:
    """The cumulative sum, or histogram count, of `name` over the points whose attributes
    include `attributes`."""
    data = reader.get_metrics_data()
    found = 0.0
    for resource in data.resource_metrics if data else []:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    if attributes.items() <= dict(point.attributes or {}).items():
                        found += getattr(point, "value", None) or getattr(point, "count", 0)
    return found
