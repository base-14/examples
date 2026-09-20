# Micronaut + PostgreSQL + OpenTelemetry

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/micronaut/)

Articles CRUD API with distributed tracing, structured logging, and custom metrics — instrumented with the OTel Java Agent.

## How to instrument Micronaut with OpenTelemetry

1. Add `io.opentelemetry:opentelemetry-api` to `app/build.gradle.kts` (version from
   `opentelemetry-bom` 1.65.0) alongside `micronaut-data-hibernate-jpa` and `micronaut-jdbc-hikari`.
   The agent itself is not a build dependency.
2. Attach the agent at startup. Each service's `Dockerfile` downloads `opentelemetry-javaagent.jar`
   (2.28.1) and sets `JAVA_TOOL_OPTIONS="-javaagent:/app/opentelemetry-javaagent.jar"`, so HTTP,
   JDBC and Hibernate are traced with no Micronaut tracing module.
3. Configure export in `compose.yaml` with `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`,
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, an `OTEL_SERVICE_NAME` per service, and
   `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER` and `OTEL_LOGS_EXPORTER` set to `otlp`.

This example adds a second service (`notify`) called over HTTP so one trace spans both services, a
custom `articles.created` counter registered through `GlobalOpenTelemetry.getMeter`, and structured
JSON logs via `logstash-logback-encoder`. The full guide is
[Micronaut OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/micronaut/).

## Stack

| Component | Version |
|---|---|
| Java | 25 (Eclipse Temurin) |
| Micronaut | 4.8.x |
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
