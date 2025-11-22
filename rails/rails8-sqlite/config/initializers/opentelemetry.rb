# OpenTelemetry Auto-Instrumentation for Rails
# Configures traces (stable auto-instrumentation)
require "opentelemetry/sdk"
require "opentelemetry/exporter/otlp"
require "opentelemetry/instrumentation/all"

# Configure Traces (Stable)
OpenTelemetry::SDK.configure do |c|
  c.use_all()
end

# Add trace correlation to Rails logs
module OpenTelemetryLoggingExtension
  def formatter
    @formatter ||= proc do |severity, timestamp, progname, msg|
      current_span = OpenTelemetry::Trace.current_span
      trace_id = current_span.context.hex_trace_id
      span_id = current_span.context.hex_span_id
      "[trace_id=#{trace_id} span_id=#{span_id}] #{severity}, [#{timestamp}] #{progname}: #{msg}\n"
    end
  end

  def formatter=(value)
    @formatter = value
  end
end

# Configure to apply trace correlation extension after Rails is initialized
Rails.application.config.to_prepare do
  # Add trace_id and span_id to log output for correlation
  unless Rails.logger.class.name.include?("OpenTelemetryLoggingExtension")
    Rails.logger.extend(OpenTelemetryLoggingExtension)
    Rails.logger.info "OpenTelemetry traces auto-instrumentation initialized"
  end
end
