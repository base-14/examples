"""Python Hello World — OpenTelemetry"""

import logging
import os
import sys

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import OsResourceDetector, ProcessResourceDetector, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# -- Configuration ----------------------------------------------------------
# The collector endpoint. Set this to where your OTel collector accepts
# OTLP/HTTP traffic (default port 4318).
endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
if not endpoint:
    print("Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)")
    sys.exit(1)

# A Resource identifies your application in the telemetry backend.
# Every span, log, and metric carries this identity.
# Resource detectors auto-populate process and OS attributes.
resource = (
    Resource.create({"service.name": "hello-world-python"})
    .merge(ProcessResourceDetector().detect())
    .merge(OsResourceDetector().detect())
)

# -- Traces -----------------------------------------------------------------
# A TracerProvider manages the lifecycle of traces. It batches spans and
# sends them to the collector via the OTLP/HTTP exporter.
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("hello-world-python")

# -- Logs -------------------------------------------------------------------
# A LoggerProvider bridges Python's standard logging module to OpenTelemetry.
# Logs emitted inside a span automatically carry the span's trace ID and
# span ID — this is called log-trace correlation.
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs"))
)
handler = LoggingHandler(logger_provider=logger_provider)
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("hello-world-python")

# -- Metrics ----------------------------------------------------------------
# A MeterProvider manages metrics. The PeriodicExportingMetricReader collects
# and exports metric data at regular intervals.
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
    export_interval_millis=5000,
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("hello-world-python")

# A counter tracks how many times something happens.
hello_counter = meter.create_counter(
    name="hello.count",
    description="Number of times the hello-world app has run",
)

# -- Application Logic ------------------------------------------------------


def say_hello():
    """A normal operation — creates a span with an info log."""
    with tracer.start_as_current_span("say-hello") as span:
        # This log is emitted inside the span, so it carries the span's trace ID.
        # In Scout, you can jump to the trace from a log detail.
        logger.info("Hello, World!")
        hello_counter.add(1)
        span.set_attribute("greeting", "Hello, World!")


def check_disk_space():
    """A degraded operation — creates a span with a warning log."""
    with tracer.start_as_current_span("check-disk-space") as span:
        # Warnings show up in Scout with a distinct severity level, making
        # them easy to filter and spot before they become errors.
        logger.warning("Disk usage above 90%%")
        span.set_attribute("disk.usage_percent", 92)


def parse_config():
    """A failed operation — creates a span with an error and exception."""
    with tracer.start_as_current_span("parse-config") as span:
        try:
            raise ValueError("invalid config: missing 'database_url'")
        except ValueError as exc:
            # record_exception attaches the stack trace to the span.
            # set_status marks the span as errored so it stands out in TraceX.
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            logger.exception("Failed to parse configuration")


# -- Run --------------------------------------------------------------------

say_hello()
check_disk_space()
parse_config()

# -- Shutdown ---------------------------------------------------------------
# Flush all buffered telemetry to the collector before exiting.
# Without this, the last batch of spans/logs/metrics may be lost.
tracer_provider.shutdown()
logger_provider.shutdown()
meter_provider.shutdown()

print("Done. Check Scout for your trace, log, and metric.")
