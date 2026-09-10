# Rails with OpenTelemetry

Rails 5.2.8 application with OpenTelemetry auto-instrumentation for traces,
metrics, and logs. Uses MySQL 8, Redis, and Sidekiq.

> ⚠️ **Security Notice**: This project uses Rails 5.2.x (EOL June 2022) and
> Ruby 2.7 (EOL March 2023) with known security vulnerabilities.
> **Not recommended for production use.** For production, upgrade to Rails 8+ with Ruby 3.3+.
> See [SECURITY.md](./SECURITY.md) for details.
>
> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/rails)

## How to instrument Rails 5.2 on Ruby 2.7 with OpenTelemetry

1. Pin Ruby 2.7 compatible gems in the `Gemfile`: `opentelemetry-sdk` (>= 1.2.0),
   `opentelemetry-exporter-otlp` (>= 0.24.2), `opentelemetry-instrumentation-rack` (~> 0.22.1),
   `opentelemetry-instrumentation-action_pack` (~> 0.4.1),
   `opentelemetry-instrumentation-active_record` (~> 0.4.1),
   `opentelemetry-instrumentation-active_support` (~> 0.3.0) and
   `opentelemetry-instrumentation-sidekiq` (~> 0.23.0). `opentelemetry-instrumentation-all` is not
   used.
2. In `config/initializers/opentelemetry.rb`, call `OpenTelemetry::SDK.configure` with an explicit
   `Resource`, a `SimpleSpanProcessor` wrapping `OpenTelemetry::Exporter::OTLP::Exporter` (the
   `BatchSpanProcessor` has GVL issues on Ruby 2.7), then `c.use_all`.
3. Set `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`,
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` and `OTEL_TRACES_EXPORTER=otlp` in
   `docker-compose.yml` for both the web and Sidekiq containers.

This example adds Sidekiq job spans, custom model spans (`article.favorite`, `user.follow`,
`comment.created`) created through `OpenTelemetryHelper.tracer`, and a `SimpleSpanProcessor` setup
that works on Ruby 2.7. The full guide is
[Rails OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/rails/).

## What's Instrumented

- HTTP requests and responses
- Database queries (ActiveRecord with MySQL)
- Background jobs (Sidekiq) and cache operations
- Distributed trace propagation (W3C)

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Base14 Scout OIDC credentials ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
- Ruby 2.7+ (only for local development without Docker)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/ruby/ruby27-rails52-mysql8

# Configure Scout credentials
cp .env.example .env
# Edit .env and update SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET, SCOUT_TOKEN_URL, SCOUT_ENDPOINT

# Start application
docker-compose up --build

# In another terminal, setup database
docker-compose exec web rails db:create
docker-compose exec web rails db:migrate
docker-compose exec web rails db:seed

# Verify it's running
curl -s http://localhost:3000/api/health
curl -s http://localhost:3000/api/articles.json
```

The app runs on port `3000`.

## Configuration

### Environment Variables (.env)

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `OTEL_SERVICE_NAME` | Yes | Service name for OpenTelemetry |
| `SCOUT_CLIENT_ID` | Yes | Base14 Scout OAuth client ID |
| `SCOUT_CLIENT_SECRET` | Yes | Base14 Scout OAuth client secret |
| `SCOUT_TOKEN_URL` | Yes | Base14 Scout OAuth token endpoint |
| `SCOUT_ENDPOINT` | Yes | Base14 Scout OTLP endpoint |

### OpenTelemetry Customization

The OpenTelemetry configuration is in
[config/initializers/opentelemetry.rb](./config/initializers/opentelemetry.rb).
You can customize:

- Service name and version
- OIDC token fetching logic
- Instrumentation options
- Custom span processors
- Log correlation settings

## Development

### Run Locally (without Docker)

```bash
bundle install          # Install dependencies
bin/rails db:setup      # Setup database
bin/rails server        # Run application
```

Set required environment variables before running locally.

### Docker Commands

```bash
docker-compose up --build        # Build and start
docker-compose down              # Stop all
docker-compose down -v           # Stop and remove volumes
docker-compose logs -f web       # View logs
docker-compose exec web bash     # Access container shell
```

## API Examples

### Batch Processing with Threads

Process multiple articles concurrently:

```bash
curl -X POST http://localhost:3000/api/jobs/bulk_process \
  -H "Content-Type: application/json" \
  -d '{"count": 10, "operation": "analyze"}'
```

Operations: `analyze`, `translate`, `moderate`

This demonstrates concurrent thread execution with OpenTelemetry tracing.

## Telemetry Data

### Traces

- HTTP requests (method, URL, status, controller/action)
- Database queries (SQL statements, duration)
- Background jobs (Sidekiq)
- Concurrent thread execution in batch jobs
- Exceptions with stack traces

### Logs

All Rails logs include `trace_id` and `span_id` for correlation. The
initializer extends the Rails logger to automatically add trace context to
every log entry.

## Troubleshooting

### Authentication failed

```bash
docker-compose logs otel-collector | grep -i "oidc\|token"
```

Verify Scout credentials are correct and token URL is accessible.

### No telemetry data

```bash
docker-compose logs web | grep -i opentelemetry
```

Check that Scout endpoint is reachable and OIDC token is being fetched
successfully.

### Enable debug logging

In `docker-compose.yml`:

```yaml
environment:
  - RAILS_LOG_LEVEL=debug
```

## Technology Stack

| Component | Version | Notes |
| --------- | ------- | ----- |
| Rails | 5.2.8 | ⚠️ EOL (June 2022) - See [SECURITY.md](./SECURITY.md) |
| Ruby | 2.7.7 | ⚠️ EOL (March 2023) |
| MySQL | 8.0 | ✅ Supported |
| Redis | 7 | ✅ Supported |
| OpenTelemetry SDK | Latest | ✅ Current |
| OpenTelemetry Instrumentation | Latest | ✅ Current |
| OpenTelemetry Collector | 0.140.0 | ✅ Current |

## Resources

- [Rails Auto-Instrumentation Guide](https://docs.base14.io/instrument/apps/auto-instrumentation/rails)
  \- Base14 documentation
- [OpenTelemetry Ruby](https://opentelemetry.io/docs/languages/ruby/) -
  OTel Ruby docs
- [Base14 Scout](https://base14.io/scout) - Observability platform
