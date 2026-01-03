# config/initializers/opentelemetry.rb
# OpenTelemetry instrumentation configuration for Rails 5.2.8 + Ruby 2.7
# Following base14 Scout documentation for legacy Rails

require 'opentelemetry/sdk'
require 'opentelemetry/exporter/otlp'

OpenTelemetry::SDK.configure do |c|
  # Service configuration
  c.service_name = ENV.fetch('OTEL_SERVICE_NAME', 'rails5-app')
  c.service_version = ENV.fetch('OTEL_SERVICE_VERSION', '1.0.0')

  # Resource attributes
  c.resource = OpenTelemetry::SDK::Resources::Resource.create(
    'service.name' => ENV.fetch('OTEL_SERVICE_NAME', 'rails5-app'),
    'service.version' => ENV.fetch('OTEL_SERVICE_VERSION', '1.0.0'),
    'deployment.environment' => ENV.fetch('RAILS_ENV', 'development')
  )

  # IMPORTANT: Use SimpleSpanProcessor for Ruby 2.7 to avoid threading issues
  # BatchSpanProcessor has known issues with Ruby 2.7's GVL
  c.add_span_processor(
    OpenTelemetry::SDK::Trace::Export::SimpleSpanProcessor.new(
      OpenTelemetry::Exporter::OTLP::Exporter.new(
        endpoint: ENV.fetch('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')
      )
    )
  )

  # Install instrumentations
  # c.use 'OpenTelemetry::Instrumentation::Rack'
  # c.use 'OpenTelemetry::Instrumentation::ActiveSupport'
  # c.use 'OpenTelemetry::Instrumentation::ActiveRecord'
  # c.use 'OpenTelemetry::Instrumentation::ConcurrentRuby'
  # c.use 'OpenTelemetry::Instrumentation::Mysql2'
  # c.use 'OpenTelemetry::Instrumentation::Net::HTTP'
  # c.use 'OpenTelemetry::Instrumentation::Redis'
  # c.use 'OpenTelemetry::Instrumentation::Sidekiq'
  c.use_all
end

# Custom tracer for manual instrumentation
module OpenTelemetryHelper
  def self.tracer
    OpenTelemetry.tracer_provider.tracer('rails5-app', '1.0.0')
  end
end
