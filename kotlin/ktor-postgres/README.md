# Ktor + PostgreSQL + OpenTelemetry

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/ktor/)

Articles CRUD API with distributed tracing, structured logging, and custom metrics — instrumented with the OTel Java Agent.

## How to instrument Ktor with OpenTelemetry

1. Add `io.opentelemetry:opentelemetry-api:1.48.0` to `app/build.gradle.kts` for custom metrics and
   span attributes. HTTP, JDBC and Netty tracing come from the OpenTelemetry Java agent, which
   needs no code dependency.
2. The `Dockerfile` downloads `opentelemetry-javaagent.jar` (`OTEL_AGENT_VERSION=2.28.1`) and
   sets `JAVA_TOOL_OPTIONS="-javaagent:/app/opentelemetry-javaagent.jar"`. There is no
   `install(...)` telemetry plugin in `app/src/main/kotlin/com/example/Application.kt`; the agent instruments Ktor at startup.
3. Set `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT` (`http://otel-collector:4318`),
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` and `OTEL_LOGS_EXPORTER=otlp` in `compose.yaml`.

This example adds a custom `articles.created` counter through `GlobalOpenTelemetry.getMeter`,
attributes on the current span in route handlers, JSON logs exported over OTLP by the agent,
and a second `notify` service called over `java.net.http.HttpClient`. The full guide is
[Ktor OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/ktor/).

## Stack

| Component | Version |
|---|---|
| Kotlin | 2.2.0 |
| Ktor | 3.2.0 |
| Exposed ORM | 0.61.0 |
| PostgreSQL | 18 |
| OTel Java Agent | 2.28.1 |
| OTel Collector | 0.161.0 (contrib) |

## Architecture

```
┌─────────┐    POST /notify    ┌──────────┐
│   app    │──────────────────▶│  notify   │
│ :8080    │                   │  :8081    │
└────┬─────┘                   └─────┬─────┘
     │                               │
     │ JDBC                          │ OTLP
     ▼                               ▼
┌─────────┐                   ┌───────────────┐
│   db    │                   │otel-collector │
│ :5432   │                   │ :4317/:4318   │
└─────────┘                   └───────────────┘
```

Both `app` and `notify` run with the OTel Java Agent attached via `JAVA_TOOL_OPTIONS`. The agent provides zero-code instrumentation for HTTP, JDBC, and Netty — plus trace context propagation across services.

## Quick Start

```bash
cp .env.example .env
# Edit .env with your Scout credentials (optional)

docker compose up -d
./scripts/test-api.sh
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /api/health | Health check (DB connectivity) |
| GET | /api/articles | List articles (paginated) |
| GET | /api/articles/:id | Get article by ID |
| POST | /api/articles | Create article (+ notify) |
| PUT | /api/articles/:id | Update article |
| DELETE | /api/articles/:id | Delete article |

## Observability Signals

**Traces** — OTel Java Agent auto-instruments HTTP server/client and JDBC. Distributed trace context propagates from `app` → `notify` via W3C traceparent headers.

**Logs** — Logback with logstash-encoder produces JSON logs. The Java Agent injects `trace_id` and `span_id` into MDC automatically.

**Metrics** — `articles.created` counter registered via OTel Meter API. JVM and HTTP metrics provided by the Java Agent.

## Scripts

- `scripts/test-api.sh` — Full API + observability test suite
- `scripts/verify-scout.sh` — Verify telemetry export to Base14 Scout
