# PHP Hello World — OpenTelemetry

A minimal PHP app that sends a **trace**, a **log**, and a **metric** to an OpenTelemetry collector. It demonstrates the three core signals of observability and how they connect.

## What You'll See in Scout

After running this app, open Scout and look for:

- **TraceX** — three spans under service `hello-world-php`: `say-hello` (ok), `check-disk-space` (ok), `parse-config` (error)
- **LogX** — three log entries under service `hello-world-php`: an INFO, a WARN, and an ERROR — all correlated to their traces
- **Metrics** — a `hello.count` counter

Click a log entry in LogX → **Trace Info** tab → **Open trace details** to see the trace it belongs to. This is log-trace correlation in action.

## Key Concepts

- **Span** — a unit of work your app performs, with a start time, duration, and status
- **Log-trace correlation** — when a log is emitted inside a span, it carries the span's trace ID, so you can jump between logs and traces
- **Metric** — a numeric measurement (here, a simple counter that tracks how many times the app runs)

## Prerequisites

- Docker (no local PHP installation needed)
- A running OpenTelemetry collector accepting OTLP/HTTP on port 4318 (see [collector setup docs](../../scout-collector/README.md))

## Run It

```bash
# Build the Docker image
docker build -t hello-world-php .

# Run the app, pointing at your collector
docker run --rm --network host -e OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 hello-world-php
```

You should see:

```
Done. Check Scout for your trace, log, and metric.
```

## Verify in Scout

1. **Traces** — go to TraceX, search for service `hello-world-php`. You'll see three spans: `say-hello`, `check-disk-space`, and `parse-config` (marked as error with an exception).
2. **Logs** — go to LogX, search for service `hello-world-php`. You'll see three entries at different severity levels (INFO, WARN, ERROR). Click any log → Trace Info → Open trace details to see the correlated trace.
3. **Metric** — look for the `hello.count` counter under service `hello-world-php`.

## Signals Included

| Signal | Status | Notes |
|---|---|---|
| Traces | Stable | Production-ready |
| Metrics | Stable | Production-ready |
| Logs | Stable | Production-ready |

See [OTel SDK Signal Maturity](https://opentelemetry.io/docs/languages/php/) for details.
