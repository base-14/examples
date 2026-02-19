# Slim 4 + PHP 8.4 + MongoDB + OpenTelemetry

Modern Slim 4 micro-framework with automatic HTTP span instrumentation via
`opentelemetry-auto-slim`, MongoDB, and PHP-FPM + Nginx. Demonstrates how to
add observability to PHP applications using Base14 Scout.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/slim)

## Stack Profile

| Component | Version | Status | Notes |
| --------- | ------- | ------ | ----- |
| **PHP** | 8.4 | Active | FPM SAPI |
| **Slim Framework** | 4.15 | Active | PSR-15 middleware, PHP-DI container |
| **MongoDB** | 8.x | Active | Document database |
| **OpenTelemetry SDK** | 1.13+ | N/A | Current |
| **opentelemetry-auto-slim** | 1.3+ | N/A | Auto HTTP span instrumentation |
| **Nginx** | alpine | Active | Reverse proxy to FPM |

## What's Instrumented

### Automatic (zero application code)

- **Traces**: HTTP requests via `opentelemetry-auto-slim` (root SERVER span with
  route pattern name, e.g. `GET /api/articles/{id}`) and MongoDB operations via
  `opentelemetry-auto-mongodb` (find, insertOne, updateOne, deleteOne)
- **HTTP metrics**: Request duration and count via `opentelemetry-auto-slim`

All auto-instrumented span attributes follow OTel semantic conventions and are
managed entirely by the official libraries. No manual duplication needed.

### Manual (minimal application code)

- **Exceptions on spans**: Error handler records exceptions on the active span
  and sets span status to ERROR (3 lines in `index.php`)
- **Log-trace correlation**: Monolog wired to OTel via the stock
  `opentelemetry-logger-monolog` handler — logs automatically carry
  `traceId` and `spanId`
- **Business metrics**: Application counters with `app.` namespace
  (`app.user.logins`, `app.article.creates`, etc.) via `Telemetry\Metrics`
- **Shutdown flush**: `Telemetry\Shutdown` ensures php-fpm flushes pending
  telemetry before process exit

### Span Hierarchy Example

```text
POST /api/articles           (SERVER   - auto-slim)
  +-- ArticleController::create (INTERNAL - auto-slim)
       +-- MongoDB articles.insert (CLIENT - auto-mongodb)
```

Auto-instrumentation creates all three levels. Controllers contain no
tracing code — just business logic, logging, and metric counters.

### OTel Semantic Convention Compliance

- Span status: UNSET for success (not OK), ERROR only for 5xx/exceptions
- Custom attributes namespaced with `app.` prefix
- Resource attribute: `deployment.environment.name` (not deprecated `deployment.environment`)
- No duplicate metrics or span attributes — auto-instrumentation handles these

### Slim 4 vs Slim 3

This example uses `opentelemetry-auto-slim` for automatic HTTP span
instrumentation, replacing the manual `TelemetryMiddleware` needed in
Slim 3. Slim 4 is clean on PHP 8.4 with no deprecation warnings. See
the `php84-slim3-mongodb` example for the legacy approach.

## Technology Stack

| Component | Version | Purpose |
| --------- | ------- | ------- |
| Slim Framework | ^4.15 | PSR-15 micro-framework |
| PHP | 8.4 | Runtime (FPM) |
| PHP-DI | ^7.1 | PSR-11 dependency injection |
| slim/psr7 | ^1.8 | PSR-7 implementation |
| MongoDB | 8.x | Document database |
| Nginx | alpine | Reverse proxy |
| firebase/php-jwt | ^7.0 | JWT authentication |
| open-telemetry/sdk | ^1.13 | Telemetry SDK |
| open-telemetry/exporter-otlp | ^1.4 | OTLP exporter |
| opentelemetry-auto-slim | ^1.3 | Slim 4 auto-instrumentation |
| opentelemetry-auto-mongodb | ^0.2 | MongoDB auto-instrumentation |
| opentelemetry-logger-monolog | ^1.1 | Log-trace correlation |
| OTel Collector | 0.144.0 | Telemetry pipeline |

## Prerequisites

1. Docker & Docker Compose
2. Base14 Scout Account ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))

## Quick Start

```bash
git clone https://github.com/base-14/examples.git
cd examples/php/php84-slim4-mongodb
```

### 1. Set Base14 Scout Credentials

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

### 2. Start Services

```bash
docker compose up --build
```

### 3. Test the API

```bash
./scripts/test-api.sh
```

### 4. Verify Scout Integration

```bash
./scripts/verify-scout.sh
```

## Viewing Traces in Scout

1. **Login**: Navigate to `https://your-tenant.base14.io`
2. **Find Service**: Traces -> Select `php-slim4-mongodb-otel`
3. **Explore**: Click any trace to see distributed view

## Configuration

### Required Environment Variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `SCOUT_ENDPOINT` | Yes | Base14 Scout OTLP endpoint |
| `SCOUT_CLIENT_ID` | Yes | OAuth2 client ID |
| `SCOUT_CLIENT_SECRET` | Yes | OAuth2 client secret |
| `SCOUT_TOKEN_URL` | Yes | OAuth2 token endpoint |

### Application Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `OTEL_SERVICE_NAME` | `php-slim4-mongodb-otel` | Service identifier |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Collector |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Export protocol |
| `OTEL_PHP_AUTOLOAD_ENABLED` | `true` | Enable auto-instrumentation |
| `OTEL_TRACES_EXPORTER` | `otlp` | Traces export format |
| `OTEL_METRICS_EXPORTER` | `otlp` | Metrics export format |
| `OTEL_LOGS_EXPORTER` | `otlp` | Logs export format |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment.name=development` | Resource attributes |
| `MONGO_URI` | `mongodb://mongo:27017` | MongoDB connection |
| `MONGO_DATABASE` | `slim_app` | Database name |
| `JWT_SECRET` | - | JWT signing key (required, fails fast if missing) |
| `APP_DEBUG` | `false` | Show error details in responses |

## API Endpoints

### System Endpoints

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/api/health` | Health check (MongoDB) | No |
| GET | `/api/metrics` | Prometheus-compatible metrics | No |

### Authentication

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/api/register` | User registration | No |
| POST | `/api/login` | User authentication | No |
| POST | `/api/logout` | User logout | Yes |
| GET | `/api/user` | Get current user | Yes |

### Articles

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/api/articles` | List articles (paginated) | No |
| POST | `/api/articles` | Create article | Yes |
| GET | `/api/articles/{id}` | Get single article | No |
| PUT | `/api/articles/{id}` | Update article | Yes |
| DELETE | `/api/articles/{id}` | Delete article | Yes |
| POST | `/api/articles/{id}/favorite` | Favorite article | Yes |
| DELETE | `/api/articles/{id}/favorite` | Unfavorite article | Yes |

### Example Requests

```bash
# Health check
curl http://localhost:8080/api/health

# Register user
curl -X POST http://localhost:8080/api/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","email":"test@example.com","password":"password123"}'

# Login
curl -X POST http://localhost:8080/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'

# Create article (with token)
curl -X POST http://localhost:8080/api/articles \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"My Article","description":"Short desc","body":"Content","tagList":["php","slim"]}'
```

## Docker Architecture

```text
Client :8080 --> nginx:alpine --> php:8.4-fpm (app)
                                      |
                                      +-- OTLP :4318 --> otel-collector
                                      |                      |
                                      |                      +-- Scout
                                      |
                                      +-- mongodb:27017 --> mongo:8
```

## Development

### Docker Commands

```bash
# Start services
docker compose up --build

# View logs
docker compose logs -f app
docker compose logs -f nginx
docker compose logs -f otel-collector

# Shell into app container
docker exec -it slim4-app bash

# MongoDB shell
docker exec -it slim4-mongo mongosh

# Stop services
docker compose down

# Stop and remove volumes
docker compose down -v
```

### Access Services

| Service | URL | Purpose |
| ------- | --- | ------- |
| Application | <http://localhost:8080> | Slim 4 API (via Nginx) |
| OTel Collector Health | <http://localhost:13133> | Collector status |
| Collector zPages | <http://localhost:55679/debug/tracez> | Trace debugging |

## Troubleshooting

### No traces appearing

1. Check collector logs: `docker compose logs otel-collector`
2. Verify Scout credentials are set correctly
3. Ensure `OTEL_PHP_AUTOLOAD_ENABLED=true`
4. Check OpenTelemetry extension: `docker exec slim4-app php -m | grep opentelemetry`

### JWT "Token required" errors

1. Include `Authorization: Bearer <token>` header
2. Check token expiry (default: 1 hour)
3. Verify JWT_SECRET matches between token generation and validation

### MongoDB connection errors

1. Verify containers are running: `docker compose ps`
2. Check MongoDB health: `docker exec slim4-mongo mongosh --eval "db.adminCommand('ping')"`
3. Verify MONGO_URI is correct

### Collector authentication failed

1. Verify all Scout credentials are exported
2. Check token URL is accessible
3. Review collector logs for OAuth errors

## Resources

- [OpenTelemetry PHP Documentation](https://opentelemetry.io/docs/languages/php/)
- [Base14 Scout Platform](https://base14.io/scout)
- [Base14 Documentation](https://docs.base14.io)
- [Slim 4 Documentation](https://www.slimframework.com/docs/v4/)
- [MongoDB PHP Library](https://www.mongodb.com/docs/php-library/)
