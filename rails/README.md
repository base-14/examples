# Sample Rails application with OpenTelemetry instrumentation to send directly to Base14 OTLP collector with oidc

<<<<<<< HEAD
This uses oidc and directly sends the telemetry to Base14 OTLP Collector

Steps for Auto instrumenting Rails application:

1. Add these gems in the `Gemfile`

```
gem 'opentelemetry-sdk'
gem 'opentelemetry-exporter-otlp'
gem 'opentelemetry-instrumentation-all'
```

2. Create a new initilizer `config/initilizers/opentelemetry.rb`

```
require 'opentelemetry/sdk'
require 'opentelemetry/exporter/otlp'

otlp_endpoint = ENV.fetch('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://0.0.0.0:4318')

OpenTelemetry::SDK.configure do |c|
    c.service_name = ENV.fetch('OTEL_SERVICE_NAME', 'rails-app')
    c.add_span_processor(
      OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(
        OpenTelemetry::Exporter::OTLP::Exporter.new(
          endpoint: otlp_endpoint
        )
      )
    )
    c.use_all
end
```

Steps to run the application:

1. Update the environment variables in `docker-compose.yml`
   2 Run `docker-compose up --build` to run the application.

Visit [docs.base.14](http://docs.base14.io/instrument/apps/auto-instrumentation/rails) for a detailed Guide on Instrumenting Rails application
=======
Steps to run the application:
1. Install the dependencies using `bundle install`.
2. Navigate to `config/initilizers/opentelemetry.rb`.
3. update the client-id, client-secret, token-url, endpoint.
4. Run the application using `rails server`
>>>>>>> 0a72ab9 (add sample rails application with auto instrumentation)
