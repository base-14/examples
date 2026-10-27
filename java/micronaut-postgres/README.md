# Micronaut + PostgreSQL + OpenTelemetry

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/micronaut/)

Articles CRUD API with distributed tracing, structured logging, and custom metrics, instrumented with the OTel Java Agent.

## How to instrument Micronaut with OpenTelemetry

1. Add `io.opentelemetry:opentelemetry-api` to `app/build.gradle.kts` (version from
   `opentelemetry-bom` 1.65.0) alongside `micronaut-data-hibernate-jpa` and `micronaut-jdbc-hikari`.
   The agent itself is not a build dependency.
2. Attach the agent at startup. Each service's `Dockerfile` downloads `opentelemetry-javaagent.jar`
   (2.33.1) and sets `JAVA_TOOL_OPTIONS="-javaagent:/app/opentelemetry-javaagent.jar"`, so HTTP,
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
| Micronaut | 5.2.x |
| PostgreSQL | 18 |
| OTel Java Agent | 2.33.1 |
| OTel Collector | 0.163.1 (contrib) |

Run Gradle on JDK 25 for host builds (`make build`, `make check`). The Micronaut 5
Gradle plugin requires it.

## Architecture

```text
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

Both `app` and `notify` run with the OTel Java Agent attached via `JAVA_TOOL_OPTIONS`. The agent
instruments HTTP, JDBC, and Netty with no code changes and propagates trace context across services.

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

**Traces.** The OTel Java Agent instruments HTTP server and client calls and JDBC. Trace context propagates from `app` to `notify` through W3C `traceparent` headers.

**Logs.** Logback with logstash-encoder writes JSON logs. The Java Agent adds `trace_id` and `span_id` to the MDC.

**Metrics.** The `articles.created` counter is registered through the OTel Meter API. The Java Agent provides JVM and HTTP metrics.

## Scripts

- `scripts/test-api.sh` - full API and observability test suite.
- `scripts/verify-scout.sh` - verifies telemetry export to Base14 Scout.
