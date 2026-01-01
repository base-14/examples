# Go Fiber + PostgreSQL + OpenTelemetry Example

A production-ready Go REST API using Fiber, sqlx, River job queue, and full OpenTelemetry instrumentation.

## Stack Profile

| Component | Version | Notes |
|-----------|---------|-------|
| Go | 1.24 | Latest stable |
| Fiber | v2.52+ | Express-inspired, fast HTTP framework |
| PostgreSQL | 17 | Primary database + job queue storage |
| sqlx | v1.4+ | Lightweight SQL toolkit (raw SQL) |
| River | v0.14+ | PostgreSQL-native job queue (no Redis!) |
| slog | stdlib | Go 1.21+ structured logging |
| OpenTelemetry | v1.33+ | Traces, metrics, trace-correlated logs |
| otelfiber | v2.1+ | Fiber OTel middleware |
| otelsql | v0.58+ | SQL query instrumentation |

### Key Differentiators from Go/Echo Example

| Aspect | Go/Echo | Go/Fiber (this example) |
|--------|---------|------------------------|
| Framework | Echo v4 | Fiber v2 |
| ORM/SQL | GORM (ORM) | sqlx (raw SQL) |
| Job Queue | Asynq (Redis) | River (PostgreSQL) |
| Logging | zerolog | slog (stdlib) |
| Redis | Required | **Not required** |

## Quick Start

```bash
# Start all services (API, Worker, PostgreSQL, OTel Collector)
docker compose up --build

# Run API tests (28 tests)
chmod +x scripts/test-api.sh
./scripts/test-api.sh
```

## API Endpoints

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/register | - | Register new user |
| POST | /api/login | - | Login, get JWT token |
| GET | /api/user | Required | Get current user |
| POST | /api/logout | Required | Logout |

### Articles

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/articles | Optional | List articles (paginated) |
| POST | /api/articles | Required | Create article |
| GET | /api/articles/:slug | Optional | Get single article |
| PUT | /api/articles/:slug | Required | Update article (owner only) |
| DELETE | /api/articles/:slug | Required | Delete article (owner only) |
| POST | /api/articles/:slug/favorite | Required | Favorite article |
| DELETE | /api/articles/:slug/favorite | Required | Unfavorite article |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Health check (database status) |

## Telemetry Data

### Traces

Auto-instrumented:
- HTTP requests via otelfiber middleware
- SQL queries via otelsql wrapper

Custom spans:
- `user.register`, `user.login`
- `article.create`, `article.update`, `article.delete`
- `article.favorite`, `article.unfavorite`
- `job.enqueue`, `job.notification`

### Metrics

- `articles.created` - Total articles created
- `articles.deleted` - Total articles deleted
- `favorites.added` - Total favorites added
- `favorites.removed` - Total favorites removed
- `jobs.enqueued` - Total jobs enqueued
- `jobs.completed` - Total jobs completed
- `jobs.failed` - Total jobs failed

### Logs

All logs include trace context:
```json
{
  "time": "2024-12-30T10:00:00Z",
  "level": "INFO",
  "msg": "article created",
  "service": "go-fiber-postgres-api",
  "traceId": "abc123...",
  "spanId": "def456...",
  "articleId": 1,
  "slug": "test-article"
}
```

## Project Structure

```
go-fiber-postgres/
├── cmd/
│   ├── api/main.go           # API server entry point
│   └── worker/main.go        # River worker entry point
├── config/
│   ├── config.go             # Configuration loader
│   └── otel-config.yaml      # OTel Collector config
├── internal/
│   ├── telemetry/            # OpenTelemetry SDK setup
│   ├── logging/              # slog with trace context
│   ├── database/             # sqlx + otelsql connection
│   ├── models/               # Data models
│   ├── repository/           # Repository pattern (sqlx)
│   ├── services/             # Business logic
│   ├── handlers/             # HTTP handlers
│   ├── middleware/           # Auth, error handling
│   └── jobs/                 # River job definitions
├── scripts/
│   └── test-api.sh           # API test script
├── Dockerfile                # API container
├── Dockerfile.worker         # Worker container
└── compose.yml               # Docker Compose (no Redis!)
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| PORT | 8080 | Server port |
| ENVIRONMENT | development | Environment name |
| DATABASE_URL | postgres://... | PostgreSQL connection string |
| JWT_SECRET | (change me) | JWT signing secret |
| JWT_EXPIRES_IN | 168h | JWT expiration |
| OTEL_SERVICE_NAME | go-fiber-postgres-api | Service name for telemetry |
| OTEL_EXPORTER_OTLP_ENDPOINT | http://localhost:4318 | OTLP endpoint |

## River Job Queue

River uses PostgreSQL as its backing store - no Redis required!

Jobs are automatically migrated when the worker starts. The worker:
- Processes `notification` jobs when articles are created
- Propagates trace context from API to worker (same trace ID)
- Records job metrics (enqueued, completed, failed)

## Development

```bash
# Local development (requires PostgreSQL running)
cp .env.example .env
go mod download
go run ./cmd/api

# In another terminal
go run ./cmd/worker
```

## Trace Context Propagation

When an article is created:
1. API creates a trace span for the HTTP request
2. API enqueues a River job with trace context
3. Worker extracts trace context and creates a child span
4. Both API and Worker spans share the same trace ID

This enables end-to-end distributed tracing across async boundaries.
