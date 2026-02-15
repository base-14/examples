# Rust Axum + PostgreSQL + OpenTelemetry Example

A production-ready Rust web application demonstrating full OpenTelemetry instrumentation with Axum, SQLx, and PostgreSQL-native background jobs.

> [Full Documentation](https://docs.base14.io/instrument/apps/custom-instrumentation/rust)

## Stack Profile

| Component | Version | Status | Notes |
|-----------|---------|--------|-------|
| **Rust** | 1.92.0 | Active | Edition 2024 |
| **Axum** | 0.8.8 | Active | Tower-based async web framework |
| **SQLx** | 0.8.6 | Active | Async PostgreSQL with compile-time queries |
| **PostgreSQL** | 18 | Active (Nov 2029) | Latest stable |
| **OpenTelemetry** | 0.31.0 | Active | Traces, metrics, logs via OTLP |
| **tracing** | 0.1.44 | Active | Instrumentation framework |
| **tracing-opentelemetry** | 0.32.0 | Active | OTel bridge |
| **jsonwebtoken** | 10.3.0 | Active | JWT authentication |
| **argon2** | 0.5.3 | Active | Password hashing |

**Version Selection**: Latest Stable
**Verified**: 2026-02-15

**Why This Stack**: Latest stable Rust with Axum 0.8 (Tower ecosystem) and SQLx for type-safe async
PostgreSQL queries. OpenTelemetry 0.31 provides unified traces, metrics, and logs export via OTLP.

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (tower-http TraceLayer)
- ✅ Database queries (SQLx tracing integration)
- ✅ Distributed trace propagation (W3C Trace Context)
- ✅ Log export with trace correlation (OTLP logs via tracing-opentelemetry)

### Custom Instrumentation

- **Traces**: User authentication, article CRUD, favorites with `#[instrument]` spans
- **Attributes**: User ID, article slug, job metadata, error context
- **Logs**: Structured JSON logs with trace correlation (traceId, spanId)
- **Metrics**: HTTP request count/duration, article counts, favorite counts, job metrics

### What Requires Manual Work

- Business-specific custom spans use `#[instrument]` attribute macro
- Custom metrics defined via OpenTelemetry meter API
- Background job trace propagation (demonstrated with PostgreSQL SKIP LOCKED pattern)

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Rust 1.92+** (for local development only)

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/rust/axum-postgres
```

### 2. Set base14 Scout Credentials

```bash
cp .env.example .env
```

Edit `.env` with your Scout credentials:

```bash
SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
SCOUT_CLIENT_ID=your_client_id
SCOUT_CLIENT_SECRET=your_client_secret
SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
SCOUT_ENVIRONMENT=development
```

New to Scout? See [Scout Setup Guide](https://docs.base14.io/get-started/scout-setup)

### 3. Start Services

```bash
docker compose up -d --build
```

### 4. Run API Tests

```bash
./scripts/test-api.sh
```

### 5. Verify Telemetry

```bash
./scripts/verify-scout.sh
```

### 6. View Traces in Scout

1. Log in to [base14 Scout](https://app.base14.io)
2. Navigate to **Services** → **rust-axum-postgres-api**
3. Click any trace to see the distributed view

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

### Example Requests

**Register user**:

```bash
curl -X POST http://localhost:8080/api/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice", "password": "password123"}'
```

**Login**:

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "password123"}' \
  | jq -r '.token')
```

**Create article** (authenticated):

```bash
curl -X POST http://localhost:8080/api/articles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title": "My Article", "body": "Article content here", "description": "A brief description"}'
```

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

## OpenTelemetry Configuration

### Dependencies

From `Cargo.toml`:

```toml
opentelemetry = "0.31.0"
opentelemetry_sdk = { version = "0.31.0", features = ["rt-tokio", "logs"] }
opentelemetry-otlp = { version = "0.31.0", features = ["grpc-tonic", "trace", "logs"] }
opentelemetry-appender-tracing = "0.31.0"
tracing = "0.1.44"
tracing-subscriber = { version = "0.3", features = ["env-filter", "json"] }
tracing-opentelemetry = "0.32.0"
```

### Implementation

Telemetry is initialized in `src/telemetry/init.rs`:

- Resource attributes: service name, version, namespace, deployment environment
- Trace exporter: OTLP gRPC with 10s timeout
- Log exporter: OTLP gRPC batch export
- Tracing subscriber layers: OpenTelemetry bridge + JSON formatting (production) or pretty-print (development)
- Log filter: `RUST_LOG` env var (default: `info,sqlx=warn,tower_http=debug`)
- Graceful shutdown with `TelemetryGuard`

Custom metrics are defined in `src/telemetry/metrics.rs` using global `LazyLock` statics.

### Custom Instrumentation Example

```rust
#[instrument(name = "article.create", skip(self, input), fields(author_id))]
pub async fn create(&self, author_id: i32, input: CreateArticleInput) -> AppResult<ArticleResponse> {
    Span::current().record("author_id", author_id);
    // Business logic...
    ARTICLES_CREATED.add(1, &[]);
    Ok(response)
}
```

Repository methods use the same pattern:

```rust
#[instrument(name = "db.article.find_by_slug", skip(self))]
pub async fn find_by_slug(&self, slug: &str) -> Result<Option<ArticleWithAuthor>, sqlx::Error> {
    // Query implementation
}
```

## Database Schema

Schema defined in `migrations/20260106000001_initial.sql`. Tables: `users`, `articles`, `favorites`,
and `jobs` (PostgreSQL-native queue with SKIP LOCKED pattern and W3C trace context propagation).

## Troubleshooting

### No traces appearing in Scout

```bash
# Check collector logs for export errors
docker compose logs otel-collector

# Verify Scout credentials are set
grep SCOUT .env

# Test collector health
curl http://localhost:13133/health
```

### Database connection errors

```bash
# Check PostgreSQL is healthy
docker compose ps postgres

# Verify connection
docker compose exec postgres pg_isready -U postgres
```

### Application won't start

```bash
# Check API logs for startup errors
docker compose logs api

# Common causes: DATABASE_URL not set, JWT_SECRET missing, port conflict
```

### Background jobs not processing

```bash
# Check worker logs
docker compose logs worker

# Verify pending jobs exist
docker compose exec postgres psql -U postgres -d rust_axum_app \
  -c "SELECT id, kind, status FROM jobs ORDER BY created_at DESC LIMIT 5"
```

### Rust compilation errors

```bash
# Clean and rebuild
cargo clean && cargo build

# Check Rust version (requires 1.92+)
rustc --version

# Update toolchain
rustup update stable
```

## Resources

- [Axum Documentation](https://docs.rs/axum/latest/axum/)
- [SQLx Documentation](https://docs.rs/sqlx/latest/sqlx/)
- [OpenTelemetry Rust](https://opentelemetry.io/docs/languages/rust/)
- [tracing Documentation](https://docs.rs/tracing/latest/tracing/)
- [base14 Scout](https://base14.io)
- [base14 Documentation](https://docs.base14.io)
