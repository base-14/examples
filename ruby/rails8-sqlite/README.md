# Rails with OpenTelemetry

Rails 8.1.1 application with OpenTelemetry auto-instrumentation for traces,
metrics, and logs.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/rails)

## What's Instrumented

- HTTP requests and responses
- Database queries (ActiveRecord)
- Background jobs and cache operations
- Action Cable connections
- Distributed trace propagation (W3C)

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Base14 Scout OIDC credentials ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
- Ruby 3.3+ (only for local development without Docker)

## Quick Start

### First Time Setup - Generate Master Key

⚠️ The example includes a demo master key. For production or your own testing, generate a new one:

```bash
# Remove demo credentials
rm config/master.key config/credentials.yml.enc

# Rails will auto-generate master key when you edit credentials
bin/rails credentials:edit

# Never commit config/master.key (already in .gitignore)
# In production, use: RAILS_MASTER_KEY=<your-key> environment variable
```

### Run the Application

```bash
# Configure Scout credentials in docker-compose.yml
# Update SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET, SCOUT_TOKEN_URL, SCOUT_ENDPOINT

# Start application
docker-compose up --build

# Verify it's running
curl http://localhost:3000
```

The app runs on port `3000`.

## Configuration

### Environment Variables (docker-compose.yml)

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `OTEL_SERVICE_NAME` | Yes | Service name for OpenTelemetry |
| `SCOUT_CLIENT_ID` | Yes | Base14 Scout OAuth client ID |
| `SCOUT_CLIENT_SECRET` | Yes | Base14 Scout OAuth client secret |
| `SCOUT_TOKEN_URL` | Yes | Base14 Scout OAuth token endpoint |
| `SCOUT_ENDPOINT` | Yes | Base14 Scout OTLP endpoint |

## OpenTelemetry Setup

### 1. Add Gems (Gemfile)

```ruby
gem 'opentelemetry-sdk'
gem 'opentelemetry-exporter-otlp'
gem 'opentelemetry-instrumentation-all'
```

### 2. Create Initializer (config/initializers/opentelemetry.rb)

```ruby
require 'opentelemetry/sdk'
require 'opentelemetry/exporter/otlp'

OpenTelemetry::SDK.configure do |c|
  c.service_name = ENV.fetch('OTEL_SERVICE_NAME', 'rails-app')

  # Fetch OIDC token for authentication
  token = fetch_oidc_token
  headers = { 'Authorization' => "Bearer #{token}" } if token

  # Configure OTLP exporter
  otlp_exporter = OpenTelemetry::Exporter::OTLP::Exporter.new(
    endpoint: ENV.fetch('SCOUT_ENDPOINT'),
    headers: headers
  )

  c.add_span_processor(
    OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(otlp_exporter)
  )

  # Enable all automatic instrumentation
  c.use_all
end
```

See the full implementation in
[config/initializers/opentelemetry.rb](./config/initializers/opentelemetry.rb)
for OIDC token fetching and log correlation.

### Resource Attributes

Automatically included in telemetry:

```ruby
service.name=ruby-rails8-sqlite-otel
telemetry.sdk.name=opentelemetry
telemetry.sdk.language=ruby
```

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
```

## Telemetry Data

### Traces

- HTTP requests (method, URL, status, controller/action)
- Database queries (SQL statements, duration)
- View rendering and background jobs
- Exceptions with stack traces

### Logs

All Rails logs include `trace_id` and `span_id` for correlation. The
initializer extends the Rails logger to automatically add trace context to
every log entry.

## Troubleshooting

### Authentication failed

```bash
docker-compose logs web | grep -i "oidc\|token"
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
| Rails | 8.1.1 |
| Ruby | 3.3+ |
| OpenTelemetry SDK | Latest |
| OpenTelemetry Instrumentation | Latest |
| SQLite | 2.1+ |

## Resources

- [Rails Auto-Instrumentation Guide](https://docs.base14.io/instrument/apps/auto-instrumentation/rails)
  \- Base14 documentation
- [OpenTelemetry Ruby](https://opentelemetry.io/docs/languages/ruby/) -
  OTel Ruby docs
- [Base14 Scout](https://base14.io/scout) - Observability platform
