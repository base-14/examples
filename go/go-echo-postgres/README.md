# Go Echo + PostgreSQL + OpenTelemetry

A production-ready Go REST API example demonstrating full OpenTelemetry instrumentation with Echo framework, GORM, and Asynq background jobs.

## Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Go | 1.24 | Runtime |
| Echo | v4.13 | HTTP framework |
| GORM | v1.25 | ORM |
| PostgreSQL | 17 | Primary database |
| Redis | 7 | Job queue backend |
| Asynq | v0.25 | Background job processing |
| OpenTelemetry | v1.33 | Distributed tracing & metrics |
| zerolog | v1.33 | Structured logging |

## What's Instrumented

### Automatic Instrumentation
- **HTTP Requests**: All requests via `otelecho` middleware
- **Database**: PostgreSQL queries via `otelgorm`
- **Background Jobs**: Trace context propagation through Asynq

### Custom Spans
- `user.register`, `user.login` - Authentication operations
- `article.create`, `article.update`, `article.delete` - Article CRUD
- `article.favorite`, `article.unfavorite` - User interactions
- `job.enqueue.notification`, `job.notification` - Background job lifecycle

### Custom Metrics
- `http.server.request.total` - Request counter by method, route, status
- `http.server.request.duration` - Request latency histogram
- `http.server.active_requests` - Current in-flight requests
- `auth.registration.total` - User registrations
- `auth.login.attempts` - Login attempts
- `articles.created` - Articles created
- `jobs.enqueued`, `jobs.completed`, `jobs.failed` - Job lifecycle
- `jobs.duration_ms` - Job processing time

### Structured Logging
All logs include trace context (`traceId`, `spanId`) for correlation:
```json
{"level":"info","traceId":"abc123...","spanId":"def456...","article_id":1,"msg":"article created"}
```

## Quick Start

```bash
# Start all services
docker compose up -d

# Wait for healthy status
docker compose ps

# Run API tests
./scripts/test-api.sh

# View logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f otel-collector
```

## API Endpoints

### Authentication
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/register` | Create new user | - |
| POST | `/api/login` | Get JWT token | - |
| GET | `/api/user` | Get current user | Required |
| POST | `/api/logout` | Logout (stateless) | Required |

### Articles
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/articles` | List articles | Optional |
| POST | `/api/articles` | Create article | Required |
| GET | `/api/articles/:slug` | Get article | Optional |
| PUT | `/api/articles/:slug` | Update article | Owner |
| DELETE | `/api/articles/:slug` | Delete article | Owner |
| POST | `/api/articles/:slug/favorite` | Favorite article | Required |
| DELETE | `/api/articles/:slug/favorite` | Unfavorite article | Required |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check (db, redis) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | HTTP server port |
| `ENVIRONMENT` | `development` | Environment name |
| `DATABASE_URL` | - | PostgreSQL connection string |
| `REDIS_URL` | `localhost:6379` | Redis connection address |
| `JWT_SECRET` | - | JWT signing secret |
| `JWT_EXPIRES_IN` | `168h` | Token expiration duration |
| `OTEL_SERVICE_NAME` | `go-echo-postgres-api` | Service name for telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTel collector endpoint |

## Telemetry Data

### Traces
Traces flow from HTTP request through database and into background jobs:

```
HTTP POST /api/articles (parent span)
├── article.create (custom span)
│   └── gorm:query (auto-instrumented)
└── job.enqueue.notification (custom span)
    └── [async] job.notification (worker, linked trace)
```

### Error Responses
All error responses include `trace_id` for debugging:
```json
{
  "error": "article not found",
  "trace_id": "abc123def456..."
}
```

## Development

```bash
# Install dependencies
go mod download

# Run API locally
export DATABASE_URL="postgres://postgres:postgres@localhost:5432/goecho?sslmode=disable"
export REDIS_URL="localhost:6379"
export JWT_SECRET="development-secret"
go run ./cmd/api

# Run worker locally
go run ./cmd/worker

# Build binaries
go build -o api ./cmd/api
go build -o worker ./cmd/worker
```

## Project Structure

```
go-echo-postgres/
├── cmd/
│   ├── api/main.go           # API entry point
│   └── worker/main.go        # Worker entry point
├── config/
│   ├── config.go             # Configuration
│   └── otel-config.yaml      # OTel Collector config
├── internal/
│   ├── database/             # GORM setup & migrations
│   ├── handlers/             # HTTP handlers
│   ├── jobs/                 # Asynq client, server, tasks
│   ├── logging/              # Structured logging
│   ├── middleware/           # Auth, error, metrics
│   ├── models/               # GORM models
│   ├── services/             # Business logic
│   └── telemetry/            # OpenTelemetry setup
├── scripts/
│   └── test-api.sh           # API test script
├── compose.yml
├── Dockerfile
└── Dockerfile.worker
```

## Troubleshooting

### No traces in collector
1. Check collector is running: `docker compose logs otel-collector`
2. Verify endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT`
3. Check network connectivity between services

### Database connection failed
1. Ensure PostgreSQL is healthy: `docker compose ps postgres`
2. Verify `DATABASE_URL` format: `postgres://user:pass@host:5432/db?sslmode=disable`

### Jobs not processing
1. Check worker logs: `docker compose logs worker`
2. Verify Redis connection: `docker compose logs redis`
3. Ensure `REDIS_URL` is correct (host:port format, no protocol)

### Health check failing
Health endpoint returns detailed status:
```json
{
  "status": "healthy",
  "database": "healthy",
  "redis": "healthy"
}
```
