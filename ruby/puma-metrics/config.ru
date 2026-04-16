require "yabeda/prometheus"

# Exposes Yabeda metrics at /metrics in Prometheus exposition format.
# The OpenTelemetry Collector scrapes this endpoint.
use Yabeda::Prometheus::Exporter, path: "/metrics"

app = proc do |_env|
  [200, { "content-type" => "text/plain" }, ["OK\n"]]
end

run app
