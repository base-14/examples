# Go Fiber + PostgreSQL + OpenTelemetry

A production-ready Go REST API demonstrating Fiber framework with Repository pattern, raw SQL via sqlx,
River job queue (PostgreSQL-native), and comprehensive OpenTelemetry instrumentation with base14 Scout.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/go)

## Stack Profile

| Component | Version | EOL Status | Current Version |
|-----------|---------|------------|-----------------|
| **Go** | 1.24.13 | Feb 2026 | Latest stable |
| **Fiber** | 2.52 | Active | Express-inspired web framework |
| **PostgreSQL** | 18 | Nov 2029 | 18.1 (database + job queue) |
| **sqlx** | 1.4 | Active | Lightweight SQL toolkit |
| **River** | 0.30 | Active | PostgreSQL-native job queue |
| **slog** | stdlib | N/A | Go 1.21+ structured logging |
| **OpenTelemetry** | 1.39 | N/A | 1.39.0 |

**Why This Stack**: Demonstrates Go's performance with Fiber framework, Repository pattern for testability,
raw SQL control via sqlx, and River for reliable background jobs **without Redis dependency**.

## Architecture Notes

### Repository Pattern with Raw SQL

This example uses a **Repository Pattern with sqlx** for direct SQL control and testing isolation.

**Pattern Characteristics:**

- **Repository Layer**: Abstracts all database operations into repository interfaces
- **Raw SQL**: Uses `sqlx` for manual query writing and fine-grained control
- **Testability**: Repositories can be easily mocked for unit testing
- **SQL-First**: Direct control over queries, indexes, and optimization

**Example:**

```go
// Repository interface defines data operations
type ArticleRepository interface {
    Create(ctx context.Context, article *models.Article) error
    FindBySlug(ctx context.Context, slug string) (*models.Article, error)
    Update(ctx context.Context, article *models.Article) error
    Delete(ctx context.Context, id int64) error
}

// Implementation uses raw SQL with sqlx
func (r *articleRepository) Create(ctx context.Context, article *models.Article) error {
    query := `INSERT INTO articles (slug, title, description, body, author_id)
              VALUES ($1, $2, $3, $4, $5) RETURNING id, created_at`
    return r.db.QueryRowxContext(ctx, query,
        article.Slug, article.Title, article.Description,
        article.Body, article.AuthorID).Scan(&article.ID, &article.CreatedAt)
}
```

**Architecture Flow:**

```text
Handler → Service → Repository → sqlx → PostgreSQL
```

**Compared to GORM Pattern** (as seen in Go Echo example):

- **Go Fiber (Repository Pattern)**: Handler → Service → Repository → raw SQL → Database
- **Go Echo (GORM Pattern)**: Handler → Service → GORM ORM → Database

**When to Use Each:**

- **Repository Pattern (this example)**: Need SQL control, complex queries, testing isolation, performance optimization
- **GORM Pattern**: Rapid development, simpler CRUD, ORM benefits outweigh SQL control

### River: PostgreSQL-Native Job Queue

Unlike other examples using Redis-backed queues (BullMQ, Asynq), River uses **PostgreSQL as job storage**:

**Benefits:**

- **No Redis Required**: Simplifies infrastructure
- **Transactional Jobs**: Enqueue jobs in same transaction as data changes
- **PostgreSQL Features**: Leverage existing backups, replication, monitoring
- **Durability**: Jobs persisted in battle-tested PostgreSQL

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (Fiber middleware with `otelfiber`)
- ✅ SQL queries (sqlx with `otelsql` wrapper)
- ✅ PostgreSQL operations (River job queue)
- ✅ Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: Business spans for auth, CRUD, favorites, background jobs
- **Attributes**: User ID, article slug, job ID, SQL query metadata
- **Metrics**: HTTP metrics, article operations, favorites, job metrics
- **Logs**: Structured logs with trace correlation (traceId, spanId)

### Background Job Trace Propagation

Demonstrates end-to-end trace propagation through River:

```text
HTTP POST /api/articles (parent span)
├── article.create (custom span)
│   └── sql:INSERT INTO articles (auto-instrumented)
└── job.enqueue.notification (custom span)
    └── [async] job.notification (worker, linked via trace context)
```

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Go 1.24.13+** (for local development)

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/go/fiber-postgres
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

- Fiber API on port 8080
- River worker for background jobs
- PostgreSQL on port 5432 (database + job queue)
- OpenTelemetry Collector on ports 4317/4318

**Note:** No Redis required!

### 4. Verify Health

```bash
# Check application health
curl http://localhost:8080/api/health
```

Response:

```json
{
  "status": "healthy",
  "database": "healthy"
}
```

### 5. Run API Tests

```bash
chmod +x scripts/test-api.sh
./scripts/test-api.sh
```

This script exercises all API endpoints and generates telemetry data.

### 6. View Traces

1. Log into your base14 Scout dashboard
2. Navigate to TraceX
3. Filter by service: `go-fiber-postgres-api`
4. Look for traces showing River job propagation

## API Endpoints

### Health

| Method | Endpoint      | Description          | Auth |
| ------ | ------------- | -------------------- | ---- |
| `GET`  | `/api/health` | Health check (db)    | No   |

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
| `POST`   | `/api/articles`              | Create article (async notification) | Yes  |
| `GET`    | `/api/articles/:slug`        | Get single article           | Optional    |
| `PUT`    | `/api/articles/:slug`        | Update article               | Yes (owner) |
| `DELETE` | `/api/articles/:slug`        | Delete article               | Yes (owner) |
| `POST`   | `/api/articles/:slug/favorite`   | Favorite article         | Yes         |
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
| `JWT_SECRET`         | JWT signing secret     | (required)              |
| `JWT_EXPIRES_IN`     | Token expiration       | `168h`                  |
| `OTEL_SERVICE_NAME`  | Service name in traces | `go-fiber-postgres-api` |
| `OTEL_EXPORTER_*`    | OTLP collector         | `http://localhost:4318` |

## Telemetry Data

### Traces

Distributed traces capture the full request lifecycle including background jobs:

```text
HTTP POST /api/articles (parent span)
├── article.create (custom span)
│   ├── sql:INSERT INTO articles
│   ├── sql:RETURNING id
│   └── job.enqueue (custom span)
└── [async] job.notification (worker, linked trace)
    └── sql:SELECT article data
```

**Custom Spans:**

| Span Name           | Description                          |
| ------------------- | ------------------------------------ |
| `user.register`     | User registration                    |
| `user.login`        | User login                           |
| `article.create`    | Create article                       |
| `article.findAll`   | List articles                        |
| `article.findBySlug`| Get single article                   |
| `article.update`    | Update article                       |
| `article.delete`    | Delete article                       |
| `article.favorite`  | Favorite article                     |
| `article.unfavorite`| Unfavorite article                   |
| `job.enqueue`       | Enqueue River job                    |
| `job.notification`  | Process notification job (worker)    |

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `http.server.request.total` | Counter | HTTP requests by method, route, status |
| `http.server.request.duration` | Histogram | Request latency in milliseconds |
| `articles.created` | Counter | Articles created |
| `articles.deleted` | Counter | Articles deleted |
| `favorites.added` | Counter | Favorites added |
| `favorites.removed` | Counter | Favorites removed |
| `jobs.enqueued` | Counter | Jobs enqueued to River |
| `jobs.completed` | Counter | Jobs completed successfully |
| `jobs.failed` | Counter | Jobs failed |

### Logs

All logs include trace context for correlation:

```json
{
  "time": "2025-12-27T10:00:00Z",
  "level": "INFO",
  "msg": "article created",
  "service": "go-fiber-postgres-api",
  "traceId": "abc123def456...",
  "spanId": "789ghi...",
  "articleId": 1,
  "slug": "test-article"
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

### River Tables (Auto-created)

River creates its own tables for job management:

- `river_job` - Job queue storage
- `river_queue` - Queue metadata
- `river_leader` - Leadership election
- `river_migration` - Schema versioning

## Project Structure

```text
go-fiber-postgres/
├── cmd/
│   ├── api/                      # API server entry point
│   │   └── main.go
│   └── worker/                   # River worker entry point
│       └── main.go
├── config/
│   ├── config.go                 # Configuration management
│   └── otel-config.yaml          # OTel Collector config
├── internal/
│   ├── database/                 # Database setup
│   │   ├── database.go           # sqlx initialization
│   │   └── migrations.go         # SQL migrations
│   ├── handlers/                 # HTTP handlers (controllers)
│   │   ├── articles.go           # Article endpoints
│   │   ├── auth.go               # Auth endpoints
│   │   └── health.go             # Health check
│   ├── jobs/                     # River background jobs
│   │   ├── client.go             # Job client (enqueue)
│   │   ├── worker.go             # Job worker
│   │   └── notification.go       # Notification job
│   ├── logging/                  # Structured logging
│   │   └── logger.go             # slog setup
│   ├── middleware/               # Fiber middleware
│   │   ├── auth.go               # JWT authentication
│   │   ├── error.go              # Error handling
│   │   └── metrics.go            # Metrics collection
│   ├── models/                   # Data models
│   │   ├── user.go               # User model
│   │   ├── article.go            # Article model
│   │   └── favorite.go           # Favorite model
│   ├── repository/               # Repository layer (sqlx)
│   │   ├── user.go               # User repository
│   │   ├── article.go            # Article repository
│   │   └── favorite.go           # Favorite repository
│   ├── services/                 # Business logic
│   │   ├── auth.go               # Auth service (uses repos)
│   │   └── article.go            # Article service (uses repos)
│   └── telemetry/                # OpenTelemetry setup
│       └── telemetry.go          # OTEL initialization
├── scripts/
│   └── test-api.sh               # API test script
├── compose.yml                   # Docker Compose (no Redis!)
├── Dockerfile                    # API Dockerfile
├── Dockerfile.worker             # Worker Dockerfile
└── go.mod                        # Go dependencies
```

## Development

### Run Locally (without Docker)

```bash
# Start infrastructure
docker compose up postgres otel-collector -d

# Install dependencies
go mod download

# Run API server
export DATABASE_URL="postgres://postgres:postgres@localhost:5432/go_fiber_app?sslmode=disable"
export JWT_SECRET="development-secret"
export OTEL_SERVICE_NAME="go-fiber-postgres-api"
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
| Fiber API      | <http://localhost:8080>        | Main application    |
| Health Check   | <http://localhost:8080/api/health> | Service health  |
| PostgreSQL     | `localhost:5432`               | Database + job queue|
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

# Check River job tables
docker compose exec postgres psql -U postgres go_fiber_app -c "SELECT * FROM river_job LIMIT 10;"

# Check job queue status
docker compose exec postgres psql -U postgres go_fiber_app -c "SELECT queue, count(*) FROM river_job GROUP BY queue;"
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

### SQL migration issues

```bash
# Check migration logs
docker compose logs api | grep migration

# Manually run migrations
docker compose exec api sh -c 'psql $DATABASE_URL < internal/database/migrations.sql'

# Drop and recreate database
docker compose down -v
docker compose up -d postgres
# Wait for postgres to be ready, then start api
docker compose up -d api
```

## View in Scout

After starting the application and generating some traffic:

1. Log in to [base14 Scout](https://app.base14.io)
2. Navigate to **Services** → **go-fiber-postgres-api**
3. View distributed traces, metrics, and logs
4. Explore the service map to see API ↔ Worker communication
5. Look for traces showing River job propagation

## Resources

- [Fiber Framework Documentation](https://docs.gofiber.io/)
- [sqlx Documentation](https://jmoiron.github.io/sqlx/)
- [River Documentation](https://riverqueue.com/docs)
- [OpenTelemetry Go](https://opentelemetry.io/docs/languages/go/)
- [base14 Scout Documentation](https://docs.base14.io)

