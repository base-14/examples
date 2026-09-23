# .NET 8.0.22 ASP.NET Core + SQL Server zero-code OpenTelemetry Example

A hello-world ASP.NET Core Minimal API on .NET 8.0.22 that writes greetings to SQL Server. It contains no
OpenTelemetry code. Traces, metrics and logs come from the OpenTelemetry .NET Automatic Instrumentation
NuGet package and `OTEL_` environment variables.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/dotnet)

## How to instrument ASP.NET Core on .NET 8 without code changes

1. Add `OpenTelemetry.AutoInstrumentation` to `HelloSqlServer.csproj`. The build copies `instrument.sh`, the CLR
   profiler and the instrumentation assemblies into the publish folder.
2. Start the app through that script. The `Dockerfile` entrypoint is `./instrument.sh dotnet HelloSqlServer.dll`.
3. Set `OTEL_SERVICE_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT` in `compose.yaml`. The default protocol is
   `http/protobuf`, so the endpoint is the collector's port 4318.

The SDK-in-code alternative for the same stack is in [dotnet-sqlserver](../dotnet-sqlserver), which targets .NET 10.

## Stack Profile

| Component | Version | Status | Notes |
| --- | --- | --- | --- |
| **.NET runtime** | 8.0.22 | Maintenance | November 2025 patch. .NET 8 leaves support on 2026-11-10. |
| **.NET SDK** | 8.0.416 | Maintenance | Pinned in `global.json` and the build image. |
| **ASP.NET Core** | 8.0.22 | Maintenance | Minimal APIs. |
| **OpenTelemetry.AutoInstrumentation** | 1.17.0 | Experimental | Zero-code profiler, released 2026-09-22. Targets net8.0 and net462. |
| **Microsoft.Data.SqlClient** | 7.1.0 | Active | Raw ADO.NET, no ORM. |
| **Azure SQL Edge** | latest | Retired | SQL Server compatible, runs on ARM64. Swap via `SQL_IMAGE`. |
| **OpenTelemetry Collector** | 0.161.0 | Active | contrib image, forwards to Scout. |

**Verified**: 2026-09-17 on macOS ARM64 with Docker.

## What Gets Emitted

Recorded from the collector debug exporter on the verified run.

### Traces

- One `Server` span per request from scope `Microsoft.AspNetCore`, named by route, for example `GET /api/hello/{name}`,
  with `http.route`, `url.path`, `http.response.status_code` and `user_agent.original`.
- One `Client` span per SQL command from scope `OpenTelemetry.Instrumentation.SqlClient`, named by the query summary,
  for example `INSERT dbo.Greetings`, with `db.system.name`, `db.namespace`, `server.address`, `db.query.text`
  (parameters replaced by `?`) and `db.query.summary`.
- Resource attributes include `process.runtime.version=8.0.22`, `host.arch`, `container.id` and
  `telemetry.distro.name=opentelemetry-dotnet-instrumentation`.

### Metrics

Exported every 60 seconds by default.

- `http.server.request.duration`, `http.server.active_requests` from ASP.NET Core hosting.
- `kestrel.*` connection metrics and `aspnetcore.routing.match_attempts`.
- `db.client.operation.duration` from SqlClient.
- `process.runtime.dotnet.*` GC, JIT, thread pool and exception counters.
- `process.cpu.time`, `process.memory.usage` and other process metrics.
- `http.client.*` and `dns.lookup.duration`, present but idle in this example.

### Logs

- Every `ILogger` record from the app, with the structured fields as attributes and the formatted message as the body.
- Each record carries the trace id and span id of the request that produced it.

## What the Zero-Code Path Does Not Cover

- Custom `ActivitySource` spans and custom `Meter` instruments are not collected unless their names are listed in
  `OTEL_DOTNET_AUTO_TRACES_ADDITIONAL_SOURCES` and `OTEL_DOTNET_AUTO_METRICS_ADDITIONAL_SOURCES`.
- Every instrumentation in this package is marked Experimental by the project. Span and metric names can change
  between releases.
- ARM64 support is marked experimental. The verified run was on linux/arm64.
- The startup hook logs a warning that .NET 8 and the automatic instrumentation for it end support on 2026-11-10.
- `InvariantGlobalization` must stay off. Microsoft.Data.SqlClient throws at connection open when it is on.
- The publish step needs a RuntimeIdentifier, or it copies native profiler libraries for every platform. The
  `Dockerfile` maps Docker's `TARGETARCH` to `linux-x64` or `linux-arm64`.

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io), optional for a local run
3. **.NET SDK 8.0.416** only for `make check` and `make format` outside Docker

## Quick Start

```bash
cd examples/csharp/dotnet8-sqlserver-hello
cp .env.example .env
docker compose up -d
./scripts/test-api.sh
./scripts/verify-otel.sh
```

The verify script generates traffic, waits for the first metrics export and checks the collector output for a
server span, a SqlClient span, request duration and runtime metrics, and a correlated log record.

### Endpoints

| Method | Path | Behaviour |
| --- | --- | --- |
| GET | `/api/health` | Runs `SELECT 1` and returns `{"status":"healthy"}`. |
| GET | `/api/hello/{name}` | Inserts a row into `dbo.Greetings` and returns the message and the running count. |

The database and table are created on startup. The app retries the connection for 45 seconds while SQL Server
starts.

### Environment Variables

| Variable | Default in compose | Purpose |
| --- | --- | --- |
| `OTEL_SERVICE_NAME` | `dotnet8-sqlserver-hello` | Service name on every signal. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | OTLP/HTTP endpoint. |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment.name` and `environment`, from `SCOUT_ENVIRONMENT` | Extra resource attributes. |
| `OTEL_DOTNET_AUTO_LOGS_INCLUDE_FORMATTED_MESSAGE` | `true` | Send the rendered message as the log body. |
| `SQL_IMAGE` | `mcr.microsoft.com/azure-sql-edge:latest` | Use `mcr.microsoft.com/mssql/server:2025-latest` on x64. |
| `MSSQL_SA_PASSWORD` | `YourStrong@Passw0rd` | SQL Server password. |
| `SCOUT_*` | unset | Collector credentials for Scout. Local runs work without them. |

The full list of `OTEL_DOTNET_AUTO_*` settings is in the
[automatic instrumentation configuration reference](https://opentelemetry.io/docs/zero-code/dotnet/configuration/).

### Troubleshooting

The instrumentation writes its own logs to `/var/log/opentelemetry/dotnet/` inside the container:

```bash
docker compose exec api sh -c 'cat /var/log/opentelemetry/dotnet/*Managed*.log'
```

Lines reading `Export succeeded for .../v1/traces` confirm the exporter is reaching the collector.

## Verify in Scout

1. **Traces** - search for service `dotnet8-sqlserver-hello`. Each request shows a server span with one or two
   SqlClient child spans.
2. **Logs** - search for the same service. Open a `Greeted` entry and follow Trace Info to the request trace.
3. **Metrics** - look for `http.server.request.duration` and `process.runtime.dotnet.gc.collections.count`.

## Project Layout

```text
dotnet8-sqlserver-hello/
├── Program.cs              Minimal API, two endpoints
├── GreetingStore.cs        Schema setup, ping and insert via Microsoft.Data.SqlClient
├── HelloSqlServer.csproj   net8.0, SqlClient 7.1.0, AutoInstrumentation 1.17.0
├── global.json             SDK 8.0.416
├── Dockerfile              sdk:8.0.416 build, aspnet:8.0.22 runtime, instrument.sh entrypoint
├── compose.yaml            api, sqlserver, otel-collector
├── config/otel-config.yaml Collector pipelines to Scout and the debug exporter
└── scripts/                test-api.sh, verify-otel.sh
```

## Signals Included

| Signal | Status | Notes |
| --- | --- | --- |
| Traces | Experimental | ASP.NET Core and SqlClient via the automatic instrumentation. |
| Metrics | Experimental | ASP.NET Core, Kestrel, SqlClient, runtime and process. |
| Logs | Experimental | ILogger bridge with trace correlation. |
