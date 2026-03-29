# Symfony 8 + PHP 8.5 + MySQL + OpenTelemetry

Symfony 8.0 articles API with MySQL and a notification microservice,
demonstrating distributed tracing, trace-log correlation, structured
logging, and custom metrics via OpenTelemetry. Exports to
[Base14 Scout][scout] observability platform.

## Stack Profile

| Component | Version | EOL Status | Notes |
| --------- | ------- | ---------- | ----- |
| **PHP** | 8.5 | Dec 2029 | Current stable |
| **Symfony** | 8.0 | Jul 2026 | Latest major |
| **Doctrine ORM** | 3.6 | Active | Attribute mapping |
| **MySQL** | 8.4 | Apr 2032 | LTS |
| **OpenTelemetry SDK** | 1.14 | Active | Current stable |
| **OTel Collector** | 0.148.0 | Active | Contrib distribution |

## Architecture

```
┌──────────────┐    POST /notify    ┌──────────────┐
│              │ ──────────────────> │              │
│  app (8080)  │   W3C traceparent  │ notify (8081)│
│  Symfony 8   │                    │  PHP CLI     │
└──────┬───┬───┘                    └──────┬───────┘
       │   │                               │
       │   │ OTLP/HTTP                     │ OTLP/HTTP
       │   │                               │
       │   └──────────┐   ┌───────────────┘
       │ Doctrine/PDO │   │
       ▼              ▼   ▼
┌──────────────┐  ┌──────────────────────────┐
│  db (3306)   │  │  otel-collector (4318)   │ ──> Scout / stdout
│  MySQL 8.4   │  │  OTel Collector contrib  │
└──────────────┘  └──────────────────────────┘
```

On `POST /api/articles`, the app creates an article in MySQL, then calls
the notify service via HTTP. The W3C `traceparent` header propagates trace
context, producing a single distributed trace spanning both services.

## What's Instrumented

### Automatic Instrumentation

- HTTP server spans (Symfony request lifecycle)
- HTTP client spans (app → notify, W3C trace propagation)
- Database spans (PDO/MySQL queries via Doctrine)
- Log correlation (PSR-3/Monolog trace context injection)

### Custom Instrumentation

- **Traces**: Notification service creates child spans from propagated context
- **Logs**: Structured JSON with `trace_id`, `span_id`, `service.name` in every line
- **Metrics**: `articles.created` counter via OTel Meter API
- **Error Handling**: Exception listener logs at ERROR level with trace context, returns JSON

### Log Levels

| Level | Condition |
| ----- | --------- |
| INFO | Article created, notification sent, article retrieved, listing articles |
| WARNING | 404 not found, validation failure, notification failure |
| ERROR | Unhandled exception (e.g., database down) |

## Technology Stack

| Component | Version | Purpose |
| --------- | ------- | ------- |
| Symfony | 8.0 | Web framework |
| PHP | 8.5 | Runtime |
| MySQL | 8.4 | Database |
| Doctrine ORM | 3.6 | Object-relational mapping |
| Doctrine DBAL | 4.4 | Database abstraction |
| Monolog | 3.10 | Structured logging |
| open-telemetry/sdk | 1.14 | Telemetry SDK |
| open-telemetry/exporter-otlp | 1.4 | OTLP exporter |
| open-telemetry/opentelemetry-auto-symfony | 1.2 | Symfony auto-instrumentation |
| open-telemetry/opentelemetry-auto-pdo | 0.4 | PDO auto-instrumentation |
| open-telemetry/opentelemetry-auto-psr18 | 1.2 | HTTP client auto-instrumentation |
| open-telemetry/opentelemetry-auto-psr3 | 0.2 | Log correlation |
| ext-opentelemetry (PECL) | 1.2.1 | PHP extension for auto-instrumentation |
| OTel Collector contrib | 0.148.0 | Telemetry pipeline |

## Prerequisites

1. Docker and Docker Compose
2. No other services on ports 8080, 8081, 3306, 4317, 4318

## Quick Start

```bash
cd php/symfony-mysql

# Copy environment file
cp .env.example .env

# Build and start
docker compose build
docker compose up -d

# Wait for services (~30s for app + migration)
sleep 30

# Test health
curl http://localhost:8080/api/health

# Run full test suite
./scripts/test-api.sh
```

### Verify Scout Export

```bash
# Set Scout credentials in environment, then:
./scripts/verify-scout.sh
```

## API Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/articles` | List articles (paginated) |
| `GET` | `/api/articles/{id}` | Get article by ID |
| `POST` | `/api/articles` | Create article + notify |
| `PUT` | `/api/articles/{id}` | Update article |
| `DELETE` | `/api/articles/{id}` | Delete article |

### Create Article

```bash
curl -X POST http://localhost:8080/api/articles \
  -H 'Content-Type: application/json' \
  -d '{"title":"Hello","body":"World"}'
```

Response:

```json
{
  "data": {
    "id": 1,
    "title": "Hello",
    "body": "World",
    "created_at": "2026-03-29T00:00:00+00:00",
    "updated_at": "2026-03-29T00:00:00+00:00"
  },
  "meta": { "trace_id": "abc123..." }
}
```

### List Articles (paginated)

```bash
curl 'http://localhost:8080/api/articles?page=1&per_page=10'
```

## Environment Variables

### Application

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `APP_PORT` | `8080` | App port |
| `APP_SECRET` | — | Symfony secret |
| `NOTIFY_PORT` | `8081` | Notify service port |
| `NOTIFY_URL` | `http://notify:8081` | Internal notify endpoint |
| `DATABASE_URL` | `mysql://symfony:secret@db:3306/symfony` | MySQL connection |

### OpenTelemetry

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `OTEL_SERVICE_NAME` | `symfony-articles` | Service name for traces/metrics |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Collector HTTP endpoint |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Transport protocol |
| `OTEL_PHP_AUTOLOAD_ENABLED` | `true` | Enable auto-instrumentation |
| `OTEL_PHP_PSR3_MODE` | `export` | Export logs to collector via OTLP (`inject` only adds trace context) |

### Scout (optional)

| Variable | Description |
| -------- | ----------- |
| `SCOUT_ENDPOINT` | Scout OTLP endpoint |
| `SCOUT_CLIENT_ID` | OAuth2 client ID |
| `SCOUT_CLIENT_SECRET` | OAuth2 client secret |
| `SCOUT_TOKEN_URL` | OAuth2 token URL |

## Observability Signals

### Traces

View in collector stdout (`docker compose logs otel-collector`):

- HTTP server spans from Symfony auto-instrumentation
- Database spans (`PDO::prepare`, `PDOStatement::execute`, etc.)
- HTTP client spans (app → notify with W3C traceparent)
- Notify service child spans (`POST /notify`)
- Single distributed trace spanning both services on article creation

### Logs

Exported to collector via OTLP (`OTEL_PHP_PSR3_MODE=export`) and also
written to stdout as structured JSON (`docker compose logs app`):

- Every log record includes `trace_id` and `span_id` for trace-log correlation
- INFO: article created, notification sent, article retrieved, listing
- WARNING: 404 not found, validation failure, notification failure
- ERROR: unhandled exceptions with full trace context
- View in collector: `docker compose logs otel-collector | grep "Body: Str"`

### Metrics

View in collector stdout (`docker compose logs otel-collector | grep articles.created`):

- `articles.created` — monotonic counter incremented on each successful creation

## Troubleshooting

**Port conflict**: Stop other OTel stacks first — they share ports 4317/4318.

```bash
docker ps --format '{{.Names}} {{.Ports}}' | grep 4317
```

**App not starting**: Check logs for Symfony configuration errors:

```bash
docker compose logs app
```

**Migration not run**: Runs automatically on compose up. To run manually:

```bash
docker compose exec app php bin/console doctrine:migrations:migrate --no-interaction
```

**Collector export errors**: If using Scout, check credentials are set:

```bash
docker compose logs otel-collector | grep -i "failed\|401\|403"
```

[scout]: https://base14.io/scout
