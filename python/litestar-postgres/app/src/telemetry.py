"""Manual telemetry instruments — counters/gauges/histograms not provided by
auto-instrumentation.

The MeterProvider itself is initialised by `opentelemetry-instrument` (the CLI
wrapper in the Dockerfile CMD); this module just acquires a Meter from it and
declares the instruments the app uses. Doing it here keeps the controllers
free of telemetry plumbing.

Why creating the Counter at import time is safe: `opentelemetry-instrument`
sets the global MeterProvider *before* it execs uvicorn, which then imports
this module. `metrics.get_meter()` returns a proxy that resolves to whichever
provider is current at instrument-creation time, so the Counter is bound to
the real OTLP-exporting provider — never the no-op default.
"""

from opentelemetry import metrics

_meter = metrics.get_meter("litestar-postgres-app")

articles_created = _meter.create_counter(
    name="articles.created",
    description="Number of articles successfully created",
    unit="1",
)
