# Phoenix LiveView Chat with OpenTelemetry

Phoenix 1.8.1 application with OpenTelemetry auto-instrumentation for traces,
metrics, and logs.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/elixir-phoenix)

## What's Instrumented

- HTTP requests and LiveView events
- Database queries (Ecto)
- Phoenix PubSub and Presence events
- Custom spans for business logic
- Distributed trace propagation (W3C)

## Prerequisites

- Elixir 1.14+ and Erlang/OTP 25+
- PostgreSQL 14+
- Node.js 18+ (for asset compilation)
- base14 Scout account for traces and logs visualization
  ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/elixir/phoenix18-ecto3-postgres

# Install dependencies
mix deps.get

# Setup database
mix ecto.setup

# Install and build assets
mix assets.setup && mix assets.build

# Start application
mix phx.server

# Verify it's running
open http://localhost:4000
```

The app runs on port `4000`.

## Configuration

### Environment Variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | OTLP endpoint (http://[::1]:4318) |
| `SCOUT_CLIENT_ID` | For Scout | base14 Scout OAuth client ID |
| `SCOUT_CLIENT_SECRET` | For Scout | base14 Scout OAuth client secret |
| `SCOUT_TOKEN_URL` | For Scout | base14 Scout OAuth token endpoint |
| `SCOUT_ENDPOINT` | For Scout | base14 Scout OTLP endpoint |

## OpenTelemetry Setup

### 1. Add Dependencies (mix.exs)

```elixir
{:opentelemetry, "~> 1.3"},
{:opentelemetry_exporter, "~> 1.6"},
{:opentelemetry_phoenix, "~> 2.0"},
{:opentelemetry_ecto, "~> 1.1"}
```

### 2. Configure Application (lib/chat_app/application.ex)

```elixir
def start(_type, _args) do
  # Setup OpenTelemetry instrumentation
  OpentelemetryPhoenix.setup(adapter: :bandit)
  OpentelemetryEcto.setup([:chat_app, :repo])

  # ... rest of supervision tree
end
```

### 3. Configure Runtime (config/runtime.exs)

```elixir
config :opentelemetry,
  resource: [
    service: [
      name: "chat_app",
      version: "1.0.0"
    ]
  ]

config :opentelemetry_exporter,
  otlp_protocol: :http_protobuf,
  otlp_endpoint: System.get_env("OTEL_EXPORTER_OTLP_ENDPOINT") || "http://[::1]:4318"
```

See the full implementation in
[lib/chat_app/application.ex](./lib/chat_app/application.ex) and
[config/runtime.exs](./config/runtime.exs) for complete setup.

### Custom Instrumentation

Create custom spans for business logic:

```elixir
def create_message(attrs) do
  OpenTelemetry.Tracer.with_span "chat.create_message" do
    # Add trace context to logger metadata
    span_ctx = OpenTelemetry.Tracer.current_span_ctx()
    Logger.metadata(
      otel_trace_id: OpenTelemetry.Span.hex_trace_id(span_ctx),
      otel_span_id: OpenTelemetry.Span.hex_span_id(span_ctx)
    )

    # Your business logic
    %Message{}
    |> Message.changeset(attrs)
    |> Repo.insert()
  end
end
```

See [lib/chat_app/chat.ex](./lib/chat_app/chat.ex) for the complete example.

## Development

### Run Tests

```bash
mix test              # Run test suite
mix precommit         # Run compile, format, and test
```

### Viewing Telemetry Data

#### base14 Scout (Recommended)

Configure your application to send telemetry to base14 Scout for production-grade
trace and log visualization:

```bash
# Set Scout environment variables
export SCOUT_CLIENT_ID="your-client-id"
export SCOUT_CLIENT_SECRET="your-client-secret"
export SCOUT_TOKEN_URL="https://your-scout-instance/oauth/token"
export SCOUT_ENDPOINT="https://your-scout-instance/v1/traces"

# Start application
mix phx.server
```

View your telemetry in base14 Scout:

- **TraceX**: Distributed tracing with trace correlation and analysis
- **LogX**: Structured logs correlated with traces via `trace_id` and `span_id`

See the [base14 Scout setup guide](https://docs.base14.io/category/opentelemetry-collector-setup)
for detailed configuration.

#### Local Development

For local testing without Scout, run an OpenTelemetry collector:

```bash
docker run -p 4318:4318 \
  otel/opentelemetry-collector:latest
```

## Telemetry Data

### Traces

- HTTP requests (method, path, status, controller/action)
- LiveView events (mount, handle_event, handle_info)
- Database queries (SQL statements, duration, pool metrics)
- Custom spans (chat.create_message with success/failure)
- Phoenix PubSub broadcasts
- Phoenix Presence tracking

### Logs

All logs include `trace_id` and `span_id` for correlation. Logger is
configured to output OpenTelemetry metadata:

```elixir
config :logger, :default_formatter,
  format: "$time [$level] $message $metadata\n",
  metadata: [:otel_trace_id, :otel_span_id]
```

### Metrics

Custom telemetry events tracked:

- `chat.message.sent` - Message creation events
- `chat.presence.update` - User join/leave events
- `chat.validation.error` - Validation failure events

See [lib/chat_app/telemetry.ex](./lib/chat_app/telemetry.ex) for metric
definitions.

## Troubleshooting

### No telemetry data

```bash
# Check if collector is running
curl http://localhost:4318

# Check application logs
mix phx.server | grep -i opentelemetry
```

Verify the OTLP endpoint is accessible and OpenTelemetry libraries are
configured correctly.

### Logger format errors

If you see errors about invalid format patterns, ensure you're using
`$metadata` instead of specific `$otel_*` patterns in your logger config.

### Missing adapter configuration

If OpentelemetryPhoenix fails to start, ensure you've specified the adapter:

```elixir
OpentelemetryPhoenix.setup(adapter: :bandit)
```

### Scout authentication failed

```bash
# Verify Scout credentials
mix phx.server 2>&1 | grep -i "scout\|oidc\|token"
```

Verify Scout credentials are correct and token URL is accessible. Ensure
`SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`, and `SCOUT_TOKEN_URL` are properly set.

## Technology Stack

| Component | Version |
| --------- | ------- |
| Phoenix | 1.8.1 |
| Elixir | 1.15+ |
| Erlang/OTP | 25+ |
| LiveView | 1.1+ |
| OpenTelemetry | 1.3+ |
| PostgreSQL | 14+ |

## Resources

- [Elixir Phoenix Auto-Instrumentation Guide](https://docs.base14.io/instrument/apps/auto-instrumentation/elixir-phoenix)
  \- base14 Scout documentation
- [OpenTelemetry Erlang](https://opentelemetry.io/docs/instrumentation/erlang/)
  \- OTel Erlang docs
- [Phoenix Framework](https://www.phoenixframework.org/) - Phoenix documentation
- [base14 Scout](https://base14.io/scout) - Observability platform
