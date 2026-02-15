# .NET 9 ASP.NET Core + Azure SQL Edge + OpenTelemetry Example

A production-ready ASP.NET Core 9 REST API demonstrating full OpenTelemetry instrumentation with Minimal APIs, Entity Framework Core, and Azure SQL Edge.

> [Full Documentation](https://docs.base14.io/instrument/apps/custom-instrumentation/dotnet)

## Stack Profile

| Component | Version | Status | Notes |
|-----------|---------|--------|-------|
| **.NET SDK** | 9.0 | Active | Latest stable |
| **ASP.NET Core** | 9.0 | Active | Minimal APIs |
| **C#** | 13 | Active | Latest language version |
| **Azure SQL Edge** | latest | Active | SQL Server compatible, ARM64 native |
| **Entity Framework Core** | 9.0.0 | Active | Latest ORM version |
| **OpenTelemetry** | 1.15.0 | Active | Traces, metrics, logs via OTLP |
| **BCrypt.Net-Next** | 4.0.3 | Active | Password hashing |

**Version Selection**: Latest Stable
**Verified**: 2026-02-15

**Why This Stack**: .NET 9 with Minimal APIs for lightweight endpoint routing and EF Core 9 for
SQL Server integration. Azure SQL Edge provides ARM64-native SQL Server compatibility for all platforms.

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (ASP.NET Core instrumentation)
- ✅ Database queries (EF Core + SqlClient instrumentation)
- ✅ HTTP client calls (HttpClient instrumentation)
- ✅ .NET runtime metrics (GC, thread pool, assembly count)
- ✅ Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: User authentication, article CRUD, favorites via custom ActivitySource
- **Attributes**: User ID, article slug, job metadata, error context
- **Logs**: Structured logs with trace correlation via OpenTelemetry logging provider
- **Metrics**: Auth attempts/failures, article counts, favorite counts, job metrics

### What Requires Manual Work

- Business-specific custom spans use `ActivitySource.StartActivity()`
- Custom metrics defined via `System.Diagnostics.Metrics` API
- Background job trace propagation (demonstrated with SQL Server READPAST pattern)

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **.NET 9 SDK** (for local development only)

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/csharp/dotnet-sqlserver
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
2. Navigate to **Services** → **dotnet-sqlserver-api**
3. Click any trace to see the distributed view

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /api/health | No | Health check with DB ping |
| POST | /api/register | No | Register new user |
| POST | /api/login | No | Login, returns JWT |
| GET | /api/user | Yes | Get current user |
| POST | /api/logout | Yes | Logout |
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
csharp/dotnet-sqlserver/
├── Makefile                # Build tasks
├── compose.yml             # Docker stack
├── Dockerfile              # API multi-stage build
├── Dockerfile.worker       # Worker multi-stage build
├── config/
│   └── otel-config.yaml    # OTel Collector config
├── scripts/
│   ├── test-api.sh         # Integration tests
│   └── verify-scout.sh     # Telemetry verification
└── src/
    ├── Api/
    │   ├── Program.cs              # Entry point, DI, middleware
    │   ├── appsettings.json        # Configuration
    │   ├── Data/
    │   │   ├── AppDbContext.cs     # EF Core DbContext
    │   │   └── Entities/           # Domain models
    │   ├── Models/                 # Request/Response DTOs
    │   ├── Services/               # Business logic
    │   ├── Endpoints/              # Minimal API endpoints
    │   ├── Middleware/             # Exception handling
    │   └── Telemetry/              # OTel configuration
    └── Worker/
        └── Program.cs              # Background job processor
```

## Telemetry

### Traces

All operations are instrumented with distributed tracing:

- HTTP requests via ASP.NET Core instrumentation
- Database queries via EF Core built-in tracing
- Service methods via custom ActivitySource
- Background jobs with trace context propagation

### Metrics

Custom business metrics exported via OTLP:

| Metric | Type | Description |
|--------|------|-------------|
| `http.requests.total` | Counter | Total HTTP requests |
| `http.request.duration` | Histogram | HTTP request duration (ms) |
| `users.registered` | Counter | Total users registered |
| `auth.login.attempts` | Counter | Total login attempts |
| `auth.login.failures` | Counter | Failed login attempts |
| `articles.created` | Counter | Total articles created |
| `articles.updated` | Counter | Total articles updated |
| `articles.deleted` | Counter | Total articles deleted |
| `favorites.added` | Counter | Total favorites added |
| `favorites.removed` | Counter | Total favorites removed |
| `jobs.enqueued` | Counter | Total jobs enqueued |
| `jobs.completed` | Counter | Total jobs completed |
| `jobs.failed` | Counter | Total jobs failed |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ASPNETCORE_HTTP_PORTS` | 8080 | API server port |
| `ConnectionStrings__DefaultConnection` | - | SQL Server connection string |
| `Jwt__Secret` | - | JWT signing secret (min 32 chars) |
| `Jwt__Issuer` | dotnet-sqlserver | JWT issuer |
| `Jwt__Audience` | dotnet-sqlserver-api | JWT audience |
| `Jwt__ExpirationHours` | 168 | Token expiry in hours |
| `OTEL_SERVICE_NAME` | dotnet-sqlserver | Service name for telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | http://localhost:4317 | OTLP gRPC endpoint |

## Development

```bash
# Install .NET 9 SDK from https://dot.net

# Using Makefile
make build          # Build all projects
make test           # Run tests
make build-lint     # Build + format check
make clean          # Clean build artifacts

# Or using dotnet directly
dotnet build
dotnet test
dotnet run --project src/Api

# Run locally (requires SQL Server)
export ConnectionStrings__DefaultConnection="Server=localhost;Database=DotnetApi;User Id=sa;Password=YourStrong@Passw0rd;TrustServerCertificate=true"
export Jwt__Secret="your-super-secret-jwt-key-change-in-production-minimum-32-chars"
dotnet run --project src/Api
```

## Background Jobs

The application uses a SQL Server-native job queue with the `READPAST` hint (equivalent to PostgreSQL's `SKIP LOCKED`) for reliable, distributed job processing.

### Job Queue Features

- **Atomic dequeue**: Uses `READPAST` for safe concurrent processing
- **Trace propagation**: Parent trace context is stored and extracted for job processing
- **Multiple job types**: Extensible handler system

### Job Flow

1. Article creation enqueues a `notification` job
2. Worker polls the `Jobs` table using `READPAST`
3. Job is processed with trace context from parent span
4. Status updated to `completed` or `failed`

## Docker

### Building

```bash
# Build all images
docker compose build

# Build API image only
docker build -t dotnet-sqlserver-api .

# Build Worker image only
docker build -f Dockerfile.worker -t dotnet-sqlserver-worker .
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| api | 8080 | Main API server |
| worker | - | Background job processor |
| sqlserver | 1433 | Azure SQL Edge |
| otel-collector | 4317, 4318 | OpenTelemetry Collector |

## OpenTelemetry Configuration

### Dependencies

From `src/Api/Api.csproj`:

```xml
<PackageReference Include="OpenTelemetry.Exporter.OpenTelemetryProtocol" Version="1.15.0" />
<PackageReference Include="OpenTelemetry.Extensions.Hosting" Version="1.15.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.AspNetCore" Version="1.15.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.Http" Version="1.15.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.Runtime" Version="1.15.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.SqlClient" Version="1.15.0-beta.1" />
```

### Implementation

Telemetry is configured in `src/Api/Telemetry/TelemetrySetup.cs`:

- Tracing: ASP.NET Core, HttpClient, SqlClient, and custom ActivitySources
- Metrics: ASP.NET Core, HttpClient, Runtime, and custom meter `DotnetSqlServer.Metrics`
- Logging: OpenTelemetry logging provider with trace correlation
- All exported via OTLP to the collector

Custom metrics are defined in `src/Api/Telemetry/Metrics.cs` using `System.Diagnostics.Metrics`.

### Custom Instrumentation Example

```csharp
private static readonly ActivitySource ActivitySource = new("DotnetSqlServer.ArticleService");

public async Task<ArticleResponse> CreateAsync(int userId, CreateArticleRequest request)
{
    using var activity = ActivitySource.StartActivity("article.create");
    activity?.SetTag("user.id", userId);
    // Business logic...
    AppMetrics.ArticlesCreated.Add(1);
    return response;
}
```

## Database Schema

Schema is managed by EF Core code-first migrations. Entities defined in `src/Api/Data/Entities/`.
Tables: `Users`, `Articles`, `Favorites`, and `Jobs` (SQL Server-native queue with READPAST hint
and trace context propagation).

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
# Check SQL Server is healthy
docker compose ps sqlserver

# SQL Server can take 30+ seconds to start
# Check logs for "SQL Server is now ready for client connections"
docker compose logs sqlserver
```

### Application won't start

```bash
# Check API logs for startup errors
docker compose logs api

# Common causes: connection string wrong, JWT secret too short (min 32 chars), port conflict
```

### Background jobs not processing

```bash
# Check worker logs
docker compose logs worker

# Worker polls every 1000ms by default (JobProcessor__PollingIntervalMs)
```

### EF Core migration errors

```bash
# Migrations run automatically on startup via AppDbContext
# If schema is stale, recreate volumes
docker compose down -v && docker compose up -d --build
```

## Resources

- [ASP.NET Core Documentation](https://learn.microsoft.com/en-us/aspnet/core/)
- [Entity Framework Core](https://learn.microsoft.com/en-us/ef/core/)
- [OpenTelemetry .NET](https://opentelemetry.io/docs/languages/net/)
- [.NET Minimal APIs](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/minimal-apis)
- [base14 Scout](https://base14.io)
- [base14 Documentation](https://docs.base14.io)
