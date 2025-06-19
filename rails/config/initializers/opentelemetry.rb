# Standard OpenTelemetry setup following the official documentation
require "opentelemetry/sdk"
require "opentelemetry/exporter/otlp"
require "opentelemetry/instrumentation/all"
require "opentelemetry/sdk/trace/export/console_span_exporter"
require "net/http"
require "json"

# Function to fetch OIDC token
def fetch_oidc_token
  client_id = ENV.fetch("SCOUT_CLIENT_ID")
  client_secret = ENV.fetch("SCOUT_CLIENT_SECRET")
  token_url = ENV.fetch("SCOUT_TOKEN_URL")

  uri = URI(token_url)
  request = Net::HTTP::Post.new(uri)
  request.set_form_data(
    "grant_type" => "client_credentials",
    "client_id" => client_id,
    "client_secret" => client_secret
  )

  response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https") do |http|
    http.request(request)
  end

  if response.is_a?(Net::HTTPSuccess)
    puts "Fetched OIDC token: #{JSON.parse(response.body)["access_token"]}"
    JSON.parse(response.body)["access_token"]
  else
    Rails.logger.error "Failed to fetch OIDC token: #{response.body}"
    nil
  end
end

# Configure OpenTelemetry
OpenTelemetry::SDK.configure do |c|
  endpoint = ENV.fetch("SCOUT_ENDPOINT")
  c.service_name = ENV.fetch("OTEL_SERVICE_NAME", "hotel-food-app")

  token = fetch_oidc_token
  headers = {}
  headers["Authorization"] = "Bearer #{token}" if token

  otlp_exporter = OpenTelemetry::Exporter::OTLP::Exporter.new(
    endpoint: endpoint,
    headers: headers
  )
  c.add_span_processor(
    OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(otlp_exporter)
  )

  c.use_all()
end

module OpenTelemetryLoggingExtension
  def self.extended(base)
    class << base
      alias_method :original_formatter, :formatter if method_defined?(:formatter)
      def formatter
        proc do |severity, timestamp, progname, msg|
          current_span = OpenTelemetry::Trace.current_span
          trace_id = current_span.context.hex_trace_id
          span_id = current_span.context.hex_span_id
          original_format = if respond_to?(:original_formatter) && original_formatter
                             original_formatter.call(severity, timestamp, progname, msg)
          else
                             "#{severity} [#{timestamp}]: #{msg}\n"
          end
          "[trace_id=#{trace_id} span_id=#{span_id}] #{original_format}"
        end
      end
    end
  end
end

# Configure to apply our extension after Rails is initialized
Rails.application.config.to_prepare do
  unless Rails.logger.class.name.include?("OpenTelemetryLoggingExtension")
    Rails.logger.extend(OpenTelemetryLoggingExtension)
    Rails.logger.info "OpenTelemetry logging extension initialized"
  end
end
