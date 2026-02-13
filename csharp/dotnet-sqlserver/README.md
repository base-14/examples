# .NET 9 ASP.NET Core + Azure SQL Edge + OpenTelemetry Example

A production-ready ASP.NET Core 9 REST API demonstrating full OpenTelemetry instrumentation with Minimal APIs, Entity Framework Core, and Azure SQL Edge.

## Stack Profile

| Component | Version | Notes |
|-----------|---------|-------|
| .NET SDK | 9.0 | Latest stable |
| ASP.NET Core | 9.0 | Minimal APIs |
| C# | 13 | Latest language version |
| Azure SQL Edge | latest | SQL Server compatible, ARM64 native |
| Entity Framework Core | 9.0.0 | Latest ORM version |
| OpenTelemetry | 1.15.0 | Traces, metrics, logs via OTLP |
| BCrypt.Net-Next | 4.0.3 | Password hashing |

## Features

- RESTful API with JWT authentication
- SQL Server-native job queue using `READPAST` pattern
- Full OpenTelemetry instrumentation (traces, metrics, logs via OTLP)
- Custom spans with business metrics
- HTTP request metrics (count, duration histogram)
- Trace ID included in error responses
- Trace context propagation to background jobs
- Multi-stage Docker builds
- Built-in rate limiting
- Security headers

## Quick Start

```bash
# Start all services
docker compose up -d

# Wait for services to be ready
sleep 10

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
| POST | /api/logout | Yes | Logout |
| GET | /api/articles | Optional | List articles (paginated) |
| POST | /api/articles | Yes | Create article |
| GET | /api/articles/:slug | Optional | Get article by slug |
| PUT | /api/articles/:slug | Owner | Update article |
| DELETE | /api/articles/:slug | Owner | Delete article |
| POST | /api/articles/:slug/favorite | Yes | Favorite article |
| DELETE | /api/articles/:slug/favorite | Yes | Unfavorite article |

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

## Key Patterns

### Custom Spans in Services

```csharp
private static readonly ActivitySource ActivitySource = new("DotnetSqlServer.ArticleService");

public async Task<ArticleResponse> CreateAsync(int userId, CreateArticleRequest request)
{
    using var activity = ActivitySource.StartActivity("article.create");
    activity?.SetTag("user.id", userId);
    // Business logic here
    AppMetrics.ArticlesCreated.Add(1);
    return response;
}
```

### Error Handling with trace_id

```csharp
app.UseExceptionHandler(errorApp =>
{
    errorApp.Run(async context =>
    {
        var traceId = Activity.Current?.TraceId.ToString();
        context.Response.StatusCode = 500;
        await context.Response.WriteAsJsonAsync(new
        {
            error = "Internal server error",
            trace_id = traceId
        });
    });
});
```

### Minimal APIs with Route Groups

```csharp
var api = app.MapGroup("/api");
api.MapHealthEndpoints();
api.MapAuthEndpoints();
api.MapArticleEndpoints();
```
