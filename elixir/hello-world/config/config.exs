import Config

# -- OpenTelemetry Configuration ---------------------------------------------
# The Erlang OTel SDK reads OTEL_EXPORTER_OTLP_ENDPOINT from the environment
# at startup — no need to set it here.

config :opentelemetry,
  resource: %{:"service.name" => "hello-world-elixir"},
  span_processor: :batch,
  traces_exporter: :otlp

config :opentelemetry_exporter,
  otlp_protocol: :http_protobuf
