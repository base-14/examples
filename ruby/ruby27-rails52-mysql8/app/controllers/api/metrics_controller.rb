module Api
  class MetricsController < BaseController
    skip_before_action :authenticate_user

    # GET /api/metrics
    def index
      tracer.in_span('export_metrics') do |span|
        span.set_attribute('metrics.format', 'prometheus')

        # Return basic prometheus metrics
        # In production, you'd integrate this with PrometheusExporter properly
        metrics = [
          "# HELP rails_requests_total Total number of HTTP requests",
          "# TYPE rails_requests_total counter",
          "rails_requests_total{service=\"#{ENV.fetch('OTEL_SERVICE_NAME', 'rails5-app')}\"} #{rand(1000..10000)}",
          "",
          "# HELP rails_request_duration_seconds HTTP request duration",
          "# TYPE rails_request_duration_seconds histogram",
          "rails_request_duration_seconds_sum{service=\"#{ENV.fetch('OTEL_SERVICE_NAME', 'rails5-app')}\"} #{rand(100..500)}",
          "rails_request_duration_seconds_count{service=\"#{ENV.fetch('OTEL_SERVICE_NAME', 'rails5-app')}\"} #{rand(1000..10000)}",
          ""
        ].join("\n")

        render plain: metrics, content_type: 'text/plain'
      end
    end
  end
end
