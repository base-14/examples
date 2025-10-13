# Phoenix LiveView Chat with OpenTelemetry

A production-ready real-time chat application built with Phoenix LiveView, demonstrating comprehensive observability with OpenTelemetry.

## Features

- **Real-time Messaging**: Instant message delivery using Phoenix PubSub
- **Phoenix Presence**: Real-time user tracking and online status
- **Guest Mode**: No authentication required - just enter a name and chat
- **Responsive UI**: Mobile-first design with Tailwind CSS
- **OpenTelemetry Integration**: Comprehensive distributed tracing and metrics
- **Production-Ready**: Clean code, comprehensive tests, and deployment-ready configuration

## Technology Stack

- **Phoenix 1.8.1** with **LiveView 1.1+**
- **PostgreSQL** for message persistence
- **OpenTelemetry** for observability (Phoenix, Ecto, custom metrics)
- **Tailwind CSS** for responsive design
- **Phoenix Presence** for real-time user tracking

## Getting Started

### Prerequisites

- Elixir 1.14+ and Erlang/OTP 25+
- PostgreSQL 14+
- Node.js 18+ (for asset compilation)

### Setup

1. Install dependencies:

   ```bash
   mix deps.get
   ```

2. Create and migrate the database:

   ```bash
   mix ecto.setup
   ```

3. Install and build assets:

   ```bash
   mix assets.setup
   mix assets.build
   ```

4. Start the Phoenix server:

   ```bash
   mix phx.server
   ```

5. Visit [`localhost:4000`](http://localhost:4000) from your browser

## OpenTelemetry Configuration

The application is configured to export telemetry data to an OpenTelemetry collector via OTLP (HTTP).

### Environment Variables

- `OTEL_EXPORTER_OTLP_ENDPOINT` - OTLP endpoint (default: `http://localhost:4318`)

### Instrumentation

The application automatically instruments:

- **Phoenix**: HTTP requests, LiveView events, routing
- **Ecto**: Database queries and connection pool metrics
- **Custom Metrics**:
  - Message send events with user type and content length
  - Presence updates with user count
  - Validation errors

### Running with OpenTelemetry Collector

To see telemetry data, run an OpenTelemetry collector:

```bash
docker run -p 4318:4318 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otel-collector-config.yaml \
  otel/opentelemetry-collector:latest \
  --config=/etc/otel-collector-config.yaml
```

## Testing

Run the comprehensive test suite:

```bash
mix test
```

Run build-lint (compile, format, and test):

```bash
mix precommit
```

## Key Architecture Decisions

- **Message Validation**: Minimum 2 characters, required name field
- **Message Limit**: Last 20 messages displayed (configurable)
- **Temporary Assigns**: Efficient memory usage for message lists
- **Stream Updates**: Optimized real-time message rendering
- **Graceful Degradation**: OpenTelemetry export failures don't affect app functionality

## Production Deployment

1. Set required environment variables:
   - `DATABASE_URL`
   - `SECRET_KEY_BASE` (generate with `mix phx.gen.secret`)
   - `PHX_HOST`
   - `OTEL_EXPORTER_OTLP_ENDPOINT` (optional)

2. Build release:

   ```bash
   MIX_ENV=prod mix release
   ```

3. Run migrations:

   ```bash
   _build/prod/rel/chat_app/bin/chat_app eval "ChatApp.Release.migrate"
   ```

4. Start the server:

   ```bash
   PHX_SERVER=true _build/prod/rel/chat_app/bin/chat_app start
   ```

## Project Structure

```plain
lib/
├── chat_app/
│   ├── application.ex          # OTP application with OpenTelemetry setup
│   ├── chat.ex                 # Chat context with business logic
│   ├── chat/
│   │   └── message.ex          # Message schema with validation
│   ├── repo.ex                 # Ecto repository
│   └── telemetry.ex            # Custom telemetry events
├── chat_app_web/
│   ├── endpoint.ex             # Phoenix endpoint
│   ├── router.ex               # Route definitions
│   ├── presence.ex             # Phoenix Presence implementation
│   └── live/
│       ├── chat_live.ex        # Main chat LiveView
│       └── chat_live.html.heex # Chat UI template
test/
├── chat_app/
│   └── chat_test.exs           # Context tests
└── chat_app_web/
    └── live/
        └── chat_live_test.exs  # LiveView integration tests
```

## Learn More

- [Phoenix Framework](https://www.phoenixframework.org/)
- [Phoenix LiveView](https://hexdocs.pm/phoenix_live_view)
- [OpenTelemetry Erlang](https://opentelemetry.io/docs/instrumentation/erlang/)
- [Phoenix Presence](https://hexdocs.pm/phoenix/presence.html)
