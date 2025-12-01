# Go 1.19 + Gin + OpenTelemetry + PostgreSQL

Go application with OpenTelemetry instrumentation.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/custom-instrumentation/go)

## Stack Profile

| Component | Version | EOL Status | Current Version |
| --------- | ------- | ---------- | --------------- |
| **Go** | 1.19.13 | EOL | 1.25 (8 versions behind) |
| **Gin** | 1.9.1 | Stable | 1.10.0 |
| **PostgreSQL** | 14 | Active | 17 |
| **OpenTelemetry** | v1.17.0 | N/A | v1.38.0 (21 versions behind) |
| **GORM** | v1.25.2 | Stable | v1.25.x |

**Why This Matters:** This stack demonstrates challenges of maintaining
observability in older applications and provides a migration path to modern
versions.

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (Gin framework with otelgin middleware)
- ✅ Database queries (GORM with custom tracing callbacks)
- ✅ SQL operations (INSERT, SELECT, UPDATE, DELETE with full query details)
- ✅ Distributed trace propagation (W3C Trace Context)
- ✅ Graceful shutdown handling

### Custom Instrumentation

- **Traces**: User CRUD operations with custom spans
- **Spans**: Hierarchical spans (HTTP → Handler → SQL)
- **Attributes**: User data, SQL tables, query details
- **Events**: Business events (user_created, user_updated, user_deleted)
- **Logs**: Structured JSON logs with trace correlation
- **Error Recording**: Automatic error capture with stack traces

### What Requires Manual Work

- **Metrics**: No automatic HTTP/runtime metrics in Go 1.19/OTel v1.17.0
- **Logs**: Application logs use custom logrus integration for trace correlation

## Technology Stack

| Component | Version |
| --------- | ------- |
| Go | 1.19.13 (EOL) |
| Gin Framework | 1.9.1 |
| PostgreSQL | 14 |
| GORM | 1.25.2 |
| OpenTelemetry SDK | 1.17.0 |
| OTel Gin Instrumentation | 0.42.0 |
| OTel Collector | 0.82.0 |
| Logrus | 1.9.3 |

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Go 1.19+** (for local development - note: older version)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/go/go119-gin191-postgres
```

### 1. Set base14 Scout Credentials

Set these as environment variables (or edit `.env.example` → `.env`):

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

See the [base14 Collector Setup Guide][collector-setup] for obtaining
credentials.

[collector-setup]: https://docs.base14.io/category/opentelemetry-collector-setup

### 2. Start Services

```bash
docker compose up --build
```

This starts:

- **app**: Go 1.19 HTTP server on port 8080
- **postgres**: PostgreSQL 14 database
- **otel-collector**: OpenTelemetry Collector v0.82.0

### 3. Test the API

```bash
./scripts/test-api.sh
```

The test script exercises all user endpoints and verifies telemetry.

### 4. View Traces

Navigate to your Scout dashboard to view traces and metrics:

```text
https://your-tenant.base14.io
```

## Configuration

### Required Environment Variables

The OpenTelemetry Collector requires base14 Scout credentials to export
telemetry data:

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `SCOUT_ENDPOINT` | Yes | base14 Scout OTLP endpoint |
| `SCOUT_CLIENT_ID` | Yes | OAuth2 client ID from base14 Scout |
| `SCOUT_CLIENT_SECRET` | Yes | OAuth2 client secret from base14 Scout |
| `SCOUT_TOKEN_URL` | Yes | OAuth2 token endpoint |

### Application Environment Variables (compose.yaml)

| Variable | Default |
| -------- | ------- |
| `APP_ENV` | `development` |
| `APP_PORT` | `8080` |
| `DATABASE_URL` | `postgres://appuser:apppass@postgres:5432/appdb` |
| `OTEL_SERVICE_NAME` | `go119-gin-app` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `otel-collector:4317` |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment=development` |
| `LOG_DIR` | `/var/log/app` |

### Resource Attributes

Automatically included in telemetry:

```properties
service.name=go119-gin-app
service.version=1.0.0
deployment.environment=development
```

## API Endpoints

### Application Endpoints

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/users` | List all users |
| `GET` | `/api/users/{id}` | Get user by ID |
| `POST` | `/api/users` | Create user |
| `PUT` | `/api/users/{id}` | Update user |
| `DELETE` | `/api/users/{id}` | Delete user |

### Example Requests

```bash
# Create a user
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice Smith", "bio": "Developer"}'

# List users
curl http://localhost:8080/api/users

# Get specific user (replace {id} with actual UUID)
curl http://localhost:8080/api/users/{id}

# Update user
curl -X PUT http://localhost:8080/api/users/{id} \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Cooper"}'

# Delete user
curl -X DELETE http://localhost:8080/api/users/{id}
```

## Telemetry Data

### Traces

- **HTTP requests**: Method, path, status code, duration
- **Handler operations**: CreateUser, UpdateUser, DeleteUser, etc.
- **Database queries**: Full SQL statements with parameters
- **Span hierarchy**: HTTP → Handler → SQL operations
- **Attributes**: User data, table names, query details
- **Events**: Business events (user_created, user_updated)
- **Errors**: Automatic error capture with stack traces

### Logs

Structured JSON logs with automatic trace correlation:

```json
{
  "timestamp": "2025-12-01T14:20:42Z",
  "severity": "info",
  "message": "User created successfully",
  "trace_id": "6ec1f6ce672d342770671880fbf89ab9",
  "span_id": "cc5e4bb6c023c846",
  "trace_flags": "01",
  "service.name": "go119-gin-app",
  "user.id": "04f12a44-66f7-4e15-938e-ec48a2fc1d47",
  "user.email": "alice@example.com"
}
```

**Log Correlation**: All logs include `trace_id` and `span_id` for
correlation with traces in Scout Dashboard.

### Metrics

**Note**: Automatic metrics collection is limited in OpenTelemetry Go v1.17.0:

- ❌ HTTP request metrics (not auto-instrumented in otelgin v0.42.0)
- ❌ Runtime metrics (memory, goroutines, GC)
- ✅ Custom metrics can be added using OTel SDK

For production, consider upgrading to Go 1.22+ and OTel v1.24.0+ for full
metrics support.

## OpenTelemetry Configuration

### Dependencies (go.mod)

```go
require (
    github.com/gin-gonic/gin v1.9.1
    github.com/google/uuid v1.3.0
    github.com/sirupsen/logrus v1.9.3
    go.opentelemetry.io/otel v1.17.0
    go.opentelemetry.io/otel/sdk v1.17.0
    go.opentelemetry.io/otel/trace v1.17.0
    go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc v1.17.0
    go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc v0.40.0
    go.opentelemetry.io/contrib/instrumentation/
        github.com/gin-gonic/gin/otelgin v0.42.0
    gorm.io/gorm v1.25.2
    gorm.io/driver/postgres v1.5.2
)
```

### Telemetry Initialization

See `internal/telemetry/telemetry.go` for complete implementation:

- **Trace Provider**: OTLP gRPC exporter with batch span processor
- **Meter Provider**: OTLP metrics exporter with periodic reader
- **Propagation**: W3C Trace Context + Baggage
- **Resource**: Service name, version, and environment attributes

### Custom Spans and Logging Example

```go
func (h *UserHandler) CreateUser(c *gin.Context) {
    ctx, span := tracer.Start(c.Request.Context(), "CreateUser",
        trace.WithSpanKind(trace.SpanKindServer))
    defer span.End()

    // Correlated logging
    logging.Info(ctx, "Received request to create new user")

    // Add span attributes
    span.SetAttributes(
        attribute.String("user.email", user.Email),
        attribute.String("user.name", user.Name),
    )

    // Structured log with context
    logging.WithFields(ctx, map[string]interface{}{
        "user.email": user.Email,
        "user.name":  user.Name,
    }).Info("Creating user in database")

    // Database operation (automatically traced via GORM callbacks)
    result := h.db.WithContext(ctx).Create(&user)

    if result.Error != nil {
        logging.WithFields(ctx, map[string]interface{}{
            "error": result.Error.Error(),
        }).Error("Failed to create user in database")
        span.RecordError(result.Error)
        span.SetStatus(codes.Error, "failed to create user")
        return
    }

    // Add span event
    span.AddEvent("user_created")

    // Log success with trace correlation
    logging.WithFields(ctx, map[string]interface{}{
        "user.id": user.ID.String(),
    }).Info("User created successfully")
}
```

## Database Schema

### Users Table

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    bio TEXT,
    image VARCHAR(512),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Development

### Local Build

```bash
# Download dependencies
go mod download

# Build binary
go build -o server ./cmd/server

# Run locally (requires PostgreSQL)
./server
```

### Docker Commands

```bash
# Build and start
docker compose up --build

# Start in background
docker compose up -d

# View logs
docker compose logs -f app
docker compose logs -f otel-collector

# Stop services
docker compose down

# Rebuild
docker compose build
```

### Access Services

```bash
# Application logs
docker compose logs -f app

# Database access
docker exec -it postgres14 psql -U appuser -d appdb

# OTel collector zpages
open http://localhost:55679/debug/servicez
```

## Upgrading This Stack

This example uses older versions intentionally. To upgrade:

### Go 1.19 → Go 1.22+

```bash
# Update go.mod
go 1.22

# Update OpenTelemetry (Go 1.20+ required for v1.18.0+)
go get go.opentelemetry.io/otel@v1.24.0
go get go.opentelemetry.io/otel/sdk@v1.24.0
go get go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc@v1.24.0

# Update Gin
go get github.com/gin-gonic/gin@v1.10.0

# Rebuild
go mod tidy
go build ./cmd/server
```

### Key Breaking Changes

- **Go 1.20**: Introduced `errors.Join()` used by OTel v1.18.0+
- **Go 1.21**: Minimum version requirements updated
- **OTel v1.18.0**: Dropped Go 1.19 support

## Troubleshooting

### No traces appearing in Scout

1. Check OTel collector logs:

   ```bash
   docker compose logs otel-collector
   ```

2. Verify Scout credentials in `.env`

3. Test collector health:

   ```bash
   curl http://localhost:55679/debug/servicez
   ```

### Database connection errors

1. Verify PostgreSQL is running:

   ```bash
   docker compose ps postgres
   ```

2. Test connection:

   ```bash
   docker exec postgres14 pg_isready -U appuser -d appdb
   ```

3. Check `DATABASE_URL` in `.env`

### Go version mismatch

This example requires Go 1.19. To check your version:

```bash
go version
```

If using a newer version, you may need to adjust dependencies in `go.mod`.

## Next Steps

This is **Option A** - Basic users CRUD. More endpoints will be added:

- **Option B**: Add articles API with relationships
- **Option C**: Add comments and favorites
- **Option D**: Add authentication (JWT)
- **Option E**: Add tags and article feed

Each addition will demonstrate incremental migration strategies.

## Implementation Notes

### SQL Tracing

This example uses **custom GORM callbacks** for SQL tracing instead of external plugins:

- Compatible with Go 1.19 and OTel v1.17.0
- Captures all CRUD operations (create, query, update, delete)
- Includes full SQL statements with placeholders
- Proper parent-child span relationships
- See `internal/database/tracing.go` for implementation

### Log Correlation

Logs use **logrus with custom trace extraction**:

- JSON formatted output
- Automatic trace_id and span_id injection
- File-based collection by OTel Collector (filelog receiver)
- See `internal/logging/logger.go` for implementation

### Metrics Limitations

OpenTelemetry Go v1.17.0 has limited metrics support:

- No automatic HTTP metrics from otelgin v0.42.0
- No built-in runtime metrics collectors
- Custom metrics require manual instrumentation
- Upgrade to Go 1.22+ and OTel v1.24.0+ for full metrics

## Resources

- [OpenTelemetry Go Documentation][otel-go] - Go SDK reference
- [Gin Framework][gin] - Gin web framework
- [GORM][gorm] - Go ORM library
- [base14 Scout][scout] - Observability platform
- [base14 Documentation][docs] - Full instrumentation guides

[otel-go]: https://pkg.go.dev/go.opentelemetry.io/otel@v1.17.0
[gin]: https://github.com/gin-gonic/gin/tree/v1.9.1
[gorm]: https://gorm.io/docs/
[scout]: https://base14.io/scout
[docs]: https://docs.base14.io
