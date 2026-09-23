# Go stdlib net/http + PostgreSQL + OpenTelemetry

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/go/)

End-to-end observability example using only the Go standard library
`net/http`, `pgx` for PostgreSQL, and the OTel Go SDK.

## How to instrument Go net/http with OpenTelemetry

1. Add `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp`,
   `github.com/exaring/otelpgx`, `go.opentelemetry.io/contrib/bridges/otelslog`,
   `go.opentelemetry.io/otel/sdk` and the `otlptracehttp`, `otlpmetrichttp` and `otlploghttp`
   exporters to `go.mod`.
2. Wrap the mux with `otelhttp.NewHandler(mux, "http.server", ...)`, set
   `cfg.ConnConfig.Tracer = otelpgx.NewTracer()` on the pgx pool config, and use
   `otelhttp.NewTransport` for outbound calls; `initTelemetry` sets the global tracer, meter
   and logger providers.
3. Set `OTEL_SERVICE_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT` (`http://otel-collector:4318`) in
   `compose.yaml`; `OTEL_RESOURCE_ATTRIBUTES` carries `deployment.environment.name` and
   `service.namespace`.

This example adds pgx query spans, slog logs exported over OTLP through the otelslog bridge, a
custom `articles.created` counter, and trace propagation to a second `notify` service. The full
guide is [Go stdlib OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/go-stdlib-postgres/).

## Stack

| Component | Version |
| --- | --- |
| Go | 1.26 |
| pgx | v5.9 |
| PostgreSQL | 18 |
| otelhttp | 0.68 |
| otelpgx | latest |
| OTel Go SDK | 1.43 |
| OTel logs SDK + bridge | 0.19 |
| OTel Collector | 0.161.0 |

## Architecture

```
+----------------------------------------+
|  stdlib-articles API   (port 8080)     |
|  +-------+  +-------+  +-----------+   |
|  | mux   |->| repo  |->| Postgres  |   |
|  | (1.22 |  | (pgx) |  |    18     |   |
|  | mux)  |  +-------+  +-----------+   |
|  +---+---+                             |
|      | http.Client + traceparent       |
|      v                                 |
|  +--------------------+                |
|  |  stdlib-notify     | (port 8081)    |
|  +--------------------+                |
+--------------+-------------------------+
               | OTLP HTTP (:4318)
               v
        +---------------+
        | OTel Collector| -> Scout / debug
        +---------------+
```

`POST /api/articles` writes the row, calls `POST notify:8081/notify` over an
otelhttp-instrumented client (W3C `traceparent` propagated automatically), and
returns the article. The notify service receives the same trace and emits its
own server span.

## Quick start

```bash
docker compose up -d --build
curl http://localhost:8080/api/health
```

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/articles?page=&per_page=` | List articles (paginated) |
| GET | `/api/articles/{id}` | Get article by ID |
| POST | `/api/articles` | Create article + fan out to notify |
| PUT | `/api/articles/{id}` | Update article |
| DELETE | `/api/articles/{id}` | Delete article |

Responses are wrapped:

```json
{ "data": { "id": 1, "title": "...", "body": "..." }, "meta": { "trace_id": "..." } }
```

Errors:

```json
{ "error": { "code": "NOT_FOUND", "message": "..." }, "meta": { "trace_id": "..." } }
```

## Observability

**Traces.** `otelhttp.NewHandler` wraps the `http.ServeMux` for server spans;
`otelhttp.NewTransport` instruments the outbound notify call. `otelpgx` adds
`pool.acquire`, `prepare`, and `query` spans on every DB call. W3C
`traceparent` propagates app -> notify automatically.

**Logs.** `slog` JSON to stdout for local tail, plus the
`go.opentelemetry.io/contrib/bridges/otelslog` bridge for OTLP export to the
collector. A custom handler reads `trace.SpanFromContext(ctx)` and adds
`trace_id`/`span_id` to every record. WARN logs fire on 400 (invalid id), 404
(not found), and 422 (validation).

**Metrics.** `articles.created` `Int64Counter` is incremented on every
successful `POST /api/articles`.

## Testing

```bash
# Functional + observability checks
make test-api

# Scout export verification (requires credentials)
make verify-scout
```

## Scout configuration

```bash
cp .env.example .env
# Edit .env with your Scout credentials
docker compose up -d --build
```

Required variables:

- `SCOUT_ENDPOINT`
- `SCOUT_CLIENT_ID`
- `SCOUT_CLIENT_SECRET`
- `SCOUT_TOKEN_URL`
- `SCOUT_ENVIRONMENT` (defaults to `development`)

## Layout

```
go/stdlib-postgres/
├── app/                 # stdlib-articles (port 8080)
│   ├── main.go          # bootstraps OTel, pgx pool, mux
│   ├── telemetry.go     # tracer + meter + logger providers
│   ├── handler/         # health + article HTTP handlers
│   ├── middleware/      # slog handler with trace context
│   ├── model/           # Article + schema.sql constant
│   ├── repository/      # pgx queries (List/Get/Create/Update/Delete)
│   └── service/         # otelhttp-instrumented notify client
├── notify/              # stdlib-notify (port 8081)
├── config/              # OTel collector config (oauth2 -> Scout)
└── scripts/             # test-api.sh, verify-scout.sh
```
