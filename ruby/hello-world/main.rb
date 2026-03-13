# Ruby Hello World — OpenTelemetry (Traces Only)

require "opentelemetry-sdk"
require "opentelemetry-exporter-otlp"

# -- Configuration ----------------------------------------------------------
# The collector endpoint. Set this to where your OTel collector accepts
# OTLP/HTTP traffic (default port 4318).
endpoint = ENV["OTEL_EXPORTER_OTLP_ENDPOINT"]
unless endpoint
  warn "Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)"
  exit 1
end

# Configure the OpenTelemetry SDK.
# A Resource identifies your application in the telemetry backend.
# The SDK auto-populates process and OS attributes.
OpenTelemetry::SDK.configure do |c|
  c.service_name = "hello-world-ruby"
  c.add_span_processor(
    OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(
      OpenTelemetry::Exporter::OTLP::Exporter.new(endpoint: "#{endpoint}/v1/traces")
    )
  )
end

tracer = OpenTelemetry.tracer_provider.tracer("hello-world-ruby")

# -- Application Logic ------------------------------------------------------

# A normal operation — creates a span with an attribute.
def say_hello(tracer)
  # A span represents a unit of work. Everything inside this block is part
  # of the "say-hello" span.
  tracer.in_span("say-hello") do |span|
    span.set_attribute("greeting", "Hello, World!")
    # Add a span event — these appear as timestamped annotations on the span.
    span.add_event("greeting.sent", attributes: { "message" => "Hello, World!" })
  end
end

# A degraded operation — creates a span with a warning event.
def check_disk_space(tracer)
  tracer.in_span("check-disk-space") do |span|
    span.set_attribute("disk.usage_percent", 92)
    # Span events are the closest equivalent to logs in traces-only mode.
    # They show up as annotations on the span in TraceX.
    span.add_event("disk.warning", attributes: { "message" => "Disk usage above 90%" })
  end
end

# A failed operation — creates a span with an error and exception.
def parse_config(tracer)
  tracer.in_span("parse-config") do |span|
    begin
      raise "invalid config: missing 'database_url'"
    rescue => e
      # record_exception attaches the stack trace to the span.
      # status = Error marks the span as errored so it stands out in TraceX.
      span.record_exception(e)
      span.status = OpenTelemetry::Trace::Status.error(e.message)
    end
  end
end

# -- Run --------------------------------------------------------------------

say_hello(tracer)
check_disk_space(tracer)
parse_config(tracer)

# Flush all buffered telemetry to the collector before exiting.
# Without this, the last batch of spans may be lost.
OpenTelemetry.tracer_provider.shutdown

puts "Done. Check Scout for your traces."
