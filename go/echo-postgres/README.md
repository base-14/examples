# Go Echo + PostgreSQL + OpenTelemetry

A production-ready Go REST API demonstrating Echo framework with GORM ORM, Asynq background jobs, and comprehensive OpenTelemetry instrumentation with base14 Scout.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/go)

## Stack Profile

| Component | Version | EOL Status | Current Version |
|-----------|---------|------------|-----------------|
| **Go** | 1.24 | Feb 2026 | Latest stable |
| **Echo** | 4.15 | Active | Latest v4 |
| **GORM** | 1.31 | Active | ORM with auto-migrations |
| **PostgreSQL** | 18 | Nov 2029 | 18.1 |
| **Redis** | 8 | Active | 8.0 |
| **Asynq** | 0.25 | Active | Background job processing |
| **OpenTelemetry** | 1.39 | N/A | 1.39.0 |
| **zerolog** | 1.34 | Active | Structured logging |

**Why This Stack**: Demonstrates Go's performance with Echo framework, GORM ORM for type-safe database operations,
Asynq for reliable background jobs, and comprehensive OpenTelemetry instrumentation.

## Architecture Notes

### GORM Service Pattern

This example uses a **Service Layer with GORM ORM** pattern. Services interact directly with GORM models without an additional repository abstraction layer.

**Pattern Characteristics:**

- **Direct GORM Usage**: Services use GORM methods directly (`db.Create()`, `db.First()`, etc.)
- **Type-Safe ORM**: GORM provides compile-time type safety and migrations
- **Auto-Migrations**: Database schema managed via GORM's `AutoMigrate()`
- **Simpler Architecture**: Fewer layers, easier to understand for smaller applications

**Example:**

```go
// Service layer uses GORM directly
func (s *ArticleService) Create(ctx context.Context, article *models.Article) error {
    return s.db.WithContext(ctx).Create(article).Error
}
```

**Compared to Repository Pattern** (as seen in Go Fiber example):

- **Go Echo (GORM Pattern)**: Handler → Service → GORM → Database
- **Go Fiber (Repository Pattern)**: Handler → Service → Repository → raw SQL → Database

**When to Use Each:**

- **GORM Pattern (this example)**: Smaller teams, rapid development, ORM benefits outweigh control
- **Repository Pattern**: Need fine-grained SQL control, complex queries, or testing isolation

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (Echo middleware with `otelecho`)
- ✅ Database queries (GORM with `otelgorm` plugin)
- ✅ Redis operations (Asynq client/server)
- ✅ Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: Business spans for auth, CRUD, favorites, background jobs
- **Attributes**: User ID, article slug, job ID, operation metadata
- **Metrics**: HTTP metrics, auth attempts, article operations, job metrics
- **Logs**: Structured logs with trace correlation (traceId, spanId)

### Background Job Trace Propagation

Demonstrates end-to-end trace propagation through Asynq:

```text
HTTP POST /api/articles/:slug/favorite (parent span)
├── article.favorite (custom span)
│   └── gorm:query INSERT (auto-instrumented)
└── job.enqueue.notification (custom span)
    └── [async] job.notification (worker, linked via trace context)
```

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Go 1.24+** (for local development)

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/go/echo-postgres
```

### 2. Set base14 Scout Credentials

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

### 3. Start Services

```bash
docker compose up --build -d
```

This starts:

- Echo API on port 8080
- Asynq worker for background jobs
- PostgreSQL on port 5432
- Redis on port 6379
- OpenTelemetry Collector on ports 4317/4318

### 4. Verify Health

```bash
# Check application health
curl http://localhost:8080/api/health
```

Response:

```json
{
  "status": "healthy",
  "database": "healthy",
  "redis": "healthy"
}
```

### 5. Run API Tests

```bash
./scripts/test-api.sh
```

This script exercises all API endpoints and generates telemetry data.

### 6. View Traces

1. Log into your base14 Scout dashboard
2. Navigate to TraceX
3. Filter by service: `go-echo-postgres-api`
4. Look for the `article.favorite` trace to see job propagation

## API Endpoints

### Health

| Method | Endpoint      | Description                      | Auth |
| ------ | ------------- | -------------------------------- | ---- |
| `GET`  | `/api/health` | Health check (db, redis) | No   |

### Authentication

| Method | Endpoint        | Description               | Auth |
| ------ | --------------- | ------------------------- | ---- |
| `POST` | `/api/register` | Register new user         | No   |
| `POST` | `/api/login`    | Login and get JWT token   | No   |
| `GET`  | `/api/user`     | Get current user profile  | Yes  |
| `POST` | `/api/logout`   | Logout (stateless)        | Yes  |

### Articles

| Method   | Endpoint                     | Description                  | Auth        |
| -------- | ---------------------------- | ---------------------------- | ----------- |
| `GET`    | `/api/articles`              | List articles (paginated)    | Optional    |
| `POST`   | `/api/articles`              | Create article               | Yes         |
| `GET`    | `/api/articles/:slug`        | Get single article           | Optional    |
| `PUT`    | `/api/articles/:slug`        | Update article               | Yes (owner) |
| `DELETE` | `/api/articles/:slug`        | Delete article               | Yes (owner) |
| `POST`   | `/api/articles/:slug/favorite`   | Favorite article (async notification) | Yes |
| `DELETE` | `/api/articles/:slug/favorite`   | Unfavorite article       | Yes         |

## API Examples

### Register User

```bash
curl -X POST http://localhost:8080/api/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice", "password": "password123"}'
```

Response:

```json
{
  "user": {
    "id": 1,
    "email": "alice@example.com",
    "name": "Alice",
    "bio": "",
    "image": ""
  },
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### Create Article

```bash
curl -X POST http://localhost:8080/api/articles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "My Article", "body": "Article content here", "description": "A brief description"}'
```

Response:

```json
{
  "slug": "my-article",
  "title": "My Article",
  "description": "A brief description",
  "body": "Article content here",
  "author": {"id": 1, "email": "alice@example.com", "name": "Alice"},
  "favoritesCount": 0,
  "favorited": false,
  "createdAt": "2025-12-27T06:42:14Z"
}
```

## Error Response Format

All errors return a consistent format with trace IDs:

```json
{
  "error": "article not found",
  "trace_id": "abc123def456..."
}
```

Error messages include trace IDs for correlation with telemetry data.

## Configuration

### Required Environment Variables

| Variable              | Description                | Required |
| --------------------- | -------------------------- | -------- |
| `SCOUT_ENDPOINT`      | base14 Scout OTLP endpoint | Yes      |
| `SCOUT_CLIENT_ID`     | Scout OAuth2 client ID     | Yes      |
| `SCOUT_CLIENT_SECRET` | Scout OAuth2 client secret | Yes      |
| `SCOUT_TOKEN_URL`     | Scout OAuth2 token URL     | Yes      |

### Application Environment Variables

| Variable             | Description            | Default                 |
| -------------------- | ---------------------- | ----------------------- |
| `PORT`               | HTTP server port       | `8080`                  |
| `ENVIRONMENT`        | Environment name       | `development`           |
| `DATABASE_URL`       | PostgreSQL connection  | (required)              |
| `REDIS_URL`          | Redis connection       | `localhost:6379`        |
| `JWT_SECRET`         | JWT signing secret     | (required)              |
| `JWT_EXPIRES_IN`     | Token expiration       | `168h`                  |
| `OTEL_SERVICE_NAME`  | Service name in traces | `go-echo-postgres-api`  |
| `OTEL_EXPORTER_*`    | OTLP collector         | `http://localhost:4318` |

## Telemetry Data

### Traces

Distributed traces capture the full request lifecycle including background jobs:

```text
HTTP POST /api/articles/:slug/favorite (parent span)
├── article.favorite (custom span)
│   ├── gorm:query SELECT (find article)
│   ├── gorm:query SELECT (check existing favorite)
│   ├── gorm:query INSERT (create favorite)
│   └── gorm:query UPDATE (increment count)
└── job.enqueue.notification (custom span)
    └── [async] job.notification (worker, linked trace)
```

**Custom Spans:**

| Span Name                  | Description                          |
| -------------------------- | ------------------------------------ |
| `user.register`            | User registration                    |
| `user.login`               | User login                           |
| `article.create`           | Create article                       |
| `article.findAll`          | List articles                        |
| `article.findBySlug`       | Get single article                   |
| `article.update`           | Update article                       |
| `article.delete`           | Delete article                       |
| `article.favorite`         | Favorite article                     |
| `article.unfavorite`       | Unfavorite article                   |
| `job.enqueue.notification` | Enqueue background job               |
| `job.notification`         | Process notification job (worker)    |

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `http.server.request.total` | Counter | HTTP requests by method, route, status |
| `http.server.request.duration` | Histogram | Request latency in milliseconds |
| `http.server.active_requests` | Gauge | Current in-flight requests |
| `auth.registration.total` | Counter | User registrations |
| `auth.login.attempts` | Counter | Login attempts (success/failed) |
| `articles.created` | Counter | Articles created |
| `jobs.enqueued` | Counter | Jobs enqueued |
| `jobs.completed` | Counter | Jobs completed successfully |
| `jobs.failed` | Counter | Jobs failed |
| `jobs.duration_ms` | Histogram | Job processing time |

### Logs

All logs include trace context for correlation:

```json
{
  "level": "info",
  "traceId": "abc123def456...",
  "spanId": "789ghi...",
  "article_id": 1,
  "user_id": 42,
  "msg": "article created"
}
```

## Database Schema

### Users Table

| Column        | Type         | Description         |
| ------------- | ------------ | ------------------- |
| id            | SERIAL       | Primary key         |
| email         | VARCHAR(255) | Unique email        |
| password_hash | VARCHAR(255) | Hashed password     |
| name          | VARCHAR(255) | Display name        |
| bio           | TEXT         | User bio            |
| image         | VARCHAR(500) | Avatar URL          |
| created_at    | TIMESTAMP    | Creation time       |
| updated_at    | TIMESTAMP    | Last update         |

### Articles Table

| Column          | Type         | Description         |
| --------------- | ------------ | ------------------- |
| id              | SERIAL       | Primary key         |
| slug            | VARCHAR(255) | Unique URL slug     |
| title           | VARCHAR(255) | Article title       |
| description     | TEXT         | Brief description   |
| body            | TEXT         | Article content     |
| author_id       | INTEGER      | FK to users         |
| favorites_count | INTEGER      | Cached favorite cnt |
| created_at      | TIMESTAMP    | Creation time       |
| updated_at      | TIMESTAMP    | Last update         |

### Favorites Table

| Column     | Type      | Description         |
| ---------- | --------- | ------------------- |
| id         | SERIAL    | Primary key         |
| user_id    | INTEGER   | FK to users         |
| article_id | INTEGER   | FK to articles      |
| created_at | TIMESTAMP | Creation time       |

## Project Structure

```text
go-echo-postgres/
├── cmd/
│   ├── api/                      # API server entry point
│   │   └── main.go
│   └── worker/                   # Background worker entry point
│       └── main.go
├── config/
│   ├── config.go                 # Configuration management
│   └── otel-config.yaml          # OTel Collector config
├── internal/
│   ├── database/                 # Database setup
│   │   ├── database.go           # GORM initialization
│   │   └── migrations.go         # Auto-migrations
│   ├── handlers/                 # HTTP handlers (controllers)
│   │   ├── articles.go           # Article endpoints
│   │   ├── auth.go               # Auth endpoints
│   │   └── health.go             # Health check
│   ├── jobs/                     # Asynq background jobs
│   │   ├── client.go             # Job client (enqueue)
│   │   ├── server.go             # Job server (worker)
│   │   └── tasks/
│   │       └── notification.go   # Notification task
│   ├── logging/                  # Structured logging
│   │   └── logger.go             # zerolog setup
│   ├── middleware/               # Echo middleware
│   │   ├── auth.go               # JWT authentication
│   │   ├── error.go              # Error handling
│   │   └── metrics.go            # Metrics collection
│   ├── models/                   # GORM models
│   │   ├── user.go               # User model
│   │   ├── article.go            # Article model
│   │   └── favorite.go           # Favorite model
│   ├── services/                 # Business logic
│   │   ├── auth.go               # Auth service (uses GORM)
│   │   ├── user.go               # User service (uses GORM)
│   │   └── article.go            # Article service (uses GORM)
│   └── telemetry/                # OpenTelemetry setup
│       └── telemetry.go          # OTEL initialization
├── scripts/
│   └── test-api.sh               # API test script
├── compose.yml                   # Docker Compose
├── Dockerfile                    # API Dockerfile
├── Dockerfile.worker             # Worker Dockerfile
└── go.mod                        # Go dependencies
```

## Development

### Run Locally (without Docker)

```bash
# Start infrastructure
docker compose up postgres redis otel-collector -d

# Install dependencies
go mod download

# Run API server
export DATABASE_URL="postgres://postgres:postgres@localhost:5432/go_echo_app?sslmode=disable"
export REDIS_URL="localhost:6379"
export JWT_SECRET="development-secret"
export OTEL_SERVICE_NAME="go-echo-postgres-api"
go run ./cmd/api

# Run worker (separate terminal)
go run ./cmd/worker
```

### Build and Test

```bash
# Build binaries
go build -o api ./cmd/api
go build -o worker ./cmd/worker

# Run tests
go test ./...

# Run with race detector
go test -race ./...

# API integration tests
./scripts/test-api.sh
```

### Docker Commands

```bash
# Start all services
docker compose up --build -d

# View logs
docker compose logs -f api worker

# Stop services
docker compose down

# Clean up volumes
docker compose down -v
```

## Access Services

| Service        | URL                            | Purpose             |
| -------------- | ------------------------------ | ------------------- |
| Echo API       | <http://localhost:8080>        | Main application    |
| Health Check   | <http://localhost:8080/api/health> | Service health  |
| PostgreSQL     | `localhost:5432`               | Database            |
| Redis          | `localhost:6379`               | Job queue backend   |
| OTel Collector | <http://localhost:4318>        | Telemetry ingestion |
| OTel Health    | <http://localhost:13133>       | Collector health    |

## Troubleshooting

### Application won't start

```bash
# Check Go version
go version  # Should be 1.24+

# View application logs
docker compose logs api

# Check for port conflicts
lsof -i :8080
```

### Database connection errors

```bash
# Verify PostgreSQL is ready
docker compose exec postgres pg_isready -U postgres

# Check database exists
docker compose exec postgres psql -U postgres -l

# Test connection string
docker compose exec api env | grep DATABASE_URL
```

### Background jobs not processing

```bash
# Check worker logs
docker compose logs worker

# Verify Redis connection
docker compose exec redis redis-cli ping

# Check Asynq queue
docker compose exec redis redis-cli LLEN asynq:default
```

### No telemetry data in Scout

```bash
# Check collector health
curl http://localhost:13133/health

# View collector logs
docker compose logs otel-collector

# Verify OTEL configuration
docker compose exec api env | grep OTEL
```

### GORM migration issues

```bash
# Check migration logs
docker compose logs api | grep migration

# Manually run migrations (if needed)
docker compose exec api sh -c 'go run ./cmd/api --migrate-only'

# Drop and recreate database
docker compose down -v
docker compose up -d postgres
# Wait for postgres to be ready, then start api
docker compose up -d api
```

## View in Scout

After starting the application and generating some traffic:

1. Log in to [base14 Scout](https://app.base14.io)
2. Navigate to **Services** → **go-echo-postgres-api**
3. View distributed traces, metrics, and logs
4. Explore the service map to see API ↔ Worker communication
5. Look for traces showing job propagation

## Resources

- [Echo Framework Documentation](https://echo.labstack.com/)
- [GORM Documentation](https://gorm.io/docs/)
- [Asynq Documentation](https://github.com/hibiken/asynq)
- [OpenTelemetry Go](https://opentelemetry.io/docs/languages/go/)
- [base14 Scout Documentation](https://docs.base14.io)

