# Rust Axum + PostgreSQL + OpenTelemetry Example

A production-ready Rust web application demonstrating full OpenTelemetry instrumentation with Axum, SQLx, and PostgreSQL-native background jobs.

## Stack Profile

| Component | Version | Notes |
|-----------|---------|-------|
| Rust | 1.92.0 | Latest stable |
| Axum | 0.8.8 | Tower-based async web framework |
| SQLx | 0.8.6 | Async PostgreSQL with runtime queries |
| PostgreSQL | 18-alpine | Latest stable |
| OpenTelemetry | 0.31.0 | Traces, metrics, logs via OTLP |
| tracing | 0.1.44 | Instrumentation framework |
| tracing-opentelemetry | 0.32.0 | OTel bridge |
| jsonwebtoken | 9.3 | JWT authentication |
| argon2 | 0.5.3 | Password hashing |

## Features

- RESTful API with JWT authentication
- PostgreSQL-native job queue using `SKIP LOCKED` pattern
- Full OpenTelemetry instrumentation (traces, metrics, logs via OTLP)
- Custom spans with business metrics
- HTTP request metrics (count, duration histogram)
- Request ID generation and propagation
- Trace ID included in error responses
- Trace context propagation to background jobs
- Multi-stage Docker builds
- Graceful shutdown handling

## Quick Start

```bash
# Start all services
docker compose up -d

# Wait for services to be ready
sleep 5

# Run integration tests
./scripts/test-api.sh

# View logs
docker compose logs -f api

# Verify telemetry
./scripts/verify-scout.sh
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/health | No | Health check with DB ping |
| POST | /api/register | No | Register new user |
| POST | /api/login | No | Login, returns JWT |
| GET | /api/user | Yes | Get current user |
| GET | /api/articles | Optional | List articles (paginated) |
| POST | /api/articles | Yes | Create article |
| GET | /api/articles/:slug | Optional | Get article by slug |
| PUT | /api/articles/:slug | Owner | Update article |
| DELETE | /api/articles/:slug | Owner | Delete article |
| POST | /api/articles/:slug/favorite | Yes | Favorite article |
| DELETE | /api/articles/:slug/favorite | Yes | Unfavorite article |

## Project Structure

```
rust/axum-postgres/
├── Cargo.toml              # Dependencies
├── Makefile                # Build tasks
├── compose.yml             # Docker stack
├── Dockerfile              # API multi-stage build
├── Dockerfile.worker       # Worker multi-stage build
├── config/
│   └── otel-config.yaml    # OTel Collector config
├── migrations/
│   └── *.sql               # Database schema
├── scripts/
│   ├── test-api.sh         # Integration tests
│   └── verify-scout.sh     # Telemetry verification
└── src/
    ├── main.rs             # API entry point
    ├── config.rs           # Environment config
    ├── error.rs            # Error types
    ├── routes.rs           # Router setup
    ├── database/           # SQLx connection pool
    ├── handlers/           # HTTP handlers
    ├── middleware/         # Auth middleware
    ├── models/             # Data models & DTOs
    ├── repository/         # Data access layer
    ├── services/           # Business logic
    ├── jobs/               # Background job queue
    └── telemetry/          # OTel initialization
```

## Telemetry

### Traces

All operations are instrumented with distributed tracing:

- HTTP requests via `tower-http` TraceLayer
- Database queries via SQLx instrumentation
- Service methods via `#[instrument]` attribute
- Background jobs with trace context propagation

### Metrics

Custom business metrics exported via OTLP:

| Metric | Type | Description |
|--------|------|-------------|
| `http.requests.total` | Counter | Total HTTP requests |
| `http.request.duration` | Histogram | HTTP request duration (ms) |
| `articles.created` | Counter | Total articles created |
| `articles.updated` | Counter | Total articles updated |
| `articles.deleted` | Counter | Total articles deleted |
| `favorites.added` | Counter | Total favorites added |
| `favorites.removed` | Counter | Total favorites removed |
| `users.registered` | Counter | Total users registered |
| `jobs.enqueued` | Counter | Total jobs enqueued |
| `jobs.completed` | Counter | Total jobs completed |
| `jobs.failed` | Counter | Total jobs failed |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8080 | API server port |
| `DATABASE_URL` | - | PostgreSQL connection string |
| `JWT_SECRET` | - | JWT signing secret |
| `JWT_EXPIRES_IN_HOURS` | 168 | Token expiry in hours |
| `ENVIRONMENT` | development | Environment name |
| `OTEL_SERVICE_NAME` | rust-axum-postgres | Service name for telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | http://localhost:4317 | OTLP gRPC endpoint |

## Development

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Using Makefile
make build          # Build release binaries
make test           # Run all tests
make lint           # Run clippy
make format         # Run cargo fmt
make build-lint     # Build + lint + test
make clean          # Clean build artifacts

# Or using cargo directly
cargo check         # Check code
cargo test          # Run tests
cargo build --release

# Run locally (requires PostgreSQL)
export DATABASE_URL="postgres://postgres:postgres@localhost:5432/app"
export JWT_SECRET="your-secret-key"
cargo run
```

## Background Jobs

The application uses a PostgreSQL-native job queue with the `SKIP LOCKED` pattern for reliable, distributed job processing.

### Job Queue Features

- **Atomic dequeue**: Uses `FOR UPDATE SKIP LOCKED` for safe concurrent processing
- **Retry support**: Failed jobs can be retried with exponential backoff
- **Trace propagation**: Parent trace context is stored and extracted for job processing
- **Multiple job types**: Extensible handler system

### Job Flow

1. Article creation enqueues a `notification` job
2. Worker polls the `jobs` table using `SKIP LOCKED`
3. Job is processed with trace context from parent span
4. Status updated to `completed` or `failed`

## Docker

### Building

```bash
# Build API image
docker build -t rust-axum-api .

# Build Worker image
docker build -f Dockerfile.worker -t rust-axum-worker .
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| api | 8080 | Main API server |
| worker | - | Background job processor |
| postgres | 5432 | PostgreSQL database |
| otel-collector | 4317 | OpenTelemetry Collector |

## Key Patterns

### Custom Spans in Services

```rust
#[instrument(name = "article.create", skip(self, input), fields(author_id))]
pub async fn create(&self, author_id: i32, input: CreateArticleInput) -> AppResult<ArticleResponse> {
    // Business logic here
    ARTICLES_CREATED.add(1, &[]);
    Ok(response)
}
```

### Error Handling

The `AppError` enum maps to appropriate HTTP status codes:

```rust
pub enum AppError {
    NotFound(String),      // 404
    Validation(String),    // 400
    Unauthorized,          // 401
    Forbidden,             // 403
    Internal(String),      // 500
    Database(sqlx::Error), // 500
}
```

### Repository Pattern

Data access is abstracted through repositories with tracing:

```rust
#[instrument(name = "db.article.find_by_slug", skip(self))]
pub async fn find_by_slug(&self, slug: &str) -> Result<Option<ArticleWithAuthor>, sqlx::Error> {
    // Query implementation
}
```
