# Laravel 12 + PHP 8.5 + PostgreSQL 18 + OpenTelemetry

Laravel 12 example with automatic OpenTelemetry instrumentation. Demonstrates
distributed tracing, JWT authentication, and PostgreSQL integration with
Base14 Scout.

## Stack

- Laravel 12.39 + PHP 8.5 + PostgreSQL 18
- OpenTelemetry auto-instrumentation (no manual spans)
- JWT authentication (tymon/jwt-auth)
- Docker Compose setup with OTel Collector

## Dependencies

| Package                                   | Version |
| ----------------------------------------- | ------- |
| opentelemetry/sdk                         | ^1.6    |
| opentelemetry/exporter-otlp               | ^1.3    |
| opentelemetry/opentelemetry-auto-laravel  | ^1.2    |
| tymon/jwt-auth                            | ^2.0    |

## Quick Start

### 1. Set Environment Variables

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

### 2. Start Services

```bash
docker-compose up --build
```

### 3. Run Database Migrations

```bash
# Run migrations only
docker exec laravel-app php artisan migrate

# Or run migrations with seed data (3 users, 5 articles, 7 tags, 5 comments)
docker exec laravel-app php artisan migrate:fresh --seed
```

Seed credentials: `alice@example.com`, `bob@example.com`, `charlie@example.com`
(password: `password`)

### 4. Test the API

```bash
./scripts/test-api.sh
```

The test script registers users, creates articles, tests CRUD operations, and
verifies traces.

## API Endpoints

**Public:** `/api/register`, `/api/login`, `/api/articles`, `/api/tags`

**Protected (JWT):** Article CRUD, favorites, comments, user feed

See routes/api.php for full endpoint list.

## What Gets Traced

Automatic instrumentation captures:

- HTTP requests (method, route, status)
- PostgreSQL queries (operation, query text)
- Eloquent operations
- Errors with stack traces

Service name: `php-laravel12-postgres-otel`

View traces in Scout dashboard at your tenant URL.

## Development

```bash
# View logs
docker-compose logs -f app
docker-compose logs -f otel-collector

# Laravel shell
docker exec -it laravel-app bash

# Database access
docker exec -it laravel-postgres psql -U laravel -d laravel
```

## Troubleshooting

**JWT "Unauthenticated" errors:**

- Ensure JWT secret generated: `docker exec laravel-app php artisan jwt:secret`
- Always include: `-H "Accept: application/json"`

**No traces in Scout:**

- Check OTel logs: `docker logs otel-collector`
- Verify Scout credentials in environment

**Database issues:**

- Confirm containers running: `docker-compose ps`
- Check migrations: `docker exec laravel-app php artisan migrate:status`

## License

The Laravel framework is open-sourced software licensed under the [MIT license](https://opensource.org/licenses/MIT).
