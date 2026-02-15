# Laravel 12 + PHP 8.5 + PostgreSQL + OpenTelemetry

Modern Laravel 12 application with automatic OpenTelemetry instrumentation for
distributed tracing, metrics, and logs. Demonstrates JWT authentication,
PostgreSQL integration, and Base14 Scout observability platform integration.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/laravel)

## Stack Profile

| Component | Version | EOL Status | Notes |
| --------- | ------- | ---------- | ----- |
| **PHP** | 8.5 | Active | Current stable |
| **Laravel** | 12.x | Active | Latest LTS |
| **PostgreSQL** | 18 | Active | Latest stable |
| **OpenTelemetry SDK** | 1.6+ | N/A | Current |

## What's Instrumented

### Automatic Instrumentation

- HTTP requests and responses (method, route, status)
- PostgreSQL database queries (Eloquent ORM)
- Redis connection and basic operations (get, set, delete, exists)
- Cache operations
- External HTTP calls (Guzzle/PSR-18)
- Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: All article operations (list, create, show, update, delete, favorite, unfavorite, feed)
- **Attributes**: `user.id`, `article.id`, `article.slug`, `db.operation`, `db.table`, `error.type`
- **Logs**: Structured JSON logs with trace correlation (`trace_id`, `span_id`)
- **Metrics**: Application counters (users, articles, comments)
- **Error Handling**: Centralized exception handler with span recording and error type classification

### Background Job Instrumentation

- Queue worker shares service name with web app for unified distributed tracing
- Web and worker distinguished via `service.instance.role` attribute (`web` or `worker`)
- Trace context propagation with span linking from HTTP request to background job
- Job attributes: `job.name`, `job.queue`, `job.attempt`, `job.parent_trace_id`
- Worker traces include nested SQL spans for database operations
- See `app/Jobs/ProcessArticleJob.php` for implementation

### Redis Instrumentation

> **Note**: Redis auto-instrumentation (`mismatch/opentelemetry-auto-redis`) covers connection and basic operations (GET, SET, DELETE, EXISTS, SCAN).
> Queue-specific operations (LPUSH, BRPOP, EVAL) used by Laravel's Redis queue driver are not instrumented.
> Queue job execution is still traced via Laravel's job instrumentation with `messaging.system=redis` attribute.

### Production Patterns

- **Atomic Counter Updates**: `favorites_count` uses database-level increment/decrement
- **Rate Limiting**: 60 req/min for API, 10 req/min for auth endpoints
- **Security Headers**: X-Content-Type-Options, X-Frame-Options, HSTS, etc.
- **Graceful Shutdown**: Telemetry flush on SIGTERM/SIGINT signals

## Technology Stack

| Component | Version | Purpose |
| --------- | ------- | ------- |
| Laravel | 12.x | Web framework |
| PHP | 8.5 | Runtime |
| PostgreSQL | 18 | Database |
| tymon/jwt-auth | 2.0 | JWT authentication |
| open-telemetry/sdk | 1.6+ | Telemetry SDK |
| open-telemetry/exporter-otlp | 1.3+ | OTLP exporter |
| open-telemetry/opentelemetry-auto-laravel | 1.2+ | Auto-instrumentation |
| mismatch/opentelemetry-auto-redis | 0.3+ | Redis auto-instrumentation |
| OTel Collector | 0.144.0 | Telemetry pipeline |

## Prerequisites

1. Docker & Docker Compose
2. Base14 Scout Account ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
3. PHP 8.5+ and Composer (for local development only)

## Quick Start

```bash
git clone https://github.com/base-14/examples.git
cd examples/php/php85-laravel12-postgres
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

### 3. Run Database Migrations

```bash
docker exec laravel-app php artisan migrate

# Or with seed data (3 users, 5 articles, 7 tags, 5 comments)
docker exec laravel-app php artisan migrate:fresh --seed
```

Seed credentials: `alice@example.com`, `bob@example.com`, `charlie@example.com`
(password: `password`)

### 4. Test the API

```bash
./scripts/test-api.sh
```

### 5. Verify Scout Integration

```bash
./scripts/verify-scout.sh
```

## Viewing Traces in Scout

1. **Login**: Navigate to `https://your-tenant.base14.io`
2. **Find Service**: Traces → Select `php-laravel12-postgres-otel`
3. **Explore**: Click any trace to see distributed view

Scout provides:

- Distributed trace visualization across all services
- Span attributes and events
- Correlated logs with trace IDs
- Performance metrics and anomaly detection

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
| `OTEL_SERVICE_NAME` | `php-laravel12-postgres-otel` | Service identifier |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Collector endpoint |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Export protocol |
| `OTEL_PHP_AUTOLOAD_ENABLED` | `true` | Enable auto-instrumentation |
| `DB_CONNECTION` | `pgsql` | Database driver |
| `JWT_SECRET` | - | JWT signing key |

### Resource Attributes

Automatically included in all telemetry:

```properties
service.name=php-laravel12-postgres-otel
telemetry.sdk.name=opentelemetry
telemetry.sdk.language=php
deployment.environment=development
```

## API Endpoints

### System Endpoints

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/api/health` | Health check (database, redis) | No |
| GET | `/api/metrics` | Prometheus-compatible metrics | No |

### Authentication

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/api/register` | User registration | No |
| POST | `/api/login` | User authentication | No |
| POST | `/api/logout` | User logout | Yes |
| GET | `/api/user` | Get current user | Yes |
| POST | `/api/refresh` | Refresh JWT token | Yes |

### Articles

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/api/articles` | List articles (paginated) | No |
| POST | `/api/articles` | Create article | Yes |
| GET | `/api/articles/{id}` | Get single article | No |
| PUT | `/api/articles/{id}` | Update article | Yes |
| DELETE | `/api/articles/{id}` | Delete article | Yes |
| GET | `/api/articles/feed` | Personalized feed | Yes |

### Social Features

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/api/articles/{id}/favorite` | Favorite article | Yes |
| DELETE | `/api/articles/{id}/favorite` | Unfavorite article | Yes |
| GET | `/api/articles/{id}/comments` | List comments | Yes |
| POST | `/api/articles/{id}/comments` | Add comment | Yes |
| DELETE | `/api/articles/{id}/comments/{cid}` | Delete comment | Yes |

### Tags

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/api/tags` | List all tags | No |

### Example Requests

```bash
# Health check
curl http://localhost:8000/api/health

# Register user
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Test User","email":"test@example.com","password":"password123"}'

# Login
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'

# Create article (with token)
curl -X POST http://localhost:8000/api/articles \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"My Article","description":"Short desc","body":"Content","tagList":["php","laravel"]}'

# Get metrics
curl http://localhost:8000/api/metrics
```

## Telemetry Data

### Traces

HTTP spans include:

- `http.method` - GET, POST, PUT, DELETE
- `http.route` - Route pattern (e.g., `/api/articles/{id}`)
- `http.status_code` - Response status
- `http.url` - Full request URL

Database spans include:

- `db.system` - `postgresql`
- `db.statement` - SQL query
- `db.operation` - SELECT, INSERT, UPDATE, DELETE

Custom business spans include:

- `user.id` - Authenticated user
- `article.id` - Article identifier
- `article.slug` - URL slug
- `service.instance.role` - `web` or `worker` (distinguishes app from queue worker)

### Logs

Structured JSON format with trace correlation:

```json
{
  "timestamp": "2025-01-15T10:30:45Z",
  "level": "info",
  "message": "Article created",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "user.id": "user-123",
  "article.id": "article-456"
}
```

### Metrics

Prometheus-compatible metrics at `/api/metrics`:

- `app_users_total` - Total registered users
- `app_articles_total` - Total articles
- `app_comments_total` - Total comments
- `app_database_up` - Database connection status
- `app_info` - Application version info

## OpenTelemetry Configuration

### Dependencies

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

### Custom Instrumentation Example

See `app/Http/Controllers/Api/ArticleController.php` for implementation:

```php
use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\StatusCode;

$tracer = Globals::tracerProvider()->getTracer('laravel-app');
$span = $tracer->spanBuilder('article.create')->startSpan();

try {
    $span->setAttribute('user.id', $user->id);
    $span->setAttribute('article.title', $request->title);

    $article = Article::create([...]);

    $span->setAttribute('article.id', $article->id);
    $span->setStatus(StatusCode::STATUS_OK);

    return $article;
} catch (\Exception $e) {
    $span->recordException($e);
    $span->setStatus(StatusCode::STATUS_ERROR, $e->getMessage());
    throw $e;
} finally {
    $span->end();
}
```

## Database Schema

```sql
-- Users
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    bio TEXT,
    image VARCHAR(255),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Articles
CREATE TABLE articles (
    id BIGSERIAL PRIMARY KEY,
    author_id BIGINT REFERENCES users(id),
    slug VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    body TEXT NOT NULL,
    favorites_count INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Tags (many-to-many with articles)
CREATE TABLE tags (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);

-- Favorites (many-to-many users <-> articles)
CREATE TABLE article_user (
    article_id BIGINT REFERENCES articles(id),
    user_id BIGINT REFERENCES users(id),
    PRIMARY KEY (article_id, user_id)
);
```

## Development

### Local Build

```bash
composer install
cp .env.example .env
php artisan key:generate
php artisan jwt:secret
php artisan migrate
php artisan serve
```

### Docker Commands

```bash
# Start services
docker compose up --build

# View logs
docker compose logs -f app
docker compose logs -f worker
docker compose logs -f otel-collector

# Laravel shell
docker exec -it laravel-app bash

# Database access
docker exec -it laravel-postgres psql -U laravel -d laravel

# Check queue jobs
docker exec laravel-app php artisan queue:monitor

# Stop services
docker compose down

# Stop and remove volumes
docker compose down -v
```

### Access Services

| Service | URL/Command | Purpose |
| ------- | ----------- | ------- |
| Application | <http://localhost:8000> | Laravel API |
| Queue Worker | `docker compose logs -f worker` | Background job processing |
| OTel Collector Health | <http://localhost:13133> | Collector status |
| Collector zPages | <http://localhost:55679/debug/tracez> | Trace debugging |

## Troubleshooting

### No traces appearing

1. Check collector logs: `docker compose logs otel-collector`
2. Verify Scout credentials are set correctly
3. Ensure `OTEL_PHP_AUTOLOAD_ENABLED=true`
4. Check OpenTelemetry extension: `php -m | grep opentelemetry`

### JWT "Unauthenticated" errors

1. Generate JWT secret: `docker exec laravel-app php artisan jwt:secret`
2. Always include header: `-H "Accept: application/json"`
3. Check token expiry (default: 60 minutes)

### Database connection errors

1. Verify containers are running: `docker compose ps`
2. Check migrations: `docker exec laravel-app php artisan migrate:status`
3. Test connection: `docker exec laravel-app php artisan tinker` then `DB::connection()->getPdo()`

### Collector authentication failed

1. Verify all Scout credentials are exported
2. Check token URL is accessible
3. Review collector logs for OAuth errors

## Resources

- [Laravel Auto-Instrumentation Guide](https://docs.base14.io/instrument/apps/auto-instrumentation/laravel)
- [OpenTelemetry PHP Documentation](https://opentelemetry.io/docs/languages/php/)
- [Base14 Scout Platform](https://base14.io/scout)
- [Base14 Documentation](https://docs.base14.io)
- [Laravel Documentation](https://laravel.com/docs)
