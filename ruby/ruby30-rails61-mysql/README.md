# Ruby 3.0 + Rails 6.1 + MySQL with OpenTelemetry

Legacy Rails 6.1 API application on Ruby 3.0 with OpenTelemetry for traces,
DB correlation, and log correlation.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/rails-legacy#ruby-30--rails-61)

## Why This Stack

Ruby 3.0 reached EOL in March 2024, and Rails 6.1 in April
2024. Many production apps still run this combination and
cannot upgrade immediately. The latest OTel Ruby gems require
Ruby >= 3.1, so this example pins the last compatible versions
to show that observability is still achievable on legacy
stacks.

## What's Instrumented

### Auto-Instrumentation

- HTTP requests and responses (Rack + ActionPack)
- Database queries — `select`, `insert`, `begin`, `commit` (MySQL2)
- ActiveRecord model operations — `Item.create!`, `Item#save!`, `Item query` (ActiveRecord)
- Distributed trace propagation (W3C)

### Custom Instrumentation

- **Custom spans**: `item.create` with business attributes (`item.title`, `item.id`)
- **Error recording**: `span.record_exception` +
  `span.status = ERROR` on RecordNotFound
- **Log correlation**: `trace_id` + `span_id` injected into
  WARN and ERROR log messages
- **Trace context in responses**: 404 JSON body includes
  `trace_id` for client-side debugging

Service name: `ruby30-rails61-mysql-otel` (configurable via `OTEL_SERVICE_NAME`)

## Stack

| Component | Version | Notes |
| --------- | ------- | ----- |
| Ruby | 3.0.7 | EOL Mar 2024 — last supported by OTel SDK 1.7.0 |
| Rails | 6.1.7 | EOL Apr 2024 — API-only mode |
| MySQL | 8.0 | LTS, widely deployed |
| Puma | 5.6 | Compatible with Ruby 3.0 + Rails 6.1 |
| OTel Collector | 0.144.0 | Contrib distribution |

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Base14 Scout OIDC credentials ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))

## Quick Start

```bash
# Configure Scout credentials (optional, works without for local dev)
cp .env.example .env
# Edit .env with your Scout credentials

docker compose up --build
```

The app runs on port `3000`.

### Test the API

```bash
./scripts/test-api.sh
```

### Verify Scout Integration

```bash
./scripts/verify-scout.sh
```

## API Endpoints

| Method | Path | Telemetry |
| ------ | ---- | --------- |
| GET | `/api/health` | Excluded via collector filter |
| POST | `/api/items` | Custom span + DB correlation + WARN |
| GET | `/api/items/:id` | DB correlation + error on 404 |

## OpenTelemetry Setup

### 1. Add Gems (Gemfile)

Core OTel gems are pinned to the last versions compatible with Ruby 3.0:

```ruby
gem "opentelemetry-api", "1.4.0"
gem "opentelemetry-sdk", "1.7.0"
gem "opentelemetry-exporter-otlp", "0.29.1"
gem "opentelemetry-instrumentation-rails", "0.34.1"
gem "opentelemetry-instrumentation-mysql2", "0.28.0"
```

### 2. Create Initializer (config/initializers/opentelemetry.rb)

```ruby
require "opentelemetry/sdk"
require "opentelemetry/exporter/otlp"

OpenTelemetry::SDK.configure do |c|
  c.use_all()
end
```

`use_all()` enables auto-instrumentation for Rack, ActionPack, ActiveRecord,
ActiveSupport, and MySQL2. The OTLP exporter endpoint is configured via
environment variables in `compose.yml`.

### 3. Custom Spans (app/controllers/items_controller.rb)

```ruby
tracer = OpenTelemetry.tracer_provider.tracer("items-controller")

tracer.in_span("item.create", attributes: { "item.title" => title }) do |span|
  # Business logic here — auto-instrumented DB calls nest under this span
  item = Item.create!(item_params)
  span.set_attribute("item.id", item.id)
end
```

This produces the trace hierarchy:

```text
HTTP POST /api/items
  └── item.create        (custom span)
      ├── Item query      (ActiveRecord auto)
      ├── select          (MySQL2 auto)
      ├── begin           (MySQL2 auto)
      ├── insert          (MySQL2 auto)
      ├── Item#save!      (ActiveRecord auto)
      ├── Item.create!    (ActiveRecord auto)
      └── commit          (MySQL2 auto)
```

### 4. Error Recording (app/controllers/application_controller.rb)

```ruby
rescue_from ActiveRecord::RecordNotFound, with: :handle_not_found

def handle_not_found(exception)
  span = OpenTelemetry::Trace.current_span
  span.record_exception(exception)
  span.status = OpenTelemetry::Trace::Status.error(exception.message)

  trace_id = span.context.hex_trace_id
  span_id = span.context.hex_span_id
  Rails.logger.error "[trace_id=#{trace_id} span_id=#{span_id}] #{exception.class}: #{exception.message}"

  render json: { error: "Not found", trace_id: trace_id }, status: :not_found
end
```

### 5. Log Correlation

Trace context is injected directly into log messages at the application level:

```ruby
# WARN on duplicate title detection
Rails.logger.warn "[trace_id=#{trace_id} span_id=#{span_id}] Duplicate title detected..."

# ERROR on exception
Rails.logger.error "[trace_id=#{trace_id} span_id=#{span_id}] #{exception.class}: #{exception.message}"
```

Example log output:

<!-- markdownlint-disable MD013 -->

```text
[trace_id=933bb053507... span_id=8686dd465...] Duplicate title detected, creating anyway: Test
[trace_id=a1588895a08... span_id=05e7c96b9...] ActiveRecord::RecordNotFound: Couldn't find Item with 'id'=99999
```

<!-- markdownlint-enable MD013 -->

## Telemetry Scenarios

### 1. Traces with DB correlation

```bash
curl -X POST http://localhost:3000/api/items \
  -H "Content-Type: application/json" \
  -d '{"item":{"title":"Test","description":"Hello"}}'
```

### 2. WARN log with trace context

```bash
# Create same title twice — second request triggers WARN
curl -X POST http://localhost:3000/api/items \
  -H "Content-Type: application/json" \
  -d '{"item":{"title":"Test","description":"Duplicate"}}'

# Check logs
docker compose logs app | grep "Duplicate"
```

### 3. Error with trace correlation

```bash
curl http://localhost:3000/api/items/99999
# Returns: {"error":"Not found","trace_id":"abc123..."}

# Check logs
docker compose logs app | grep "trace_id"
```

## Configuration

### Environment Variables (compose.yml)

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `OTEL_SERVICE_NAME` | Yes | Service name for OpenTelemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Yes | Collector endpoint |
| `DATABASE_HOST` | Yes | MySQL hostname |
| `SCOUT_CLIENT_ID` | No | Base14 Scout OAuth client ID |
| `SCOUT_CLIENT_SECRET` | No | Base14 Scout OAuth client secret |
| `SCOUT_TOKEN_URL` | No | Base14 Scout OAuth token endpoint |
| `SCOUT_ENDPOINT` | No | Base14 Scout OTLP endpoint |
| `SCOUT_ENVIRONMENT` | No | Deployment environment label |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | No | OTLP transport (`http/protobuf`) |

## Pinned Gem Versions

These are the last OTel gem versions compatible with Ruby 3.0:

| Gem | Version |
| --- | ------- |
| opentelemetry-api | 1.4.0 |
| opentelemetry-sdk | 1.7.0 |
| opentelemetry-exporter-otlp | 0.29.1 |
| opentelemetry-instrumentation-rails | 0.34.1 |
| opentelemetry-instrumentation-mysql2 | 0.28.0 |

## Known Compatibility Notes

- **Logger gem**: Pinned to `1.4.3` (Ruby 3.0 default) because newer versions break
  `ActiveSupport::LoggerThreadSafeLevel` in Rails 6.1
- **Bundler**: Upgraded to 2.3.27 in Docker to handle default gem replacement correctly
- **Bootsnap**: Not included — latest version (1.23.0) is
  incompatible with Ruby 3.0

## Development

```bash
docker compose up --build     # Start all services
docker compose down            # Stop all services
docker compose down -v         # Stop and remove volumes
docker compose logs -f app     # Follow app logs
```

## Troubleshooting

### No traces appearing

```bash
docker compose logs otel-collector | grep "service.name"
docker compose logs app | grep "Instrumentation"
```

Verify the OTel instrumentations loaded successfully on app startup.

### Database connection refused

The app waits for MySQL healthcheck before starting. If issues persist:

```bash
docker compose logs mysql
docker compose down -v && docker compose up --build
```

## Resources

- [Rails Legacy Instrumentation Guide][rails-guide]
- [OpenTelemetry Ruby][otel-ruby]
- [Base14 Scout][scout]

[rails-guide]: https://docs.base14.io/instrument/apps/auto-instrumentation/rails-legacy#ruby-30--rails-61
[otel-ruby]: https://opentelemetry.io/docs/languages/ruby/
[scout]: https://base14.io/scout
