# Rust Actix Web + PostgreSQL + OpenTelemetry Example

A production-ready Rust web application demonstrating full OpenTelemetry instrumentation with Actix Web, SQLx, and PostgreSQL-native background jobs.

## Stack Profile

| Component | Version | Notes |
|-----------|---------|-------|
| Rust | 1.92.0 | Latest stable, edition 2024 |
| Actix Web | 4.12 | High-performance async web framework |
| SQLx | 0.8.6 | Async PostgreSQL with runtime queries |
| PostgreSQL | 18.2-alpine | Latest stable |
| OpenTelemetry | 0.31.0 | Traces, metrics, logs via OTLP |
| tracing | 0.1.44 | Instrumentation framework |
| tracing-opentelemetry | 0.32.0 | OTel bridge |
| tracing-actix-web | 0.7 | HTTP span instrumentation |
| jsonwebtoken | 10.3 | JWT authentication |
| argon2 | 0.5.3 | Password hashing |
| OTel Collector | 0.144.0 | Pinned (0.145.0 breaks oauth2client) |

## Features

- RESTful API with JWT authentication
- PostgreSQL-native job queue using `SKIP LOCKED` pattern
- Full OpenTelemetry instrumentation (traces, metrics, logs via OTLP)
- Custom spans with business metrics
- HTTP request spans with parameterized route names via `tracing-actix-web`
- Trace ID included in error responses
- Trace context propagation to background jobs (W3C traceparent)
- Noisy span filtering at collector level
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
| POST | /api/logout | Yes | Logout (stateless) |
| GET | /api/articles | Optional | List articles (paginated) |
| POST | /api/articles | Yes | Create article |
| GET | /api/articles/:slug | Optional | Get article by slug |
| PUT | /api/articles/:slug | Owner | Update article |
| DELETE | /api/articles/:slug | Owner | Delete article |
| POST | /api/articles/:slug/favorite | Yes | Favorite article |
| DELETE | /api/articles/:slug/favorite | Yes | Unfavorite article |

## Project Structure

```
rust/actix-postgres/
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
    ├── main.rs             # API entry point (HttpServer + TracingLogger)
    ├── lib.rs              # Module declarations
    ├── config.rs           # Environment config
    ├── error.rs            # AppError with ResponseError trait
    ├── routes.rs           # web::ServiceConfig route registration
    ├── bin/
    │   └── worker.rs       # Background job processor
    ├── database/           # SQLx connection pool + migrations
    ├── handlers/           # HTTP handlers (web::Data, web::Json, web::Path)
    ├── middleware/          # Auth extractors (FromRequest trait)
    ├── models/             # Data models & DTOs
    ├── repository/         # Data access layer
    ├── services/           # Business logic with tracing
    ├── jobs/               # PostgreSQL-native job queue
    └── telemetry/          # OTel initialization + metrics
```

## Telemetry

### Traces

All operations are instrumented with distributed tracing:

- HTTP requests via `tracing-actix-web::TracingLogger` (parameterized route names)
- Database queries via SQLx instrumentation
- Service methods via `#[instrument]` attribute
- Background jobs with W3C traceparent propagation

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

### Collector Configuration

The OTel Collector is configured with a `filter/noisy` processor to drop low-value spans:
- `pg-pool.connect` spans from connection pool management
- Bare HTTP method spans (e.g., `GET`, `POST`) that duplicate framework-level route spans

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8080 | API server port |
| `DATABASE_URL` | - | PostgreSQL connection string |
| `JWT_SECRET` | - | JWT signing secret |
| `JWT_EXPIRES_IN_HOURS` | 168 | Token expiry in hours |
| `ENVIRONMENT` | development | Environment name |
| `OTEL_SERVICE_NAME` | actix-postgres | Service name for telemetry |
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

The application uses a PostgreSQL-native job queue with the `SKIP LOCKED` pattern for reliable, distributed job processing without requiring Redis.

### Job Queue Features

- **Atomic dequeue**: Uses `FOR UPDATE SKIP LOCKED` for safe concurrent processing
- **Retry support**: Failed jobs are retried up to `max_attempts`
- **Trace propagation**: W3C traceparent stored in `trace_context JSONB` column
- **Multiple job types**: Extensible handler system

### Job Flow

1. Article creation enqueues a `notification` job with trace context
2. Worker polls the `jobs` table every second using `SKIP LOCKED`
3. Job is processed under a span linked to the API's parent trace
4. Status updated to `completed` or `failed`

## Actix Web vs Axum

This example mirrors the `rust/axum-postgres` implementation with Actix Web-specific patterns:

| Aspect | Axum | Actix Web |
|--------|------|-----------|
| State | `State<AppState>` extractor | `web::Data<T>` (wraps Arc) |
| Routing | `Router::new().route()` | `web::ServiceConfig` with `.route()` |
| Extractors | `FromRequestParts` trait | `FromRequest` trait |
| HTTP tracing | `tower-http` TraceLayer | `tracing-actix-web::TracingLogger` |
| Error response | `IntoResponse` trait | `ResponseError` trait |
| Server | `axum::serve()` | `HttpServer::new().bind().run()` |

## Docker

### Building

```bash
# Build API image
docker build -t actix-postgres-api .

# Build Worker image
docker build -f Dockerfile.worker -t actix-postgres-worker .
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| api | 8080 | Main API server |
| worker | - | Background job processor |
| postgres | 5432 | PostgreSQL database |
| otel-collector | 4317 | OpenTelemetry Collector (0.144.0) |

## Key Patterns

### Actix Web Extractors for Auth

```rust
pub struct AuthUser(pub i32);

impl FromRequest for AuthUser {
    type Error = AppError;
    type Future = Ready<Result<Self, Self::Error>>;

    fn from_request(req: &HttpRequest, _payload: &mut Payload) -> Self::Future {
        // Extract Bearer token, validate JWT, return user ID
    }
}
```

### Error Handling with ResponseError

```rust
impl actix_web::ResponseError for AppError {
    fn status_code(&self) -> StatusCode {
        match self {
            AppError::NotFound(_) => StatusCode::NOT_FOUND,
            AppError::Unauthorized => StatusCode::UNAUTHORIZED,
            // ...
        }
    }

    fn error_response(&self) -> HttpResponse {
        // JSON body with trace_id for observability
    }
}
```

### Repository Pattern with Tracing

```rust
#[instrument(name = "db.article.find_by_slug", skip(self))]
pub async fn find_by_slug(&self, slug: &str) -> Result<Option<ArticleWithAuthor>, sqlx::Error> {
    // Query implementation
}
```
