# Temporal Workflow Tracing with OpenTelemetry

Demonstrates distributed tracing for a Temporal Java SDK application using OpenTelemetry, exporting traces to [Scout](https://base14.io).

## What's Instrumented

- Workflow execution spans (`StartWorkflow`, `RunWorkflow`)
- Activity execution spans (`StartActivity`, `RunActivity`)
- Cross-worker trace context propagation (workflow → activity spans share a single trace)

## Prerequisites

- Docker and Docker Compose
- (Optional) Scout credentials for remote export — without them, traces are visible locally via the collector's debug exporter

## Quick Start

```bash
# Clone and enter the example
cd java/temporal-tracing

# Option A: With Scout credentials
cp .env.example .env
# Edit .env with your Scout credentials
docker compose up --build

# Option B: Local only (no Scout credentials, no auth errors in logs)
OTEL_CONFIG=config/otel-config-local.yaml docker compose up --build
```

Watch the `app` container logs for:
```
Worker started on task queue: tracing-example-queue
Workflow result: Hello World!
Traces exported. Worker staying alive...
```

The Temporal UI is available at http://localhost:8080 to inspect workflow executions.

Then verify traces reached the collector:
```bash
docker compose logs otel-collector | grep "Name"
```

## How It Works

The Temporal Java SDK uses **OpenTracing-based interceptors** bridged to OpenTelemetry via a shim:

```
Java App (OpenTracing interceptors)
    ↓ bridged via OpenTracing → OTel shim
OpenTelemetry SDK (BatchSpanProcessor)
    ↓ OTLP gRPC
OTel Collector
    ↓ OTLP HTTP + OAuth2
Scout
```

Two interceptors are registered:
1. **Client interceptor** (`OpenTracingClientInterceptor`) — creates spans when workflows are started
2. **Worker interceptor** (`OpenTracingWorkerInterceptor`) — propagates trace context into workflow and activity executions

Both are required. Without the worker interceptor, spans start but never propagate into workflow/activity code.

## Telemetry Data

A single workflow execution produces this span tree (all sharing one trace ID):

```
StartWorkflow:GreetingWorkflow        (root — client side)
  └── RunWorkflow:GreetingWorkflow    (worker side)
        └── StartActivity:ComposeGreeting
              └── RunActivity:ComposeGreeting
```

## Configuration

| Environment Variable | Code Default | Docker Compose Override | Description |
|---------------------|-------------|------------------------|-------------|
| `TEMPORAL_ADDRESS` | `localhost:7233` | `temporal:7233` | Temporal server address |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | `http://otel-collector:4317` | OTel Collector OTLP gRPC endpoint |
| `OTEL_SERVICE_NAME` | `temporal-tracing-example` | `temporal-tracing-example` | Service name in traces |

When running locally outside Docker, the code defaults (`localhost`) apply. Inside Docker Compose, the environment variables in `compose.yaml` override them to use container hostnames.

## Caveats

- **OTel Baggage may not propagate through Temporal workflows.** This tracing approach uses an OpenTracing → OpenTelemetry shim. If your application also uses the OTel API directly (e.g., via the OTel Java agent for HTTP/DB instrumentation), [Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/) set via the OTel API may not arrive inside Temporal workflows/activities. Standard trace/span propagation is unaffected — this only matters if you rely on OTel Baggage for cross-service key-value propagation alongside Temporal.

- **Don't register global OpenTelemetry twice.** If your app already registers a global OTel instance (e.g., via the Java agent), skip `buildAndRegisterGlobal()` and create the shim from the existing instance: `OpenTracingShim.createTracerShim(GlobalOpenTelemetry.get())`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Spans for client but not inside workflows | Missing worker interceptor | Add `OpenTracingWorkerInterceptor` to `WorkerFactoryOptions` |
| No traces reach Scout | Collector has no traces pipeline | Add OTLP receiver + traces pipeline to collector config |
| App starts but no spans appear | OTel endpoint wrong | Check `OTEL_EXPORTER_OTLP_ENDPOINT` points to collector |

## Scripts

```bash
./scripts/test-workflow.sh    # Verify workflow executed successfully
./scripts/verify-scout.sh    # Verify traces appear in collector
```

## Technology Stack

| Component | Version |
|-----------|---------|
| Java | 17 |
| Temporal SDK | 1.25.0 |
| OpenTelemetry SDK | 1.40.0 |
| OpenTelemetry Collector | contrib 0.144.0 |
