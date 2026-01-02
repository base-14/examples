# Quarkus with OpenTelemetry

Quarkus 3.17 application with OpenTelemetry instrumentation using the built-in
`quarkus-opentelemetry` extension.

## Instrumentation Approach

This example uses **Quarkus OpenTelemetry Extension** (production-ready):

- Extension: `quarkus-opentelemetry`
- Native compilation ready
- Automatic instrumentation for HTTP, JDBC, and more
- Custom spans with `@WithSpan` annotation

### What's Auto-Instrumented

- HTTP requests and responses (RESTEasy)
- Database queries (Hibernate/JDBC)
- JVM metrics
- Distributed trace propagation (W3C)

### What Requires Manual Instrumentation

- Custom business spans (`@WithSpan` annotation)
- Custom metrics (`MeterProvider`)

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Base14 Scout credentials ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
- Java 21+ and Maven 3.9+ (only for local development without Docker)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/quarkus/quarkus-postgres

# Set Base14 Scout credentials
export SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token

# Start application (PostgreSQL + Quarkus + OTel Collector)
docker compose up --build -d

# Verify it's running
curl http://localhost:8080/api/health

# Run API tests
./scripts/test-api.sh
```

The app runs on port `8080`, PostgreSQL on `5432`, OTel Collector on `4317/4318`.

## Configuration

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SCOUT_ENDPOINT` | Yes | Base14 Scout OTLP endpoint |
| `SCOUT_CLIENT_ID` | Yes | OAuth2 client ID |
| `SCOUT_CLIENT_SECRET` | Yes | OAuth2 client secret |
| `SCOUT_TOKEN_URL` | Yes | OAuth2 token endpoint |

### Application Environment Variables

| Variable | Default |
|----------|---------|
| `DB_HOST` | `localhost` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `quarkus` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | `postgres` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` |

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/register` | Register new user |
| `POST` | `/api/login` | Login and get JWT |
| `GET` | `/api/user` | Get current user (auth required) |
| `POST` | `/api/logout` | Logout (auth required) |

### Articles

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/articles` | List articles |
| `POST` | `/api/articles` | Create article (auth required) |
| `GET` | `/api/articles/:slug` | Get article |
| `PUT` | `/api/articles/:slug` | Update article (auth required) |
| `DELETE` | `/api/articles/:slug` | Delete article (auth required) |
| `POST` | `/api/articles/:slug/favorite` | Favorite (auth required) |
| `DELETE` | `/api/articles/:slug/favorite` | Unfavorite (auth required) |

### System

| Endpoint | Purpose |
|----------|---------|
| `/api/health` | Health check |
| `/q/health` | Quarkus SmallRye health |

## Development

### Run Locally (without Docker)

```bash
# Start PostgreSQL
docker compose up postgres -d

# Run in dev mode (with hot reload)
./mvnw quarkus:dev

# Or use Makefile
make dev
```

### Build and Test

```bash
make build          # Build JAR
make test           # Run tests
make test-api       # Run API tests
make build-lint     # Build and verify
```

### Docker Commands

```bash
make docker-up      # Start all services
make docker-down    # Stop all services
make docker-logs    # View logs
make docker-build   # Rebuild images
```

## Telemetry Data

### Traces

- HTTP requests (method, URL, status)
- Database queries (SQL statements)
- Custom business spans (`@WithSpan`)
- Exceptions with stack traces

### Metrics

- **HTTP**: Request count, duration
- **JVM**: Memory, GC, threads
- **Custom**: articles.created, articles.deleted, favorites.added, favorites.removed

### Logs

All logs include `traceId` and `spanId` for correlation.

## Technology Stack

| Component | Version |
|-----------|---------|
| Quarkus | 3.17.5 |
| Java | 21 |
| PostgreSQL | 17 |
| OTel Collector | 0.116.0 |
| Maven | 3.9+ |

## Resources

- [Quarkus OpenTelemetry Guide](https://quarkus.io/guides/opentelemetry)
- [OpenTelemetry Java](https://opentelemetry.io/docs/languages/java/)
- [Quarkus Documentation](https://quarkus.io/guides/)
- [Base14 Scout](https://base14.io/scout)
