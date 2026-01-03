# Rails with OpenTelemetry

Rails 5.2.8 application with OpenTelemetry auto-instrumentation for traces,
metrics, and logs. Uses MySQL 8, Redis, and Sidekiq.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/rails)

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

| Component | Version |
| --------- | ------- |
| Rails | 5.2.8 |
| Ruby | 2.7.7 |
| MySQL | 8.0 |
| Redis | 7 |
| OpenTelemetry SDK | Latest |
| OpenTelemetry Instrumentation | Latest |
| OpenTelemetry Collector | 0.140.0 |

## Resources

- [Rails Auto-Instrumentation Guide](https://docs.base14.io/instrument/apps/auto-instrumentation/rails)
  \- Base14 documentation
- [OpenTelemetry Ruby](https://opentelemetry.io/docs/languages/ruby/) -
  OTel Ruby docs
- [Base14 Scout](https://base14.io/scout) - Observability platform
