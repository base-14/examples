# .NET Aspire 13.2 + PostgreSQL 18 + OpenTelemetry

Demonstrates .NET Aspire 13.2 with PostgreSQL 18, exporting OpenTelemetry to base14 Scout.
Two run modes: Aspire AppHost for local development, or a headless Docker Compose stack
for CI and customer-environment use.

> [Full documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/dotnet-aspire/)

## Stack profile

| Component | Version | Notes |
| --- | --- | --- |
| .NET SDK | 9.0.308 | Latest stable; arm64 native on Apple Silicon. |
| ASP.NET Core | 9.0 | Minimal APIs. |
| .NET Aspire | 13.2.4 | AppHost + Hosting.PostgreSQL. Dashboard auth on by default. |
| PostgreSQL | 18 | Aspire-managed in dev; `postgres:18.3` image in Compose. |
| Entity Framework Core | 9.0.15 | `EnsureCreated` at startup; no migrations. |
| Npgsql.EntityFrameworkCore.PostgreSQL | 9.0.4 | EF Core 9 provider. |
| OpenTelemetry .NET (core) | 1.15.3 | OTLP exporter + extensions hosting. |
| OpenTelemetry instrumentation | AspNetCore 1.15.2, Http 1.15.1, Runtime 1.15.1, EFCore 1.15.1-beta.1 | Per-package latest stable (the contrib EF Core package is still beta). |
| OTel Collector contrib | 0.151.0 | Receives OTLP from the apps; OAuth2 export to Scout. |

**Verified**: 2026-04-29.

## What's instrumented

- ASP.NET Core HTTP server spans (auto).
- HttpClient outbound spans (auto). Cross-service `POST /notify` propagates W3C `traceparent` to notify-svc.
- Entity Framework Core DB spans (auto, contrib beta).
- .NET Runtime metrics (auto): GC, thread pool, exceptions.
- Custom `ActivitySource` `AspirePostgres.Articles` with the `article.create` span and `article.id` attribute.
- Custom `Meter` `AspirePostgres.Articles` with `articles.created` counter (incremented on every successful POST).
- Structured logs via OpenTelemetry logging provider; `WARN` on validation failures and 404s, `INFO` on creates.

## Architecture

```text
                                     +---------------------+
                                     |  Aspire dashboard   |  http://localhost:15888/login?t=<token>
                                     |  (AppHost mode)     |  shows resource state and lifecycle
                                     +----------+----------+
                                                |
+---------------------+   +------------------+  |  +---------------------+
|  curl / browser     |-->|  articles-api    |--+->|  notify-svc         |
|  http://localhost   |   |  ASP.NET Core    |     |  ASP.NET Core       |
|  :8080              |   |  EF Core + Npgsql|     |  POST /notify       |
+---------------------+   +-------+----------+     +----------+----------+
                                  |                           |
                                  v                           |
                          +----------------+                  |
                          | PostgreSQL 18  |                  |
                          | (Aspire / pg)  |                  |
                          +----------------+                  |
                                                              |
       all OTLP/gRPC over :4317                               |
       +---------------+ <-----------+----------------------+ +
       | OTel Collector|
       |  contrib 0.151|--->  Scout   (otlphttp + OAuth2)
       +---------------+--->  debug   (local stdout)
```

In **Aspire mode** (`make up`), AppHost orchestrates Postgres and the OTel Collector as Docker containers, while
`articles-api` and `notify-svc` run as host .NET processes that DCP proxies behind stable ports 8080 / 8081. In
**Compose mode** (`make compose-up`), all four services run as Docker containers; identical OTel signals reach the same
collector config.

## Quick start - Aspire mode (recommended for local development)

```bash
cd csharp/aspire-postgres
cp .env.example .env  # optional: fill in SCOUT_* credentials for Scout export

make up
# or: dotnet run --project AppHost/AppHost.csproj
```

AppHost prints a dashboard URL on startup. Look for the `Login to the dashboard at` line - the URL contains a one-time
login token that is regenerated each run:

```text
info: Aspire.Hosting.DistributedApplication[0]
      Login to the dashboard at http://localhost:15888/login?t=<32-char-token>
```

Then in a separate terminal:

```bash
make test-api      # exercises all 6 endpoints, checks distributed tracing
make verify-scout  # requires SCOUT_* in .env
```

## Quick start - Compose mode (CI / headless)

```bash
cd csharp/aspire-postgres
cp .env.example .env  # optional: fill in SCOUT_* credentials

make compose-up      # docker compose up -d --build

make test-api        # against http://localhost:8080
make verify-scout    # requires SCOUT_* in .env

make compose-down    # cleanup
```

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check including DB ping. |
| GET | `/api/articles` | List with pagination (`?page=1&per_page=20`). |
| GET | `/api/articles/{id}` | Detail. 404 emits a structured WARN log. |
| POST | `/api/articles` | Create. Validation failure emits WARN; success calls `notify-svc`. |
| PUT | `/api/articles/{id}` | Update. |
| DELETE | `/api/articles/{id}` | Delete. |

### Response shape

```json
{ "data": { "id": 1, "title": "...", "body": "..." }, "meta": { "trace_id": "..." } }
```

Pagination adds `page`, `per_page`, `total` to `meta`. Errors:

```json
{ "error": { "code": "VALIDATION_FAILED", "message": "..." }, "meta": { "trace_id": "..." } }
```

## Telemetry

### Traces

Auto-instrumented via ServiceDefaults: ASP.NET Core, HttpClient, EF Core. Plus:

- Custom `ActivitySource` `AspirePostgres.Articles` registered on the tracer provider via
  `.AddSource("AspirePostgres.Articles")`. Without this call, custom spans do not export.
- The `article.create` span fires on every successful `POST /api/articles` and tags `article.id`.
- W3C `traceparent` propagates from articles-api to notify-svc; both services share trace IDs in Scout.

### Metrics

Auto-instrumented: ASP.NET Core, HttpClient, .NET Runtime. Plus:

| Metric | Type | Description |
| --- | --- | --- |
| `articles.created` | Counter | Incremented on every successful POST |

Custom `Meter` `AspirePostgres.Articles` is registered on the meter provider via `.AddMeter("AspirePostgres.Articles")`.

### Logs

OpenTelemetry logging provider with trace/span correlation: every log record carries `trace_id` and `span_id` of the
active span. The collector's `transform/log_severity` processor sets `severity_text` from `severity_number` so Scout
displays human-readable INFO/WARN/ERROR labels.

## Environment variables

Application code reads only the right-hand column. AppHost / Compose handle the left-hand column wiring.

| App reads | Aspire injection (AppHost) | Compose injection (compose.yml) |
| --- | --- | --- |
| `ASPNETCORE_HTTP_PORTS` | `WithHttpEndpoint(port: 8080, env: "ASPNETCORE_HTTP_PORTS")` | `8080` for api, `8081` for notify. |
| `ConnectionStrings__articles` | `WithReference(articlesDb)` from postgres database resource. | Explicit `Host=postgres;Port=5432;...`. |
| `Notify__BaseUrl` | `WithEnvironment("Notify__BaseUrl", notify.GetEndpoint("http"))` | `http://notify-svc:8081`. |
| `OTEL_SERVICE_NAME` | Set per project in AppHost. | Set per service in compose.yml. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `collector.GetEndpoint("grpc")` -> `http://localhost:4317`. | `http://otel-collector:4317`. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc`. | `grpc`. |
| `SCOUT_*` (collector use only) | Read from AppHost configuration / `.env`. | Read from `.env` via `env_file`. |

## .NET Aspire-specific notes

- **AppHost uses the package-only Aspire SDK**: `<Sdk Name="Aspire.AppHost.Sdk" Version="13.2.4"/>` (no `dotnet workload
  install` required).
- **Project resources**: `<ProjectReference Include="..\ArticlesApi\ArticlesApi.csproj"
  IsAspireProjectResource="true"/>` triggers source generation of `Projects.ArticlesApi` and `Projects.NotifySvc` typed
  resource names used by `builder.AddProject<Projects.X>("name")`.
- **Endpoint declaration**: use `WithHttpEndpoint(port:, targetPort:, name:)` for any endpoint a .NET project will reach
  via OTLP, even gRPC. Plain `WithEndpoint(...)` produces a `tcp://` URL that the .NET OTLP exporter cannot parse.
- **Port pinning**: Aspire selects ephemeral ports for project resources by default. To pin (so `localhost:8080` is
  stable for scripts and curl), call `WithHttpEndpoint(port: 8080, env: "ASPNETCORE_HTTP_PORTS")` - the `env:` argument
  tells Aspire to also inject `ASPNETCORE_HTTP_PORTS=8080` so Kestrel binds to the requested target port.
- **Service discovery override**: Aspire's default service-discovery env var for the notify endpoint is
  `services__notify-svc__http__0`. The AppHost rewrites that into the simpler `Notify__BaseUrl` the application code
  reads, so application code is identical in Aspire and Compose modes.

## Troubleshooting

### Where is the Aspire dashboard?

`dotnet run --project AppHost/AppHost.csproj` prints two info-level log lines on stdout. Look for the second one:

```text
info: Aspire.Hosting.DistributedApplication[0]
      Login to the dashboard at http://localhost:15888/login?t=<token>
```

The login token is regenerated each run; you must use the full URL from this line, not just `http://localhost:15888/`.
Aspire 13.x has dashboard auth on by default.

### The dashboard's Traces and Metrics tabs are empty

Expected in this configuration. The example overrides `OTEL_EXPORTER_OTLP_ENDPOINT` to point at the local OTel Collector
container instead of the Aspire dashboard's OTLP receiver, because the goal is "Aspire orchestration plus telemetry to
Scout, not Aspire's bundled backend." The collector's debug exporter logs every signal (visible via Aspire dashboard's
per-resource Console panel for `otel-collector`, or `docker logs otel-collector-*`); the otlphttp exporter forwards
everything to Scout when credentials are set.

If you want the dashboard to receive traces too, add a second exporter to ServiceDefaults' OpenTelemetry config that
targets `${DOTNET_DASHBOARD_OTLP_ENDPOINT_URL}` (Aspire injects this automatically). The example keeps the simpler
single-exporter shape.

### Port conflicts on 4317 / 4318 / 13133 / 8080 / 8081

Other examples in this repo also publish these ports. Stop other example stacks before starting this one:

```bash
docker ps --format '{{.Names}}' | grep -E 'pg-|otel-' | xargs -r docker rm -f
```

If port 8080 / 8081 is in use by a system service, edit `WithHttpEndpoint(port: 8080, ...)` in `AppHost/AppHost.cs` and
the `ports:` section of `compose.yml`.

### Postgres slow first pull on Apple Silicon

`postgres:18.3` is ~310 MB and only ships an x86_64 image; Docker Desktop runs it under Rosetta. First pull can take
60-120 seconds depending on bandwidth. Subsequent runs reuse the cached image.

### Expected timing

| Run | Apple Silicon, Rosetta on |
| --- | --- |
| First cold (image pulls + build) | 2 - 4 minutes |
| Warm (`--no-build`, cached pulls) | under 90 seconds |

Cold timing is dominated by `postgres:18.3` and `otel/opentelemetry-collector-contrib:0.151.0` pulls plus the initial
`dotnet build`.

### macOS dashboard cert trust (HTTPS profile)

The default Aspire dashboard uses HTTPS with a dev cert. If your browser shows a cert error, run:

```bash
dotnet dev-certs https --trust
```

The example's `launchSettings.json` ships an `http` profile (no cert needed) and an `https` profile. `make up` picks the
`http` profile.

### `make compose-up` hangs at "articles-api Created"

Check the `articles-api` health probe. The Compose healthcheck calls `curl -f http://localhost:8080/api/health` from
inside the container; if curl is missing in the runtime image, the healthcheck fails and Compose waits. Both Dockerfiles
in this example install curl at build time. Run `docker compose logs articles-api` to see startup errors.

### EF Core "relation 'articles' does not exist"

The application calls `db.Database.EnsureCreated()` at startup, which creates the schema if missing. If you see this
error after a Postgres volume reset, restart the application; `EnsureCreated` runs again on the next launch.

### Postgres container exits during init with "PostgreSQL data in /var/lib/postgresql/data (unused mount/volume)"

You probably bumped the Postgres major version (e.g., 17 → 18) on an existing volume. Postgres 18+ Debian images expect
the volume mounted at `/var/lib/postgresql` (not `/var/lib/postgresql/data`) so they can use a major-version subdirectory
and run `pg_upgrade --link` cleanly. The image refuses to overwrite data from a previous version. Fix:

```bash
docker compose down -v   # discards the old volume; data is lost
docker compose up -d --build
```

If you need to preserve data across a major-version bump, use `pg_upgrade` against a parallel container with both
versions mounted - this example does not script that flow because the article schema is recreated on every run via
`EnsureCreated`.

## Project layout

```text
csharp/aspire-postgres/
+-- AppHost/                 .NET Aspire orchestrator
|   +-- AppHost.cs           DistributedApplication.CreateBuilder + resource wiring
|   +-- AppHost.csproj       Aspire.AppHost.Sdk + IsAspireProjectResource refs
|   +-- Properties/launchSettings.json   http + https profiles
+-- ServiceDefaults/         Cross-cutting OTel + resilience + service discovery
|   +-- Extensions.cs        AddServiceDefaults / MapDefaultEndpoints
|   +-- ServiceDefaults.csproj
+-- ArticlesApi/             ASP.NET Core minimal API
|   +-- Data/                Article entity + AppDbContext (EnsureCreated)
|   +-- Endpoints/           ArticleEndpoints + HealthEndpoints
|   +-- Models/              ArticleDto + ApiResponse wrapper
|   +-- Services/            NotifyService (typed HttpClient)
|   +-- Telemetry/           AppMetrics (Meter + ActivitySource)
|   +-- Program.cs
|   +-- Dockerfile           Multi-stage; non-root `app` user (built into base image)
+-- NotifySvc/               Single-endpoint notify receiver
|   +-- Program.cs
|   +-- Dockerfile
+-- config/
|   +-- otel-collector.yaml  oauth2client + otlp_http/b14 + debug exporters
+-- scripts/
|   +-- test-api.sh          6 endpoints + distributed-trace probe
|   +-- verify-scout.sh      Scout export verification (requires SCOUT_*)
+-- compose.yml              Headless mode; same code, no AppHost
+-- AspirePostgres.sln
+-- Makefile                 build, build-lint, up, compose-up, test-api, verify-scout
+-- .env.example
+-- .gitignore
+-- .dockerignore
```

## Resources

- [.NET Aspire docs](https://learn.microsoft.com/dotnet/aspire/)
- [OpenTelemetry .NET](https://opentelemetry.io/docs/languages/net/)
- [base14 Scout](https://base14.io)
- [base14 Scout documentation](https://docs.base14.io)
