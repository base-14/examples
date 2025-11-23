# Laravel with OpenTelemetry

Laravel 8.x application with OpenTelemetry auto-instrumentation for traces,
metrics, and logs.

> ⚠️ **Security Notice**: This project uses Laravel 8.x (EOL July 2023) and
> contains [19+ known security vulnerabilities](./SECURITY.md).
> **Not recommended for production use.** For production, upgrade to Laravel 11+.
>
> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/laravel)

## What's Instrumented

- HTTP requests and responses
- Database queries (Eloquent ORM)
- Cache operations and queue jobs
- External HTTP calls (Guzzle)
- Distributed trace propagation (W3C)

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Base14 Scout OIDC credentials ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
- PHP 7.3+ and Composer (only for local development without Docker)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/laravel/php8-laravel8-sqlite

# Set Base14 Scout credentials as environment variables
export SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token

# Start application (Laravel + OTel Collector)
docker-compose up --build

# Verify it's running
curl http://localhost:8000/api/articles
```

The app runs on port `8000`, OTel Collector on `4317/4318`.

## Configuration

### Required Environment Variables

The OpenTelemetry Collector requires Base14 Scout credentials to export
telemetry data. Set these before running `docker-compose up`:

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `SCOUT_ENDPOINT` | Yes | Base14 Scout OTLP endpoint |
| `SCOUT_CLIENT_ID` | Yes | OAuth2 client ID from Base14 Scout |
| `SCOUT_CLIENT_SECRET` | Yes | OAuth2 client secret from Base14 Scout |
| `SCOUT_TOKEN_URL` | Yes | OAuth2 token endpoint |

**Example:**

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

See the
[Base14 Collector Setup Guide](https://docs.base14.io/category/opentelemetry-collector-setup)
for obtaining credentials.

### Application Environment Variables (docker-compose.yml)

| Variable | Default |
| -------- | ------- |
| `OTEL_SERVICE_NAME` | `php-laravel8-sqlite-otel` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` |
| `OTEL_TRACES_EXPORTER` | `otlp` |
| `OTEL_METRICS_EXPORTER` | `otlp` |
| `OTEL_LOGS_EXPORTER` | `otlp` |
| `OTEL_PHP_AUTOLOAD_ENABLED` | `true` |

### Resource Attributes

Automatically included in telemetry:

```properties
service.name=php-laravel8-sqlite-otel
telemetry.sdk.name=opentelemetry
telemetry.sdk.language=php
```

## OpenTelemetry Setup

Laravel auto-instrumentation is configured through the following components:

### 1. Dependencies (composer.json)

The required OpenTelemetry packages are already included:

```json
{
  "require": {
    "open-telemetry/sdk": "^1.6",
    "open-telemetry/exporter-otlp": "^1.3",
    "open-telemetry/opentelemetry-auto-laravel": "^1.2",
    "open-telemetry/opentelemetry-auto-psr18": "^1.1"
  }
}
```

### 2. Collector Configuration (config/otel-config.yml)

The OpenTelemetry Collector handles:

- OIDC authentication with Base14 Scout
- Receiving telemetry from the Laravel app (OTLP)
- Exporting to Scout with retry and compression

### 3. Auto-Instrumentation

Enabled via environment variables in `docker-compose.yml`. The Laravel app
automatically instruments HTTP requests, database queries, and external calls
without code changes.

## API Endpoints

The application provides a RESTful API for articles, users, and comments:

### Public Endpoints

```bash
# List articles
GET /api/articles

# Get article feed
GET /api/articles/feed

# Get single article
GET /api/articles/{slug}

# Get article comments
GET /api/articles/{slug}/comments

# Get user profile
GET /api/profiles/{username}

# List tags
GET /api/tags

# User registration
POST /api/users

# User login
POST /api/users/login
```

### Authenticated Endpoints

```bash
# Get current user
GET /api/user

# Update current user
PUT /api/user

# Create article
POST /api/articles

# Update article
PUT /api/articles/{slug}

# Delete article
DELETE /api/articles/{slug}

# Favorite article
POST /api/articles/{slug}/favorite

# Unfavorite article
DELETE /api/articles/{slug}/favorite

# Add comment
POST /api/articles/{slug}/comments

# Delete comment
DELETE /api/articles/{slug}/comments/{id}

# Follow user
POST /api/profiles/{username}/follow

# Unfollow user
DELETE /api/profiles/{username}/follow
```

## Development

### Run Locally (without Docker)

```bash
composer install          # Install dependencies
cp .env.example .env      # Create environment file
php artisan key:generate  # Generate application key
php artisan migrate       # Run database migrations
php artisan serve         # Run application
```

Set required environment variables before running locally.

### Docker Commands

```bash
docker-compose up --build        # Build and start
docker-compose down              # Stop all
docker-compose down -v           # Stop and remove volumes
docker-compose logs -f app       # View logs
```

## Telemetry Data

### Traces

- HTTP requests (method, URL, status, controller/action)
- Database queries (SQL statements, duration)
- Cache operations and queue jobs
- External HTTP calls (Guzzle)
- Exceptions with stack traces

### Metrics

- Request count and duration
- Database query performance
- Cache hit/miss rates
- Queue job processing times

### Logs

Application logs are automatically exported to Scout with trace correlation.
Each log entry includes `trace_id` and `span_id` for correlation with traces.

## Troubleshooting

### Authentication failed

```bash
docker-compose logs app | grep -i "token\|auth"
```

Verify Scout credentials are correct and token URL is accessible.

### No telemetry data

```bash
docker-compose logs app | grep -i opentelemetry
```

Check that:

- Scout endpoint is reachable
- OIDC token is being fetched successfully
- `OTEL_PHP_AUTOLOAD_ENABLED=true` is set
- OpenTelemetry packages are installed

### Enable debug logging

In `.env`:

```bash
LOG_LEVEL=debug
```

Or in `docker-compose.yml`:

```yaml
environment:
  - LOG_LEVEL=debug
  - OTEL_LOG_LEVEL=debug
```

### Database errors

```bash
# Reset database
php artisan migrate:fresh

# Check database connection
php artisan tinker
>>> DB::connection()->getPdo();
```

## Technology Stack

| Component | Version | Notes |
| --------- | ------- | ----- |
| Laravel | 8.83 (dev) | ⚠️ EOL - See [SECURITY.md](./SECURITY.md) |
| PHP | 8.1 | ✅ Supported |
| OpenTelemetry SDK | 1.6+ | ✅ Current |
| OpenTelemetry Auto-Laravel | 1.2+ | ✅ Current |
| SQLite | 3.x | ✅ Supported |
| JWT Auth | 1.0+ | ⚠️ Development version |

## Resources

- [Laravel Auto-Instrumentation Guide](https://docs.base14.io/instrument/apps/auto-instrumentation/laravel)
  \- Base14 documentation
- [OpenTelemetry PHP](https://opentelemetry.io/docs/languages/php/) -
  OTel PHP docs
- [Base14 Scout](https://base14.io/scout) - Observability platform
